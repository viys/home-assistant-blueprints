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
    run.entity_map["target"] = ["switch.target_external_temperature_sensor",
                                "select.target_temperature_sensor_select",
                                "number.target_external_temperature_input"]
    run.set_state("switch.target_external_temperature_sensor", "on")
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
            run.fire(trigger, entity="switch.target_external_temperature_sensor", new_state={"state": "on"})
            self.assertEqual([(call["data"]["attribute"], call["data"]["value"]) for call in run.calls],
                             [(0xFF11, 2000), (0xFF12, 2100), (0xFF13, 2200)])

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
        """MQTT has no multi-slot or startup/full-sync behavior in this blueprint."""
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
        run.set_state("switch.target_external_temperature_sensor", "off")
        run.fire("source_changed", entity="sensor.source1", new_state=run.states["sensor.source1"])
        self.assertEqual(run.calls, [])
        run = sources()
        run.fire("source_changed", entity="sensor.unrelated", new_state={"state": "on"})
        run.fire("source_changed", entity="switch.target_external_temperature_sensor", new_state=None)
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


if __name__ == "__main__":
    unittest.main()
