"""Test TRV-ZBL temperature synchronization and entity discovery."""

import unittest

from tools.blueprint_coverage import ROOT
from tools.blueprint_runner import BlueprintRunner


def sources(integration="zha", count=5):
    """Configure five independently addressable temperature sources."""
    inputs = {f"source_entity_{i}": f"sensor.source{i}" if i <= count else ""
              for i in range(1, 6)}
    run = BlueprintRunner(ROOT / "automation/sonoff/remote_temperature_link_trv_zbl.yaml",
                          dict(target_device="target",
                               **inputs))
    run.devices["target"] = dict(manufacturer="SONOFF", identifiers=[(integration, "00:11")],
                                  model="TRV-ZBL" if integration == "zha" else "Zigbee thermostatic radiator valve")
    run.entity_map["target"] = ["sensor.target_temperature_source_mode",
                                "select.target_temperature_sensor_select",
                                "number.target_external_temperature_input"]
    run.set_state("sensor.target_temperature_source_mode", "external_sensor", device_class="enum")
    for i in range(1, 6):
        run.set_state(f"sensor.source{i}", 19 + i, "°C")
    run.set_state("number.target_external_temperature_input", "20", "°C",
                  min=0, max=99.9, step=0.1)
    return run


class ZblSourcesTests(unittest.TestCase):
    """Verify independent slots, invalidation, lifecycle sync, and MQTT fallback."""

    def test_each_source_and_unit_routes_to_its_own_slot(self):
        """The valve receives individual centidegree values, not a gateway average."""
        for i in range(1, 6):
            for value, unit in (("20", "°C"), ("68", "°F"), ("293.15", "K")):
                with self.subTest(source=i, unit=unit):
                    run = sources()
                    entity = f"sensor.source{i}"
                    old = run.states[entity]
                    new = run.set_state(entity, value, unit)
                    run.dispatch_state(entity, old, new)
                    self.assertEqual(len(run.calls), 1)
                    self.assertEqual(run.calls[0]["data"], dict(ieee="00:11", endpoint_id=1,
                                     cluster_id=0xFC11, cluster_type="in", attribute=0xFF10 + i, value=2000))
                    self.assertEqual(run.calls[0]["action"], "zha.set_zigbee_cluster_attribute")

    def test_full_sync_and_empty_slots(self):
        """Startup, reload and enable restore sources and remove unused slots."""
        for count in range(1, 6):
            for trigger in ("ha_started", "automation_reloaded", "source_changed"):
                run = sources(count=count)
                run.fire(trigger, entity="sensor.target_temperature_source_mode", new_state={"state": "external_sensor"})
                self.assertEqual([(c["data"]["attribute"], c["data"]["value"]) for c in run.calls],
                                 [(0xFF10 + i, (19 + i) * 100 if i <= count else -32768)
                                  for i in range(1, 6)])

    def test_invalid_removed_and_recovered_sources(self):
        """Bad readings clear only their own slot and a fresh value rebinds it."""
        for i in range(1, 6):
            for value, unit in (("unavailable", "°C"), ("unknown", "°C"), ("NaN", "°C"),
                                ("inf", "°C"), ("20", "bad")):
                run = sources()
                entity = f"sensor.source{i}"
                new = run.set_state(entity, value, unit)
                run.dispatch_state(entity, None, new)
                self.assertEqual([(c["data"]["attribute"], c["data"]["value"]) for c in run.calls],
                                 [(0xFF10 + i, -32768)])
                run.calls.clear()
                run.dispatch_state(entity, new, run.set_state(entity, "21", "°C"))
                self.assertEqual(run.calls[0]["data"]["value"], 2100)
            run = sources()
            entity = f"sensor.source{i}"
            old = run.states.pop(entity)
            run.dispatch_state(entity, old, None)
            self.assertEqual(run.calls[0]["data"]["value"], -32768)

    def test_full_sync_keeps_valid_peers_and_rejects_duplicates_and_self(self):
        """Unavailable, duplicate and valve-local inputs cannot bias the mean."""
        run = sources()
        run.inputs["source_entity_2"] = "sensor.source1"
        run.entity_map["target"].append("sensor.source3")
        run.set_state("sensor.source4", "unavailable", "°C")
        run.fire("ha_started")
        self.assertEqual([c["data"]["value"] for c in run.calls], [2000, -32768, -32768, -32768, 2400])

    def test_conversion_and_negative_rounding(self):
        """Preserve unit conversion and centidegree rounding."""
        for value, unit, expected in (("-30", "°C", -3000), ("212", "°F", 10000),
                                      ("243.15", "K", -3000), ("-5.126", "°C", -513)):
            run = sources()
            new = run.set_state("sensor.source5", value, unit)
            run.dispatch_state("sensor.source5", None, new)
            self.assertEqual(run.calls[0]["data"]["value"], expected)

    def test_numeric_readings_are_forwarded_without_temperature_range_filter(self):
        """Forward abnormal numeric readings for the device to validate locally."""
        samples = (("-40", "°C", -40), ("-60", "°C", -60),
                   ("-76", "°F", -60), ("213.15", "K", -60),
                   ("-30.01", "°C", -30.01), ("100.01", "°C", 100.01))
        for integration in ("zha", "mqtt"):
            for i in (range(1, 6) if integration == "zha" else (1,)):
                for value, unit, celsius in samples:
                    with self.subTest(integration=integration, source=i, value=value, unit=unit):
                        run = sources(integration)
                        entity = f"sensor.source{i}"
                        new = run.set_state(entity, value, unit)
                        run.dispatch_state(entity, None, new)
                        if integration == "zha":
                            self.assertEqual(run.calls, [{
                                "action": "zha.set_zigbee_cluster_attribute",
                                "continue_on_error": True,
                                "data": dict(ieee="00:11", endpoint_id=1, cluster_id=0xFC11,
                                             cluster_type="in", attribute=0xFF10 + i,
                                             value=round(celsius * 100)),
                            }])
                        else:
                            self.assertEqual(len(run.calls), 1)
                            call = run.calls[0]
                            self.assertEqual(call["action"], "number.set_value")
                            self.assertEqual(call["target"],
                                             {"entity_id": "number.target_external_temperature_input"})
                            self.assertEqual(set(call["data"]), {"value"})
                            self.assertAlmostEqual(call["data"]["value"], celsius)

    def test_disabled_unrelated_and_wrong_devices_skip(self):
        """Only compatible enabled targets and relevant events may write."""
        run = sources()
        run.dispatch_state("sensor.other", None, {"state": "20"})
        run.dispatch_state("sensor.target_temperature_source_mode", {"state": "on"}, None)
        run.set_state("sensor.target_temperature_source_mode", "internal_sensor", device_class="enum")
        run.fire("ha_started")
        self.assertEqual(run.calls, [])
        for integration in ("zha", "mqtt"):
            for field, value in (("manufacturer", "OTHER"), ("model", "OTHER"), ("identifiers", [])):
                run = sources(integration)
                run.devices["target"][field] = value
                run.fire("source_changed", entity="sensor.source1")
                self.assertEqual(run.calls, [])
            run = sources(integration)
            run.entity_map["target"] = []
            run.fire("source_changed", entity="sensor.source1")
            self.assertEqual(run.calls, [])

    def test_mqtt_only_converts_source_one_updates(self):
        """MQTT retains the reference blueprint's single-source behavior."""
        for value, unit in (("20", "°C"), ("68", "°F"), ("293.15", "K")):
            run = sources("mqtt")
            new = run.set_state("sensor.source1", value, unit)
            run.dispatch_state("sensor.source1", None, new)
            self.assertEqual(run.calls, [{"action": "number.set_value",
                                         "target": {"entity_id": "number.target_external_temperature_input"},
                                         "data": {"value": 20}}])
        run = sources("mqtt")
        run.fire("ha_started")
        run.fire("automation_reloaded")
        for i in range(2, 6):
            run.fire("source_changed", entity=f"sensor.source{i}")
        run.set_state("sensor.source1", "unavailable")
        run.fire("source_changed", entity="sensor.source1")
        run.dispatch_state("select.target_temperature_sensor_select", None, {"state": "external"})
        self.assertEqual(run.calls, [])

    def test_failed_slot_does_not_block_other_sources(self):
        """An individual service error does not interrupt the remaining full sync."""
        run = sources()
        run.fail.add(0xFF12)
        run.fire("ha_started")
        self.assertEqual([c["data"]["attribute"] for c in run.calls], list(range(0xFF11, 0xFF16)))
        self.assertEqual(len(run.errors), 1)
        run.fail.clear()
        run.fire("source_changed", entity="sensor.source2")
        self.assertEqual(run.calls[-1]["data"]["value"], 2100)


class ZblEntitySelectionTests(unittest.TestCase):
    def instances(self, integration="zha"):
        yield sources(integration), "source_changed", "sensor.source1"

    def status(self, run, entity, value="external_sensor", **attrs):
        return run.set_state(entity, value, device_class="enum", **attrs)

    def test_real_ha_enum_state_without_options_enables_sync(self):
        """HA enum sensors publish device_class and state, but not options."""
        for run, trigger, source in self.instances():
            entity = "sensor.target_temperature_source_mode"
            run.set_state(entity, "external_sensor", device_class="enum")
            run.fire(trigger, entity=source)
            self.assertEqual(len(run.calls), 1, run.file.name)

    def test_localized_and_renamed_status_without_selection(self):
        for suffix in ("wen_du_lai_yuan", "temperaturquelle", "renamed_42"):
            for run, trigger, source in self.instances():
                with self.subTest(file=run.file.name, suffix=suffix):
                    entity = f"sensor.{suffix}"
                    run.entity_map["target"] = [entity]
                    self.status(run, entity, friendly_name="任意名称")
                    run.fire(trigger, entity=source)
                    self.assertEqual(run.calls[0]["data"]["value"], 2000)
                    run.calls.clear()
                    old = self.status(run, entity, "internal_sensor")
                    run.fire(trigger, entity=source)
                    self.assertEqual(run.calls, [])
                    run.dispatch_state(entity, old, self.status(run, entity))
                    self.assertEqual(len(run.calls), 5)

    def test_missing_foreign_ambiguous_unavailable_status_skips(self):
        for problem in ("missing", "foreign", "duplicate", "unavailable", "unknown", "wrong_state"):
            for run, trigger, source in self.instances():
                with self.subTest(file=run.file.name, problem=problem):
                    entity = "sensor.target_temperature_source_mode"
                    if problem in ("missing", "foreign"):
                        run.entity_map["target"].remove(entity)
                    elif problem == "duplicate":
                        run.entity_map["target"].append("sensor.duplicate")
                        self.status(run, "sensor.duplicate")
                    elif problem == "wrong_state":
                        run.set_state(entity, "other_mode", device_class="enum")
                    else:
                        self.status(run, entity, problem)
                    # A legacy switch selection/name must not bypass the status contract.
                    run.inputs["external_temperature_control"] = "switch.target_external_temperature_sensor"
                    run.set_state("switch.target_external_temperature_sensor", "on")
                    run.fire(trigger, entity=source)
                    self.assertEqual(run.calls, [])

    def test_mqtt_localized_input_is_discovered_without_selection(self):
        for suffix in ("wai_bu_wen_du", "externe_temperatur", "renamed_42"):
            for run, trigger, source in self.instances("mqtt"):
                entity = f"number.{suffix}"
                run.entity_map["target"] = [entity, "number.frost_temperature"]
                run.set_state(entity, "20", "°C", min=0, max=99.9, step=0.1)
                run.set_state("number.frost_temperature", "5", "°C", min=4, max=10, step=0.5)
                run.fire(trigger, entity=source)
                self.assertEqual(run.calls[0]["target"], {"entity_id": entity})
                self.assertEqual(run.calls[0]["data"]["value"], 20)

    def test_mqtt_missing_foreign_ambiguous_and_wrong_attributes_skip(self):
        for problem in ("missing", "foreign", "duplicate", "unit", "min", "max", "step", "domain"):
            for run, trigger, source in self.instances("mqtt"):
                with self.subTest(file=run.file.name, problem=problem):
                    entity = "number.target_external_temperature_input"
                    attrs = dict(min=0, max=99.9, step=0.1)
                    if problem in ("missing", "foreign"):
                        run.entity_map["target"] = []
                    elif problem == "duplicate":
                        run.entity_map["target"].append("number.duplicate")
                        run.set_state("number.duplicate", "20", "°C", **attrs)
                    elif problem == "domain":
                        run.entity_map["target"] = ["sensor.wrong_domain"]
                        run.set_state("sensor.wrong_domain", "20", "°C", **attrs)
                    else:
                        if problem in attrs:
                            attrs[problem] = 1
                        run.set_state(entity, "20", "°F" if problem == "unit" else "°C", **attrs)
                    # Old automation inputs cannot override automatic discovery.
                    run.inputs["external_temperature_control"] = entity
                    run.fire(trigger, entity=source)
                    self.assertEqual(run.calls, [])

    def test_control_selector_is_removed(self):
        for run, _, _ in self.instances():
            self.assertNotIn("external_temperature_control", run.doc["blueprint"]["input"])

if __name__ == "__main__":
    unittest.main()
