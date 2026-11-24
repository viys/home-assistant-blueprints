"""Behavior checks for the TRVZB remote temperature blueprint."""

import unittest

from common.single_source_checks import SingleSourceChecks, single_source


class RemoteTemperatureTests(SingleSourceChecks, unittest.TestCase):
    """Run the shared single-source scenarios for this blueprint."""

    mqtt_mode_sync = True
    continue_on_error = True

    cases = (("remote_temperature_link_trvzb.yaml", "TRVZB",
              "Zigbee thermostatic radiator valve", None),)


class MultipleTargetTests(unittest.TestCase):
    """Exercise independent TRVZB destinations using the actual YAML loop."""

    def setUp(self):
        """Create one ZHA valve followed by a Zigbee2MQTT valve."""
        # Mixed integrations expose accidental reuse of the previous loop's entities.
        case = RemoteTemperatureTests.cases[0]
        self.run = single_source(case)
        peer = single_source(case, "mqtt")
        self.run.inputs["target_device"] = ["target", "peer", "target"]
        self.run.devices["peer"] = peer.devices["target"]
        self.run.entity_map["peer"] = [entity.replace("target_", "peer_")
                                       for entity in peer.entity_map["target"]]
        for entity in peer.entity_map["target"]:
            snapshot = peer.states[entity]
            if snapshot:
                self.run.set_state(entity.replace("target_", "peer_"), snapshot["state"],
                                   **snapshot["attributes"])

    def test_mixed_targets_deduplicate_and_convert_once(self):
        """Both integrations receive one converted reading per distinct valve."""
        # The duplicate ZHA selection must not cause a second write.
        self.run.set_state("sensor.source", "293.15", "K")
        self.run.fire("source_temperature")
        self.assertEqual([call["target"]["entity_id"] for call in self.run.calls],
                         ["number.target_external_temperature_sensor_value",
                          "number.peer_external_temperature_input"])
        self.assertEqual([call["data"]["value"] for call in self.run.calls], [20, 20])
        self.assertEqual(self.run.doc["mode"], "queued")
        self.assertTrue(self.run.doc["blueprint"]["input"]["target_device"]["selector"]["device"]["multiple"])

    def test_first_target_failure_or_invalidity_does_not_block_peer(self):
        """A failed, disabled, missing, unavailable, or wrong valve is isolated."""
        # Reset fixtures for each first-target failure to keep the peer healthy.
        for fault in ("failure", "off", "missing", "unavailable", "wrong_model"):
            self.setUp()
            if fault == "failure":
                self.run.fail.add("number.target_external_temperature_sensor_value")
            elif fault == "off":
                self.run.set_state("switch.target_external_temperature_sensor", "off")
            elif fault == "missing":
                self.run.entity_map["target"] = []
            elif fault == "unavailable":
                self.run.set_state("number.target_external_temperature_sensor_value", "unavailable")
            else:
                self.run.devices["target"]["model"] = "OTHER"
            self.run.fire("source_temperature")
            self.assertEqual(self.run.calls[-1]["target"]["entity_id"],
                             "number.peer_external_temperature_input", fault)
            self.assertEqual(len(self.run.errors), int(fault == "failure"))

    def test_mode_enable_and_destination_recovery_only_update_affected_valve(self):
        """Mode changes and restored destinations target only their owner."""
        # Ordinary numeric echoes, removal, and attribute updates must not resync.
        for entity, before, after in (
            ("select.peer_temperature_sensor_select", "internal", "external"),
            ("number.peer_external_temperature_input", "unavailable", "20"),
            ("number.target_external_temperature_sensor_value", "unknown", "20"),
        ):
            self.run.calls.clear()
            old = self.run.set_state(entity, before)
            new = self.run.set_state(entity, after)
            self.run.dispatch_state(entity, old, new)
            self.assertEqual(len(self.run.calls), 1, entity)
            self.assertEqual(self.run.calls[0]["target"]["entity_id"],
                             "number.target_external_temperature_sensor_value"
                             if "target_" in entity else "number.peer_external_temperature_input")
        self.run.calls.clear()
        for entity, before, after in (
            ("number.peer_external_temperature_input", {"state": "20"}, {"state": "21"}),
            ("select.peer_temperature_sensor_select", {"state": "external"}, {"state": "external"}),
            ("select.peer_temperature_sensor_select", {"state": "external"}, None),
            ("sensor.unrelated", None, {"state": "on"}),
        ):
            self.run.dispatch_state(entity, before, after)
        self.assertEqual(self.run.calls, [])

    def test_startup_reload_and_empty_selection(self):
        """Startup/reload reach both targets; an empty selection performs no writes."""
        # Existing scalar configurations remain covered by RemoteTemperatureTests.
        for trigger in ("ha_started", "automation_reloaded"):
            self.run.calls.clear()
            self.run.fire(trigger)
            self.assertEqual(len(self.run.calls), 2)
        self.run.inputs["target_device"] = []
        self.run.calls.clear()
        self.run.fire("source_temperature")
        self.assertEqual(self.run.calls, [])

    def test_any_selected_valves_temperature_is_rejected_for_whole_group(self):
        """Prevent a selected valve's measured temperature feeding the room group."""
        # Reject the second valve's source even while processing the first valve.
        self.run.entity_map["peer"].append("sensor.source")
        self.run.fire("source_temperature")
        self.assertEqual(self.run.calls, [])

    def test_next_target_mode_is_checked_after_previous_write(self):
        """A valve switched to internal mode during dispatch must not receive a write."""
        # Service hooks model state changes between loop iterations, not HA scheduling.
        def switch_peer_to_internal(run, call):
            """Change the pending valve's mode after the first service call."""
            # A queued run must not rely on mode snapshots from trigger time.
            run.set_state("select.peer_temperature_sensor_select", "internal")

        self.run.hook = switch_peer_to_internal
        self.run.fire("source_temperature")
        self.assertEqual(len(self.run.calls), 1)

    def test_numbered_same_model_targets_receive_updates_and_recovery(self):
        """HA duplicate-name suffixes must not hide any selected valve or its events."""
        # Reproduce same-name devices: only the appended entity number differs.
        for integration in ("zha", "mqtt"):
            for suffix in ("_2", "_3", "_12"):
                with self.subTest(integration=integration, suffix=suffix):
                    run = single_source(RemoteTemperatureTests.cases[0], integration)
                    run.inputs["target_device"] = ["target", "peer"]
                    run.devices["peer"] = dict(run.devices["target"])
                    run.entity_map["peer"] = [entity + suffix for entity in run.entity_map["target"]]
                    for entity in run.entity_map["target"]:
                        snapshot = run.states[entity]
                        if snapshot:
                            run.set_state(entity + suffix, snapshot["state"], **snapshot["attributes"])
                    destination = ("number.target_external_temperature_sensor_value" if integration == "zha"
                                   else "number.target_external_temperature_input")
                    run.fire("source_temperature")
                    self.assertEqual([call["target"]["entity_id"] for call in run.calls],
                                     [destination, destination + suffix])
                    self.assertEqual([call["data"]["value"] for call in run.calls], [20, 20])
                    run.calls.clear()
                    run.fail.add(destination)
                    run.fire("source_temperature")
                    self.assertEqual(run.calls[-1]["target"]["entity_id"], destination + suffix)
                    self.assertEqual(len(run.errors), 1)
                    run.calls.clear()
                    mode = ("switch.target_external_temperature_sensor" if integration == "zha"
                            else "select.target_temperature_sensor_select") + suffix
                    enabled = run.states(mode)
                    old = run.set_state(mode, "off" if integration == "zha" else "internal")
                    new = run.set_state(mode, enabled)
                    run.dispatch_state(mode, old, new)
                    self.assertEqual([call["target"]["entity_id"] for call in run.calls], [destination + suffix])
                    run.calls.clear()
                    old = run.set_state(destination + suffix, "unavailable")
                    new = run.set_state(destination + suffix, "20", "°C")
                    run.dispatch_state(destination + suffix, old, new)
                    self.assertEqual([call["target"]["entity_id"] for call in run.calls], [destination + suffix])
                    run.calls.clear()
                    newer = run.set_state(destination + suffix, "23", "°C")
                    run.dispatch_state(destination + suffix, new, newer)
                    self.assertEqual(run.calls, [])
