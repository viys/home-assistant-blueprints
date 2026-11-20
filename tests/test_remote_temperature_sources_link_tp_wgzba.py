"""Behavior checks for firmware-dependent TP-WGZBA multi-source synchronization."""

import unittest

from tools.blueprint_coverage import ROOT
from tools.blueprint_runner import BlueprintRunner, HandledServiceError, ha_bool


def sources(integration="zha", version="0x00001006", extras=True):
    """Configure independent source entities and the target firmware metadata."""
    # All source validity and version routing are evaluated from the original YAML.
    run = BlueprintRunner(ROOT / "automation/sonoff/remote_temperature_sources_link_tp_wgzba.yaml",
                          dict(target_device="target", source_entity_1="sensor.source1",
                               source_entity_2="sensor.source2" if extras else "",
                               source_entity_3="sensor.source3" if extras else ""))
    run.devices["target"] = dict(manufacturer="SONOFF", model="TP-WGZBA" if integration == "zha" else "Zigbee thermostat panel",
                                  identifiers=[(integration, "00:11")], sw_version=version)
    run.entity_map["target"] = ["sensor.target_temperature_source_mode",
                                "select.target_temperature_sensor_select",
                                "number.target_external_temperature_input"]
    run.set_state("sensor.target_temperature_source_mode", "external_sensor", device_class="enum")
    for index in (1, 2, 3):
        run.set_state(f"sensor.source{index}", str(19 + index), "°C")
    return run


class MultiSourceTests(unittest.TestCase):
    """Check independent routing, optional unbinding, units, and firmware boundaries."""

    def test_new_firmware_updates_only_the_changed_source(self):
        """A source change writes only its corresponding quirk attribute."""
        # Each source is exercised in Celsius, Fahrenheit, and Kelvin.
        for index in (1, 2, 3):
            for value, unit in (("20", "°C"), ("68", "°F"), ("293.15", "K")):
                with self.subTest(source=index, unit=unit):
                    run = sources()
                    entity = f"sensor.source{index}"
                    new = run.set_state(entity, value, unit)
                    run.fire("source_changed", entity=entity, new_state=new)
                    self.assertEqual(len(run.calls), 1)
                    self.assertEqual(run.calls[0]["action"], "zha.set_zigbee_cluster_attribute")
                    self.assertEqual(run.calls[0]["data"], dict(ieee="00:11", endpoint_id=1,
                                     cluster_id=0xFC11, cluster_type="in", attribute=0xFF10 + index, value=2000))

    def test_startup_reload_and_switch_enable_full_sync(self):
        """Full sync serially writes all configured sources on supported ZHA firmware."""
        # Verify order and values, not merely the number of actions reached.
        for trigger in ("ha_started", "automation_reloaded", "source_changed"):
            run = sources()
            run.fire(trigger, entity="sensor.target_temperature_source_mode", new_state={"state": "external_sensor"})
            self.assertEqual([(call["data"]["attribute"], call["data"]["value"]) for call in run.calls],
                             [(0xFF11, 2000), (0xFF12, 2100), (0xFF13, 2200)])

    def test_localized_mode_sensor_controls_zha_sync(self):
        """Use the enum state even when the switch has no English suffix."""
        # Both the mode sensor and the switch can have localized IDs.
        run = sources()
        mode = "sensor.target_temperaturquelle"
        run.entity_map["target"][0] = "switch.target_externer_temperatursensor"
        run.entity_map["target"].append(mode)
        internal = run.set_state(mode, "internal_sensor", device_class="enum")
        run.fire("ha_started")
        self.assertEqual(run.calls, [])
        external = run.set_state(mode, "external_sensor", device_class="enum")
        run.dispatch_state(mode, internal, external)
        self.assertEqual([call["data"]["attribute"] for call in run.calls],
                         [0xFF11, 0xFF12, 0xFF13])

    def test_unavailable_mode_does_not_fall_back_on_startup(self):
        """Skip startup synchronization when the mode cannot be confirmed."""
        # An enabled legacy switch must not authorize a full sync.
        run = sources()
        legacy_switch = "switch.target_external_temperature_sensor"
        run.entity_map["target"].append(legacy_switch)
        run.set_state(legacy_switch, "on")
        run.set_state(run.entity_map["target"][0], "unavailable", device_class="enum")
        run.fire("ha_started")
        self.assertEqual(run.calls, [])

    def test_blank_optional_sources_unbind_only_on_full_sync(self):
        """Empty optional slots send the unbind sentinel during full synchronization."""
        # A normal source-1 update must not repeatedly clear unrelated slots.
        run = sources(extras=False)
        run.fire("ha_started")
        self.assertEqual([call["data"]["value"] for call in run.calls], [2000, -32768, -32768])
        run.calls.clear()
        run.fire("source_changed", entity="sensor.source1", new_state=run.states["sensor.source1"])
        self.assertEqual([call["data"]["attribute"] for call in run.calls], [0xFF11])

    def test_invalid_sources_do_not_block_valid_peers(self):
        """Skip an invalid configured source while synchronizing other valid sources."""
        # Unlike blank inputs, unavailable inputs must not send unbind sentinels.
        for index in (1, 2, 3):
            for value, unit in (("unavailable", "°C"), ("unknown", "°C"), ("NaN", "°C"),
                                ("20", "bad"), ("327.68", "°C"), ("-273.16", "°C")):
                run = sources()
                run.set_state(f"sensor.source{index}", value, unit)
                run.fire("automation_reloaded")
                expected = [0xFF10 + other for other in (1, 2, 3) if other != index]
                self.assertEqual([call["data"]["attribute"] for call in run.calls], expected)
                self.assertNotIn(-32768, [call["data"]["value"] for call in run.calls])

    def test_each_source_rejects_self_reference_and_accepts_numeric_boundaries(self):
        """Check independent self-source rejection and the declared encodable range."""
        # Boundary inputs must reach the exact centidegree payload without clamping.
        for index in (1, 2, 3):
            run = sources()
            run.entity_map["target"].append(f"sensor.source{index}")
            run.fire("ha_started")
            self.assertNotIn(0xFF10 + index, [call["data"]["attribute"] for call in run.calls])
            for value, encoded in (("-273.15", -27315), ("327.67", 32767)):
                run = sources()
                entity = f"sensor.source{index}"
                run.set_state(entity, value, "°C")
                run.fire("source_changed", entity=entity, new_state=run.states[entity])
                self.assertEqual(run.calls[0]["data"]["value"], encoded)

    def test_legacy_firmware_and_unrecognized_versions_use_source_one(self):
        """Use the exact hexadecimal firmware boundary, with a safe legacy fallback."""
        # Dotted, missing, malformed, and short hex versions must not enable three slots.
        for version in ("0x00001005", "1.0.6", None, "garbage", "0x1006", "0xzzzzzzzz"):
            run = sources(version=version)
            run.fire("ha_started")
            self.assertFalse(ha_bool(run.last_scope["supports_multi_remote_temperature"]))
            self.assertEqual([(call["data"]["attribute"], call["data"]["value"]) for call in run.calls], [(0xFF11, 2000)])
            run.calls.clear()
            run.fire("source_changed", entity="sensor.source2", new_state=run.states["sensor.source2"])
            self.assertEqual(run.calls, [])
            run.set_state("sensor.source1", "unavailable")
            run.fire("automation_reloaded")
            self.assertEqual(run.calls, [])
        for version in ("0x00001006", "0X00001006", "0x00001007"):
            run = sources(version=version)
            run.fire("ha_started")
            self.assertTrue(ha_bool(run.last_scope["supports_multi_remote_temperature"]))
            self.assertEqual(len(run.calls), 3)

    def test_legacy_source_one_conversion(self):
        """The legacy branch converts every supported temperature unit."""
        # Multi-source and legacy branches must agree on source-1 payload units.
        for value, unit in (("20", "°C"), ("68", "°F"), ("293.15", "K")):
            run = sources(version="0x00001005")
            run.set_state("sensor.source1", value, unit)
            run.fire("source_changed", entity="sensor.source1", new_state=run.states["sensor.source1"])
            self.assertEqual(run.calls[0]["data"]["value"], 2000)

    def test_mqtt_sends_only_source_one_updates(self):
        """Legacy MQTT converters retain source-one-only update behavior."""
        # Source 2/3 events and startup/reload must not generate stray MQTT writes.
        for value, unit in (("20", "°C"), ("68", "°F"), ("293.15", "K")):
            run = sources("mqtt")
            run.set_state("sensor.source1", value, unit)
            run.fire("source_changed", entity="sensor.source1", new_state=run.states["sensor.source1"])
            self.assertEqual(run.calls, [{"action": "number.set_value",
                                          "target": {"entity_id": "number.target_external_temperature_input"},
                                          "data": {"value": 20}}])
        for trigger, entity in (("ha_started", None), ("automation_reloaded", None),
                                ("source_changed", "sensor.source2"), ("source_changed", "sensor.source3")):
            run = sources("mqtt")
            run.fire(trigger, entity=entity, new_state=run.states[entity])
            self.assertEqual(run.calls, [])
        run = sources("mqtt")
        run.set_state("sensor.source1", "unavailable")
        run.fire("source_changed", entity="sensor.source1", new_state=run.states["sensor.source1"])
        self.assertEqual(run.calls, [])

    def test_off_unrelated_removed_and_wrong_target_events_skip(self):
        """Reject disabled mode, unrelated events, and incompatible target metadata."""
        # The common condition filters are exercised separately from action choices.
        run = sources()
        run.set_state("sensor.target_temperature_source_mode", "internal_sensor", device_class="enum")
        run.fire("source_changed", entity="sensor.source1", new_state=run.states["sensor.source1"])
        self.assertEqual(run.calls, [])
        run = sources()
        run.fire("source_changed", entity="sensor.unrelated", new_state={"state": "on"})
        run.fire("source_changed", entity="sensor.target_temperature_source_mode", new_state=None)
        self.assertEqual(run.calls, [])
        for integration in ("zha", "mqtt"):
            for field, value in (("manufacturer", "OTHER"), ("model", "OTHER"), ("identifiers", [])):
                run = sources(integration)
                run.devices["target"][field] = value
                run.fire("ha_started")
                self.assertEqual(run.calls, [])
            run = sources(integration)
            run.entity_map["target"] = []
            run.fire("ha_started")
            self.assertEqual(run.calls, [])

    def test_failed_full_sync_stops_and_later_source_event_still_runs(self):
        """Record the existing lack of per-source service-error isolation honestly."""
        # These tests do not claim the queued HA runtime retries a failed full sync.
        run = sources()
        run.fail.add(0xFF11)
        with self.assertRaises(HandledServiceError):
            run.fire("ha_started")
        self.assertEqual([call["data"]["attribute"] for call in run.calls], [0xFF11])
        run.fail.clear()
        run.fire("source_changed", entity="sensor.source2", new_state=run.states["sensor.source2"])
        self.assertEqual(run.calls[-1]["data"]["attribute"], 0xFF12)


def mqtt_sources(extras=True):
    """Model the three numbered inputs exposed by the supplied Z2M converter."""
    # Multi-source converters replace the legacy number and temperature select.
    run = sources("mqtt", version="1.0.6", extras=extras)
    run.entity_map["target"] = []
    for index in (1, 2, 3):
        number = f"number.target_external_temperature_input_{index}"
        select = f"select.target_external_temperature_input_{index}_state"
        run.entity_map["target"].extend([number, select])
        run.set_state(number, "20", "°C", min=0, max=99.9, step=0.1)
        run.set_state(select, "unbound", options=["online", "offline", "unbound", "restored"])
    return run


class MqttMultiSourceTests(unittest.TestCase):
    """Exercise the numbered converter contract using the actual blueprint YAML."""

    def test_each_source_update_converts_and_routes_independently(self):
        """Only the changed slot receives a Celsius value at converter precision."""
        # Setting a temperature defaults to online in the converter, without a second call.
        for index in (1, 2, 3):
            for value, unit in (("20.24", "°C"), ("68.432", "°F"), ("293.39", "K")):
                with self.subTest(index=index, unit=unit):
                    run = mqtt_sources()
                    entity = f"sensor.source{index}"
                    new = run.set_state(entity, value, unit)
                    run.dispatch_state(entity, None, new)
                    self.assertEqual(run.calls, [dict(action="number.set_value",
                        target=dict(entity_id=f"number.target_external_temperature_input_{index}"),
                        data=dict(value=20.2))])

    def test_startup_and_reload_sync_all_sources(self):
        """MQTT capability comes from numbered entities rather than ZHA version strings."""
        # Z2M reports dotted firmware versions and needs no ZHA enum mode sensor.
        for trigger in ("ha_started", "automation_reloaded"):
            run = mqtt_sources()
            run.fire(trigger)
            self.assertEqual([(call["target"]["entity_id"], call["data"]) for call in run.calls],
                [(f"number.target_external_temperature_input_{index}", dict(value=19 + index))
                 for index in (1, 2, 3)])

    def test_empty_optional_sources_unbind_on_full_sync(self):
        """Unbinding uses the state selects rather than writing a numeric sentinel."""
        # Source updates must not repeatedly clear the other slots.
        for trigger in ("ha_started", "automation_reloaded"):
            run = mqtt_sources(extras=False)
            run.fire(trigger)
            self.assertEqual(run.calls[0]["data"], dict(value=20))
            self.assertEqual(run.calls[1:], [dict(action="select.select_option",
                target=dict(entity_id=f"select.target_external_temperature_input_{index}_state"),
                data=dict(option="unbound")) for index in (2, 3)])
            run.calls.clear()
            run.fire("source_changed", entity="sensor.source1", new_state=run.states["sensor.source1"])
            self.assertEqual(len(run.calls), 1)

    def test_invalid_source_is_skipped_without_blocking_peers(self):
        """Bad readings never become online writes or unbind configured slots."""
        # Include converter limits, nonfinite values, unsupported units and self sources.
        for index in (1, 2, 3):
            for value, unit in (("unavailable", "°C"), ("unknown", "°C"), ("nan", "°C"),
                                ("inf", "°C"), ("20", "bad"), ("-0.1", "°C"),
                                ("100", "°C"), ("31", "°F"), ("273", "K")):
                with self.subTest(index=index, value=value, unit=unit):
                    run = mqtt_sources()
                    run.set_state(f"sensor.source{index}", value, unit)
                    run.fire("ha_started")
                    self.assertEqual([call["target"]["entity_id"] for call in run.calls],
                        [f"number.target_external_temperature_input_{peer}" for peer in (1, 2, 3) if peer != index])
            run = mqtt_sources()
            run.entity_map["target"].append(f"sensor.source{index}")
            run.fire("ha_started")
            self.assertEqual(len(run.calls), 2)

    def test_limits_and_recovery(self):
        """Exact converter bounds and a recovered source are sent normally."""
        # Fahrenheit and Kelvin limits are checked after conversion to Celsius.
        for value, unit, expected in (("0", "°C", 0), ("99.9", "°C", 99.9),
                                      ("32", "°F", 0), ("273.15", "K", 0)):
            run = mqtt_sources()
            run.set_state("sensor.source2", "unavailable")
            run.fire("source_changed", entity="sensor.source2", new_state=run.states["sensor.source2"])
            self.assertEqual(run.calls, [])
            recovered = run.set_state("sensor.source2", value, unit)
            run.dispatch_state("sensor.source2", None, recovered)
            self.assertEqual(run.calls[0]["data"], dict(value=expected))

    def test_missing_or_ambiguous_slot_entities_block_writes(self):
        """Do not partially synchronize an incompletely discovered three-slot device."""
        # Legacy entities are absent for the multi-source converter.
        for index in (1, 2, 3):
            for domain, suffix in (("number", ""), ("select", "_state")):
                for ambiguous in (False, True):
                    run = mqtt_sources()
                    entity = f"{domain}.target_external_temperature_input_{index}{suffix}"
                    if ambiguous:
                        run.entity_map["target"].append(entity.replace(".target_", ".duplicate_"))
                    else:
                        run.entity_map["target"].remove(entity)
                    run.fire("ha_started")
                    self.assertEqual(run.calls, [])

    def test_target_reports_and_unrelated_events_do_not_loop(self):
        """Echoes of number/state writes cannot trigger further synchronization."""
        # Only source inputs and startup/reload events authorize MQTT writes.
        run = mqtt_sources()
        for entity in run.entity_map["target"] + ["sensor.unrelated"]:
            run.dispatch_state(entity, None, dict(state="online"))
        self.assertEqual(run.calls, [])


if __name__ == "__main__":
    unittest.main()
