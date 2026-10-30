"""Behavior checks for target-temperature fan-out and unsupported valve handling."""

import unittest

from tools.blueprint_coverage import ROOT
from tools.blueprint_runner import BlueprintRunner, HandledServiceError


def fanout(source_integration="zha", targets=None):
    """Build explicit source and mixed supported/unsupported target device fixtures."""
    # Supported target routing is determined by the YAML, not by fixture filtering.
    targets = targets if targets is not None else ["zbl", "zbt", "trvzb", "mqtt", "foreign"]
    run = BlueprintRunner(ROOT / "automation/sonoff/trv_target_temperature_link_tp_wgzba.yaml",
                          dict(source_tp_wgzba="panel", target_trvs=targets))
    run.devices["panel"] = dict(manufacturer="SONOFF",
                                 model="TP-WGZBA" if source_integration == "zha" else "Zigbee thermostat panel",
                                 model_id="TP-WGZBA", identifiers=[(source_integration, "source-ieee")])
    run.entity_map["panel"] = ["sensor.panel_temperature", "climate.panel"]
    for device, integration, model, manufacturer in (
            ("zbl", "zha", "TRV-ZBL", "SONOFF"), ("zbt", "zha", "TRV-ZBT", "SONOFF"),
            ("trvzb", "zha", "TRVZB", "SONOFF"), ("mqtt", "mqtt", "TRV-ZBL", "SONOFF"),
            ("foreign", "zha", "TRV-ZBL", "OTHER")):
        run.devices[device] = dict(manufacturer=manufacturer, model=model, identifiers=[(integration, f"ieee-{device}")])
    return run


class TargetTemperatureTests(unittest.TestCase):
    """Verify target changes, supported destinations, boundary values, and logging."""

    def test_changed_target_forwards_supported_devices_and_logs_skips(self):
        """Forward to ZHA ZBL/ZBT only, preserving target order and encoded values."""
        # Source integration does not affect the selected climate event's payload.
        for integration in ("zha", "mqtt"):
            run = fanout(integration)
            old = run.set_state("climate.panel", "heat", temperature=19)
            new = run.set_state("climate.panel", "heat", temperature=21.5)
            run.dispatch_state("climate.panel", old, new)
            writes = [call for call in run.calls if call["action"] == "zha.set_zigbee_cluster_attribute"]
            self.assertEqual([call["data"]["ieee"] for call in writes], ["ieee-zbl", "ieee-zbt"])
            for call in writes:
                self.assertEqual(call["data"], dict(ieee=call["data"]["ieee"], endpoint_id=1,
                                 cluster_id=0xFC11, cluster_type="in", attribute=0xFF01, value=2150))
            logs = [call["data"] for call in run.calls if call["action"] == "system_log.write"]
            self.assertEqual([log["level"] for log in logs], ["info", "info", "warning", "warning", "warning"])
            self.assertIn("climate.panel", logs[0]["message"])
            self.assertIn("21.5", logs[0]["message"])
            for device, log in zip(("trvzb", "mqtt", "foreign"), logs[2:]):
                self.assertIn(device, log["message"])

    def test_temperature_bounds_rounding_and_empty_target_list(self):
        """Validate inclusive 5–30°C targets and centidegree rounding."""
        # Out-of-range targets are logged, not written to any valve.
        for temperature, expected in ((5, 500), (30, 3000), (21.456, 2146), (4.99, None), (30.01, None)):
            run = fanout(targets=["zbl"])
            run.fire("source_target_temperature_changed", entity="climate.panel",
                     old_state={"attributes": {"temperature": 19}},
                     new_state={"attributes": {"temperature": temperature}})
            writes = [call for call in run.calls if call["action"] == "zha.set_zigbee_cluster_attribute"]
            self.assertEqual([call["data"]["value"] for call in writes], [] if expected is None else [expected])
            self.assertEqual(run.calls[-1]["data"]["level"], "warning" if expected is None else "info")
        run = fanout(targets=[])
        run.fire("source_target_temperature_changed", entity="climate.panel",
                 old_state={"attributes": {"temperature": 19}}, new_state={"attributes": {"temperature": 20}})
        self.assertEqual(run.calls, [])

    def test_unchanged_missing_nonnumeric_and_unrelated_events_skip(self):
        """Reject changes that do not carry a new numeric target temperature."""
        # A room-temperature update or entity removal must not be forwarded.
        for entity, old, new in (
                ("sensor.unrelated", {"attributes": {"temperature": 19}}, {"attributes": {"temperature": 20}}),
                ("climate.panel", None, {"attributes": {"temperature": 20}}),
                ("climate.panel", {"attributes": {"temperature": 19}}, None),
                ("climate.panel", {"attributes": {"temperature": 20}}, {"attributes": {"temperature": 20}}),
                ("climate.panel", {"attributes": {"temperature": 19}}, {"attributes": {"temperature": "20"}}),
                ("climate.panel", {"attributes": {"temperature": 19}}, {"attributes": {"temperature": None}})):
            run = fanout()
            run.fire("source_target_temperature_changed", entity=entity, old_state=old, new_state=new)
            self.assertEqual(run.calls, [])
        run = fanout()
        run.entity_map["panel"] = ["sensor.panel_temperature"]
        run.fire("source_target_temperature_changed", entity="climate.panel",
                 old_state={"attributes": {"temperature": 19}}, new_state={"attributes": {"temperature": 20}})
        self.assertEqual(run.calls, [])

    def test_unknown_target_is_logged_without_aborting_other_targets(self):
        """A missing target identifier is skipped before processing a supported peer."""
        # Default logging is part of the actual choose action, not a test-side fallback.
        run = fanout(targets=["missing", "zbt"])
        run.fire("source_target_temperature_changed", entity="climate.panel",
                 old_state={"attributes": {"temperature": 19}}, new_state={"attributes": {"temperature": 20}})
        self.assertEqual([call["action"] for call in run.calls],
                         ["system_log.write", "zha.set_zigbee_cluster_attribute", "system_log.write"])
        self.assertIn("missing", run.calls[0]["data"]["message"])
        self.assertEqual(run.calls[1]["data"]["ieee"], "ieee-zbt")

    def test_service_error_stops_current_fanout_and_fresh_event_can_retry(self):
        """Do not silently claim later targets are attempted after an unhandled error."""
        # The current YAML has no per-target continue_on_error policy.
        run = fanout(targets=["zbl", "zbt"])
        run.fail.add(0xFF01)
        old, new = {"attributes": {"temperature": 19}}, {"attributes": {"temperature": 20}}
        with self.assertRaises(HandledServiceError):
            run.fire("source_target_temperature_changed", entity="climate.panel", old_state=old, new_state=new)
        self.assertEqual(len(run.calls), 1)
        run.fail.clear()
        run.calls.clear()
        run.fire("source_target_temperature_changed", entity="climate.panel", old_state=old, new_state=new)
        self.assertEqual([call["data"]["ieee"] for call in run.calls if call["action"].startswith("zha.")],
                         ["ieee-zbl", "ieee-zbt"])


if __name__ == "__main__":
    unittest.main()
