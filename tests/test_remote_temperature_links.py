"""Behavior checks for the four single-source thermostat/TRV blueprints."""

import unittest

from tools.blueprint_coverage import ROOT
from tools.blueprint_runner import BlueprintRunner, HandledServiceError


CASES = (
    ("remote_temperature_link_tp_wgzba.yaml", "TP-WGZBA", "Zigbee thermostat panel", 0x7009),
    ("remote_temperature_link_trv_zbl.yaml", "TRV-ZBL", "Zigbee thermostatic radiator valve", 0xFF02),
    ("remote_temperature_link_trvzb.yaml", "TRVZB", "Zigbee thermostatic radiator valve", None),
    ("remote_temperature_link_trvzbt.yaml", "TRV-ZBT", "Zigbee thermostatic radiator valve", None),
)


def single_source(case, integration="zha"):
    """Configure a real blueprint with explicit target entities and source state."""
    # Shared fixture setup avoids four separate copies of the same execution model.
    file, model, mqtt_model, _ = case
    run = BlueprintRunner(ROOT / "automation/sonoff" / file,
                          dict(target_device="target", source_entity="sensor.source"))
    run.devices["target"] = dict(manufacturer="SONOFF", model=model if integration == "zha" else mqtt_model,
                                  model_id=model, identifiers=[(integration, "00:11")])
    run.entity_map["target"] = ["switch.target_external_temperature_sensor",
                                "number.target_external_temperature_sensor_value",
                                "select.target_temperature_sensor_select",
                                "number.target_external_temperature_input"]
    run.set_state("sensor.source", "20", "°C")
    run.set_state("switch.target_external_temperature_sensor", "on")
    run.set_state("select.target_temperature_sensor_select", "external")
    return run


class SingleSourceTests(unittest.TestCase):
    """Verify conversion, destination, mode gating, and invalid-event rejection."""

    def test_each_unit_and_integration_writes_expected_value(self):
        """Exercise every blueprint's supported unit and integration combinations."""
        # Assert full destination metadata, not just that some action executed.
        for case in CASES:
            for integration in ("zha", "mqtt"):
                for value, unit, celsius in (("20", "°C", 20), ("68", "°F", 20),
                                             ("293.15", "K", 20), ("-5", "°C", -5)):
                    with self.subTest(file=case[0], integration=integration, unit=unit, value=value):
                        run = single_source(case, integration)
                        run.set_state("sensor.source", value, unit)
                        run.fire("source_temperature")
                        self.assertEqual(len(run.calls), 1)
                        call = run.calls[0]
                        if integration == "zha" and case[3] is not None:
                            self.assertEqual(call["action"], "zha.set_zigbee_cluster_attribute")
                            self.assertEqual(call["data"], dict(ieee="00:11", endpoint_id=1,
                                             cluster_id=0xFC11, cluster_type="in",
                                             attribute=case[3], value=celsius * 100))
                        else:
                            suffix = "external_temperature_sensor_value" if integration == "zha" else "external_temperature_input"
                            self.assertEqual(call["action"], "number.set_value")
                            self.assertEqual(call["target"], {"entity_id": f"number.target_{suffix}"})
                            self.assertEqual(call["data"], {"value": celsius})

    def test_source_dispatch_sends_once_and_never_changes_sensor_selection(self):
        """A source change matches state/event listeners without duplicating writes."""
        # The broad mode listener must reject the same event as a mode change.
        for case in CASES:
            for integration in ("zha", "mqtt"):
                run = single_source(case, integration)
                old = run.states["sensor.source"]
                new = run.set_state("sensor.source", "21", "°C")
                run.dispatch_state("sensor.source", old, new)
                self.assertEqual(len(run.calls), 1, (case[0], integration))
                self.assertNotIn("select.select_option", [call["action"] for call in run.calls])

    def test_zha_mode_enable_resyncs_and_off_or_unrelated_events_skip(self):
        """ZHA mode enable syncs immediately, while off and unrelated events do not."""
        # Source data remains valid while event filtering is exercised independently.
        for case in CASES:
            run = single_source(case)
            switch = "switch.target_external_temperature_sensor"
            old = run.set_state(switch, "off")
            run.fire("source_temperature")
            self.assertEqual(run.calls, [])
            new = run.set_state(switch, "on")
            run.dispatch_state(switch, old, new)
            self.assertEqual(len(run.calls), 1, case[0])
            run.calls.clear()
            run.dispatch_state("sensor.unrelated", None, {"state": "on"})
            run.dispatch_state(switch, new, None)
            off = run.set_state(switch, "off")
            run.dispatch_state(switch, new, off)
            self.assertEqual(run.calls, [])

    def test_attribute_only_source_change_does_not_trigger_filtered_state_listener(self):
        """A not_to state trigger ignores unchanged values with changed attributes."""
        # Even a unit change must not fabricate a state-value trigger in this simulator.
        for case in CASES:
            for integration in ("zha", "mqtt"):
                run = single_source(case, integration)
                old = run.states["sensor.source"]
                new = run.set_state("sensor.source", "20", "°F")
                run.dispatch_state("sensor.source", old, new)
                self.assertEqual(run.calls, [], (case[0], integration))

    def test_mqtt_mode_event_does_not_sync_or_change_mode(self):
        """MQTT accepts source updates only; select-entity events remain unrelated."""
        # Current YAML does not command the source selector itself.
        for case in CASES:
            run = single_source(case, "mqtt")
            run.dispatch_state("select.target_temperature_sensor_select", {"state": "internal"}, {"state": "external"})
            self.assertEqual(run.calls, [])

    def test_invalid_sources_and_target_metadata_do_not_send(self):
        """Reject unavailable, nonnumeric, unsupported-unit, self, and wrong targets."""
        # NaN/infinity must not masquerade as valid numeric readings in the fixture.
        for case in CASES:
            for integration in ("zha", "mqtt"):
                for value, unit in (("unknown", "°C"), ("unavailable", "°C"), ("NaN", "°C"),
                                    ("inf", "°C"), ("text", "°C"), ("20", "bad")):
                    run = single_source(case, integration)
                    old = run.states["sensor.source"]
                    new = run.set_state("sensor.source", value, unit)
                    run.dispatch_state("sensor.source", old, new)
                    self.assertEqual(run.calls, [], (case[0], integration, value, unit))
                for field, value in (("manufacturer", "OTHER"), ("model", "OTHER"), ("identifiers", [])):
                    run = single_source(case, integration)
                    run.devices["target"][field] = value
                    run.fire("source_temperature")
                    self.assertEqual(run.calls, [])
                run = single_source(case, integration)
                run.entity_map["target"].append("sensor.source")
                run.fire("source_temperature")
                self.assertEqual(run.calls, [])
                run = single_source(case, integration)
                run.entity_map["target"] = []
                run.fire("source_temperature")
                self.assertEqual(run.calls, [])

    def test_trvzbt_accepts_alternative_zha_switch_name(self):
        """Support both selector-switch entity suffixes declared in the ZBT YAML."""
        # The fixture must not hard-code only the older switch naming pattern.
        run = single_source(CASES[3])
        run.entity_map["target"][0] = "switch.target_temperature_sensor_select"
        run.set_state("switch.target_temperature_sensor_select", "on")
        run.fire("source_temperature")
        self.assertEqual(run.calls[0]["data"]["value"], 20)

    def test_service_failure_propagates_and_fresh_run_can_send(self):
        """Document existing failure behavior without inventing retries or swallowing errors."""
        # These blueprints do not promise that a failed run is automatically retried.
        for case in CASES:
            for integration in ("zha", "mqtt"):
                run = single_source(case, integration)
                key = case[3] if integration == "zha" and case[3] else (
                    "number.target_external_temperature_sensor_value" if integration == "zha"
                    else "number.target_external_temperature_input")
                run.fail.add(key)
                with self.assertRaises(HandledServiceError):
                    run.fire("source_temperature")
                run.fail.clear()
                run.set_state("sensor.source", "22", "°C")
                run.fire("source_temperature")
                self.assertEqual(len(run.calls), 2)
                self.assertEqual(run.calls[-1]["data"]["value"], 2200 if integration == "zha" and case[3] else 22)


if __name__ == "__main__":
    unittest.main()
