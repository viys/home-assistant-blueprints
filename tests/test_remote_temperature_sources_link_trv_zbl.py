"""Exercise the ZBL five-source blueprint against its ZHA handler contract."""

import unittest

from tools.blueprint_coverage import ROOT
from tools.blueprint_runner import BlueprintRunner


def sources(integration="zha", count=5):
    """Configure five independently addressable temperature sources."""
    inputs = {f"source_entity_{i}": f"sensor.source{i}" if i <= count else ""
              for i in range(1, 6)}
    run = BlueprintRunner(ROOT / "automation/sonoff/remote_temperature_sources_link_trv_zbl.yaml",
                          dict(target_device="target",
                               external_temperature_switch="switch.target_external_temperature_sensor",
                               external_temperature_input="number.target_external_temperature_input", **inputs))
    run.devices["target"] = dict(manufacturer="SONOFF", identifiers=[(integration, "00:11")],
                                  model="TRV-ZBL" if integration == "zha" else "Zigbee thermostatic radiator valve")
    run.entity_map["target"] = ["switch.target_external_temperature_sensor",
                                "select.target_temperature_sensor_select",
                                "number.target_external_temperature_input"]
    run.set_state("switch.target_external_temperature_sensor", "on")
    for i in range(1, 6):
        run.set_state(f"sensor.source{i}", 19 + i, "°C")
    return run


class ZblSourcesTests(unittest.TestCase):
    """Verify independent slots, invalidation, lifecycle sync, and MQTT fallback."""

    def test_explicit_localized_switch_enables_sync(self):
        """Localized or renamed switches must not silently block all writes."""
        run = sources(count=2)
        switch = "switch.sonoff_trv_zbl_wai_bu_wen_du_chuan_gan_qi"
        run.entity_map["target"][0] = switch
        run.inputs["external_temperature_switch"] = switch
        run.set_state(switch, "on")
        run.fire("ha_started")
        self.assertEqual(len(run.calls), 5)
        self.assertEqual([c["data"]["value"] for c in run.calls], [2000, 2100, -32768, -32768, -32768])
        run.calls.clear()
        run.dispatch_state(switch, {"state": "off"}, run.states[switch])
        self.assertEqual(len(run.calls), 5)
        run.calls.clear()
        run.set_state(switch, "off")
        run.fire("source_changed", entity="sensor.source1")
        self.assertEqual(run.calls, [])

    def test_explicit_switch_must_belong_to_target(self):
        """A selected switch from another device cannot enable synchronization."""
        run = sources()
        run.inputs["external_temperature_switch"] = "switch.other"
        run.set_state("switch.other", "on")
        run.fire("ha_started")
        self.assertEqual(run.calls, [])

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
                run.fire(trigger, entity="switch.target_external_temperature_sensor", new_state={"state": "on"})
                self.assertEqual([(c["data"]["attribute"], c["data"]["value"]) for c in run.calls],
                                 [(0xFF10 + i, (19 + i) * 100 if i <= count else -32768)
                                  for i in range(1, 6)])

    def test_invalid_removed_and_recovered_sources(self):
        """Bad readings clear only their own slot and a fresh value rebinds it."""
        for i in range(1, 6):
            for value, unit in (("unavailable", "°C"), ("unknown", "°C"), ("NaN", "°C"),
                                ("inf", "°C"), ("20", "bad"), ("100.01", "°C"), ("-30.01", "°C")):
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

    def test_boundaries_and_negative_rounding(self):
        """Enforce the firmware's usable range after unit conversion."""
        for value, unit, expected in (("-30", "°C", -3000), ("212", "°F", 10000),
                                      ("243.15", "K", -3000), ("-5.126", "°C", -513)):
            run = sources()
            new = run.set_state("sensor.source5", value, unit)
            run.dispatch_state("sensor.source5", None, new)
            self.assertEqual(run.calls[0]["data"]["value"], expected)

    def test_disabled_unrelated_and_wrong_devices_skip(self):
        """Only compatible enabled targets and relevant events may write."""
        run = sources()
        run.dispatch_state("sensor.other", None, {"state": "20"})
        run.dispatch_state("switch.target_external_temperature_sensor", {"state": "on"}, None)
        run.set_state("switch.target_external_temperature_sensor", "off")
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


if __name__ == "__main__":
    unittest.main()
