"""Behavior checks for target-temperature fan-out and unsupported valve handling."""

import unittest

from tests.common.entity_discovery import NUMBERED_ENTITY_IDS, assert_entity_id_compatibility
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
    run.entity_map["trvzb"] = ["switch.valve_panel_target_temperature_linkage",
                                "number.valve_panel_linked_target_temperature"]
    run.set_state("switch.valve_panel_target_temperature_linkage", "on")
    return run


class TargetTemperatureTests(unittest.TestCase):
    """Verify target changes, supported destinations, boundary values, and logging."""

    def test_changed_target_forwards_supported_devices_and_logs_skips(self):
        """Forward to all supported ZHA models with their respective write paths."""
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
            self.assertEqual([log["level"] for log in logs], ["info", "info", "info", "warning", "warning"])
            numbers = [call for call in run.calls if call["action"] == "number.set_value"]
            self.assertEqual(len(numbers), 1)
            self.assertEqual(numbers[0]["target"]["entity_id"], "number.valve_panel_linked_target_temperature")
            self.assertEqual(numbers[0]["data"]["value"], 21.5)
            self.assertIn("climate.panel", logs[0]["message"])
            self.assertIn("21.5", logs[0]["message"])
            for device, log in zip(("mqtt", "foreign"), logs[3:]):
                self.assertIn(device, log["message"])

    def test_trvzb_names_bounds_and_linkage_gate(self):
        """Use old/new numbered names; never send a target to disabled linkage."""
        for switch, number in (
                ("switch.room_panel_target_temperature_linkage", "number.room_panel_linked_target_temperature"),
                ("switch.room_panel_linkage_2", "number.room_panel_linkage_target_temperature_2")):
            for state, temperature, expected in (("on", 5, True), ("on", 30, True),
                                                  ("on", 4.9, False), ("on", 30.1, False),
                                                  ("off", 20, False), ("unavailable", 20, False)):
                with self.subTest(switch=switch, state=state, temperature=temperature):
                    run = fanout(targets=["trvzb"])
                    run.entity_map["trvzb"] = [switch, number]
                    run.set_state(switch, state)
                    run.fire("source_target_temperature_changed", entity="climate.panel",
                             old_state={"attributes": {"temperature": 19}},
                             new_state={"attributes": {"temperature": temperature}})
                    writes = [call for call in run.calls if call["action"] == "number.set_value"]
                    self.assertEqual(len(writes), int(expected))
                    if expected:
                        self.assertEqual(writes[0]["target"]["entity_id"], number)
                        self.assertEqual(writes[0]["data"]["value"], temperature)

    def test_trvzb_missing_ambiguous_entities_and_mqtt_are_skipped(self):
        """Fail closed on ambiguous discovery and unsupported MQTT TRVZB targets."""
        for entities, integration in (([], "zha"),
                (["switch.a_panel_linkage", "number.a_panel_linked_target_temperature",
                  "number.b_panel_linked_target_temperature"], "zha"),
                (["switch.valve_panel_target_temperature_linkage",
                  "number.valve_panel_linked_target_temperature"], "mqtt")):
            run = fanout(targets=["trvzb", "zbt"])
            run.entity_map["trvzb"] = entities
            run.devices["trvzb"]["identifiers"] = [(integration, "ieee-trvzb")]
            run.set_state("switch.a_panel_linkage", "on")
            run.fire("source_target_temperature_changed", entity="climate.panel",
                     old_state={"attributes": {"temperature": 19}},
                     new_state={"attributes": {"temperature": 20}})
            self.assertFalse(any(call["action"] == "number.set_value" for call in run.calls))
            self.assertEqual(run.calls[0]["data"]["level"], "warning")
            self.assertEqual(run.calls[1]["data"]["ieee"], "ieee-zbt")

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

    def test_half_hour_refresh_forwards_current_frost_target_only_while_off(self):
        """Resend the current frost target on each timer tick for an Off panel."""
        # A repeated value must still reach every supported valve to renew linkage.
        for integration, frost in (("zha", "number.panel_frost_proof_temperature_2"),
                                   ("mqtt", "number.panel_frost_protection_temperature_12")):
            run = fanout(integration, targets=["zbl", "zbt", "trvzb"])
            run.entity_map["panel"].append(frost)
            run.set_state("climate.panel", "off", temperature=None)
            run.set_state(frost, 7.5)
            for expected in (7.5, 7.5, 8):
                run.calls.clear()
                run.set_state(frost, expected)
                run.fire("off_target_temperature_refresh")
                writes = [call for call in run.calls if call["action"] == "zha.set_zigbee_cluster_attribute"]
                self.assertEqual([call["data"]["value"] for call in writes], [expected * 100] * 2)
                self.assertEqual([call["data"]["value"] for call in run.calls
                                  if call["action"] == "number.set_value"], [expected])
            run.calls.clear()
            run.set_state("climate.panel", "heat", temperature=20)
            run.fire("off_target_temperature_refresh")
            self.assertEqual(run.calls, [])

    def test_half_hour_refresh_skips_non_off_unknown_and_missing_panels(self):
        """Never issue timer-driven writes unless the selected panel is explicitly Off."""
        # Another panel being Off must not enable this automation's periodic sends.
        for mode in ("heat", "auto", "cool", "unknown", "unavailable", None):
            run = fanout()
            if mode is not None:
                run.set_state("climate.panel", mode, temperature=20)
            run.set_state("climate.other_panel", "off")
            run.fire("off_target_temperature_refresh")
            self.assertEqual(run.calls, [])
        run = fanout()
        run.entity_map["panel"] = []
        run.set_state("climate.panel", "off")
        run.fire("off_target_temperature_refresh")
        self.assertEqual(run.calls, [])

    def test_half_hour_refresh_invalid_frost_and_disabled_linkage_never_write(self):
        """Preserve existing frost-source validation and the TRVZB enable gate."""
        # No extra diagnostic entity or cached climate target may substitute for frost data.
        frost = "number.panel_frost_proof_temperature"
        for entities, value in (([], 5), ([frost, "number.other_frost_proof_temperature"], 5),
                                ([frost], "unavailable"), ([frost], "unknown"), ([frost], "nan")):
            run = fanout(targets=["trvzb"])
            run.entity_map["panel"].extend(entities)
            run.set_state("climate.panel", "off", temperature=20)
            run.set_state(frost, value)
            run.fire("off_target_temperature_refresh")
            self.assertEqual([call["action"] for call in run.calls], ["system_log.write"])
            self.assertEqual(run.calls[0]["data"]["level"], "warning")
        run = fanout(targets=["trvzb", "zbt"])
        run.entity_map["panel"].append(frost)
        run.set_state(frost, 5)
        run.set_state("climate.panel", "off")
        run.set_state("switch.valve_panel_target_temperature_linkage", "off")
        run.fire("off_target_temperature_refresh")
        self.assertFalse(any(call["action"] == "number.set_value" for call in run.calls))
        self.assertEqual([call["data"]["value"] for call in run.calls
                          if call["action"] == "zha.set_zigbee_cluster_attribute"], [500])

    def test_entering_off_forwards_panel_frost_temperature(self):
        """Use the selected panel's frost setting even when its climate target becomes None."""
        # ZHA and MQTT use different frost entity names; duplicate devices add numeric suffixes.
        for integration, frost in (
                ("zha", "number.panel_frost_proof_temperature_2"),
                ("mqtt", "number.panel_frost_protection_temperature_12")):
            with self.subTest(integration=integration):
                run = fanout(integration, targets=["zbl", "zbt", "trvzb"])
                run.entity_map["panel"].append(frost)
                run.set_state(frost, 7.5, unit="°C")
                old = run.set_state("climate.panel", "heat", temperature=6)
                new = run.set_state("climate.panel", "off", temperature=None)
                run.dispatch_state("climate.panel", old, new)
                writes = [call for call in run.calls if call["action"].startswith("zha.")]
                self.assertEqual([call["data"]["value"] for call in writes], [750, 750])
                numbers = [call for call in run.calls if call["action"] == "number.set_value"]
                self.assertEqual([call["data"]["value"] for call in numbers], [7.5])

    def test_off_forwarding_supports_numbered_source_and_target_entities(self):
        """Apply shared numbering checks to both panel discovery and TRVZB linkage controls."""
        # These custom controls use fallback English names today; this test claims numbering support only.
        for integration in ("zha", "mqtt"):
            def make_runner():
                """Create an independent fixture with the integration's frost-control name."""
                # Both factories preserve the chosen source device and target linkage setup.
                run = fanout(integration, targets=["trvzb"])
                frost = ("number.panel_frost_proof_temperature" if integration == "zha"
                         else "number.panel_frost_protection_temperature")
                run.entity_map["panel"].append(frost)
                run.set_state(frost, 7.5)
                return run

            def exercise(run, entity_ids):
                """Dispatch Off using the possibly renamed source climate entity."""
                # Target-only renames leave the panel climate ID unchanged.
                climate = entity_ids.get("climate.panel", "climate.panel")
                old = run.set_state(climate, "heat", temperature=6)
                new = run.set_state(climate, "off", temperature=None)
                run.dispatch_state(climate, old, new)

            for device in ("panel", "trvzb"):
                with self.subTest(integration=integration, device=device):
                    assert_entity_id_compatibility(self, make_runner, exercise, device,
                                                   expected_actions=["number.set_value"],
                                                   variants=NUMBERED_ENTITY_IDS)

    def test_frost_changes_forward_only_while_panel_is_off(self):
        """Follow changed frost settings in Off without forwarding echoes or room readings."""
        # The entity state is a numeric string rather than a climate temperature attribute.
        run = fanout(targets=["trvzb"])
        frost = "number.panel_frost_proof_temperature"
        run.entity_map["panel"].append(frost)
        run.set_state("climate.panel", "off", temperature=None)
        old = run.set_state(frost, 5)
        new = run.set_state(frost, 10)
        run.dispatch_state(frost, old, new)
        self.assertEqual(run.calls[0]["data"]["value"], 10)
        run.calls.clear()
        run.dispatch_state(frost, new, new)
        off = run.states["climate.panel"]
        run.dispatch_state("climate.panel", off, run.set_state("climate.panel", "off", temperature=5))
        self.assertEqual(run.calls, [])
        run.set_state("climate.panel", "heat", temperature=20)
        run.dispatch_state(frost, new, run.set_state(frost, 12))
        self.assertEqual(run.calls, [])

    def test_off_missing_ambiguous_and_invalid_frost_settings_are_logged(self):
        """Never invent a fallback temperature when the panel frost setting cannot be used."""
        # Only entities belonging to the chosen source device can supply frost settings.
        frost = "number.panel_frost_proof_temperature"
        for entities, value in (([], 5), ([frost, "number.other_frost_proof_temperature"], 5),
                                ([frost], "unavailable"), ([frost], "unknown"), ([frost], "nan")):
            with self.subTest(entities=entities, value=value):
                run = fanout(targets=["trvzb"])
                run.entity_map["panel"].extend(entities)
                run.set_state(frost, value)
                old = run.set_state("climate.panel", "heat", temperature=20)
                new = run.set_state("climate.panel", "off", temperature=None)
                run.dispatch_state("climate.panel", old, new)
                self.assertEqual([call["action"] for call in run.calls], ["system_log.write"])
                self.assertEqual(run.calls[0]["data"]["level"], "warning")
                self.assertIn("frost", run.calls[0]["data"]["message"])

    def test_leaving_off_uses_climate_target_and_initial_states_do_not_forward(self):
        """Restore normal target forwarding on Heat without sending on entity creation."""
        # A stale frost setting must not override a fresh non-Off climate target.
        run = fanout(targets=["trvzb"])
        frost = "number.panel_frost_proof_temperature"
        run.entity_map["panel"].append(frost)
        run.set_state(frost, 5)
        off = run.set_state("climate.panel", "off", temperature=None)
        run.dispatch_state("climate.panel", None, off)
        run.dispatch_state(frost, None, run.states[frost])
        self.assertEqual(run.calls, [])
        run.dispatch_state("climate.panel", off, run.set_state("climate.panel", "heat", temperature=20))
        self.assertEqual(run.calls[0]["data"]["value"], 20)

    def test_leaving_off_resends_an_unchanged_climate_target(self):
        """Replace the frost target even when an MQTT climate retains its setpoint while Off."""
        # Mode changes switch the effective source even if the temperature attribute is unchanged.
        run = fanout("mqtt", targets=["trvzb"])
        run.entity_map["panel"].append("number.panel_frost_protection_temperature")
        run.set_state("number.panel_frost_protection_temperature", 5)
        old = run.set_state("climate.panel", "off", temperature=20)
        new = run.set_state("climate.panel", "heat", temperature=20)
        run.dispatch_state("climate.panel", old, new)
        self.assertEqual(run.calls[0]["data"]["value"], 20)

    def test_unknown_and_unavailable_climate_states_never_forward_cached_targets(self):
        """Do not treat a panel availability change as leaving Off for a working mode."""
        # Climate entities can retain numeric temperature attributes while unavailable.
        for integration in ("zha", "mqtt"):
            for previous_mode in ("off", "heat"):
                for next_mode in ("unknown", "unavailable"):
                    for temperature in (20, 21):
                        with self.subTest(integration=integration, previous=previous_mode,
                                          next=next_mode, temperature=temperature):
                            run = fanout(integration, targets=["zbl", "zbt", "trvzb"])
                            old = run.set_state("climate.panel", previous_mode, temperature=20)
                            new = run.set_state("climate.panel", next_mode, temperature=temperature)
                            run.dispatch_state("climate.panel", old, new)
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
