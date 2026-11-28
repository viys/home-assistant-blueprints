"""Offline contact aggregation and ZHA write checks for TP-WGZBA."""

from pathlib import Path
import unittest

from tests.common.entity_discovery import assert_entity_id_compatibility
from tools.blueprint_runner import BlueprintRunner


def door_link():
    """Bind the actual blueprint to two contacts and a selected ZHA panel."""
    # Register HA's is_state test locally; the shared runner supplies its action interface.
    contacts = ["binary_sensor.door", "binary_sensor.window"]
    run = BlueprintRunner(
        Path(__file__).resolve().parents[1] / "automation/sonoff/door_window_link_tp_wgzba.yaml",
        {"target_device": "panel", "contact_sensors": contacts},
    )
    run.env.tests["is_state"] = lambda entity, value: run.states(entity) == value
    run.devices["panel"] = {"identifiers": [("zha", "00:11:22:33:44:55:66:77")]}
    run.entity_map["contacts"] = contacts.copy()
    for entity in contacts:
        run.set_state(entity, "off")
    return run


class DoorWindowLinkTests(unittest.TestCase):
    """Verify aggregate transitions without modeling HA scheduling or radio delivery."""

    def transition(self, run, changes):
        """Admit only false-to-true edges of the blueprint's template triggers."""
        # Evaluate real trigger_variables and templates; fire() alone cannot test aggregation.
        scope = {}
        run.variables(run.doc["trigger_variables"], scope)
        triggers = [item for item in run.doc["triggers"] if item["trigger"] == "template"]
        before = [run.render(item["value_template"], scope) for item in triggers]
        for entity, value in changes.items():
            run.set_state(entity, value)
        for item, previous in zip(triggers, before):
            if not previous and run.render(item["value_template"], scope):
                run.fire(item["id"])

    def test_multiple_contacts_preserve_manual_exit_until_all_closed(self):
        """Do not resend open while another selected contact remains open."""
        # Additional openings and partial closures must not overwrite a panel manual exit.
        run = door_link()
        for changes in (
            {"binary_sensor.door": "on"},
            {"binary_sensor.window": "on"},
            {"binary_sensor.door": "off"},
            {"binary_sensor.window": "off"},
            {"binary_sensor.door": "on"},
        ):
            self.transition(run, changes)
        self.assertEqual([call["data"]["value"] for call in run.calls], [1, 0, 1])
        self.assertEqual(run.calls[0], {
            "action": "zha.set_zigbee_cluster_attribute",
            "data": {"ieee": "00:11:22:33:44:55:66:77", "endpoint_id": 1,
                     "cluster_id": 0xFC11, "cluster_type": "in", "attribute": 0x7F10,
                     "value": 1},
        })

    def test_invalid_contacts_never_count_as_closed(self):
        """Require every contact to be explicitly off before clearing the panel input."""
        # Missing and invalid states must follow the same fail-closed aggregation rule.
        for invalid in ("unknown", "unavailable", "invalid", None):
            with self.subTest(state=invalid):
                run = door_link()
                run.states.pop("binary_sensor.window")
                if invalid is not None:
                    run.set_state("binary_sensor.window", invalid)
                run.fire("startup")
                self.assertEqual(run.calls, [])
                self.transition(run, {"binary_sensor.door": "on"})
                self.transition(run, {"binary_sensor.door": "off"})
                self.assertEqual([call["data"]["value"] for call in run.calls], [1])
                self.transition(run, {"binary_sensor.window": "off"})
                self.assertEqual([call["data"]["value"] for call in run.calls], [1, 0])

    def test_recovered_open_contact_reapplies_open(self):
        """Recovery after all open contacts disappear produces a new aggregate open edge."""
        # Preserve the original recovery behavior even if a manual panel exit occurred.
        run = door_link()
        for value in ("on", "unavailable", "on"):
            self.transition(run, {"binary_sensor.door": value})
        self.assertEqual([call["data"]["value"] for call in run.calls], [1, 1])

    def test_startup_synchronizes_current_aggregate(self):
        """Send the known aggregate once on Home Assistant startup."""
        # An open contact wins over an unavailable peer; all-off clears the input.
        for door, window, expected in (("off", "off", 0), ("on", "off", 1),
                                       ("on", "unavailable", 1)):
            with self.subTest(door=door, window=window):
                run = door_link()
                run.set_state("binary_sensor.door", door)
                run.set_state("binary_sensor.window", window)
                run.fire("startup")
                self.assertEqual([call["data"]["value"] for call in run.calls], [expected])

    def test_stale_queued_events_are_discarded(self):
        """Recompute contact state before an admitted event writes to the panel."""
        # A queued open cannot overwrite newer closed state, and vice versa.
        run = door_link()
        run.fire("open")
        run.set_state("binary_sensor.door", "on")
        run.fire("closed")
        run.set_state("binary_sensor.door", "unavailable")
        run.fire("open")
        run.fire("closed")
        self.assertEqual(run.calls, [])

    def test_empty_selection_and_missing_zha_identifier_block_writes(self):
        """Reject unusable source selections and panel registry entries."""
        # Neither an empty aggregate nor a foreign integration provides a valid destination.
        for identifiers in (None, [], [("mqtt", "other")]):
            run = door_link()
            run.devices["panel"]["identifiers"] = identifiers
            run.fire("startup")
            self.assertEqual(run.calls, [])
        run = door_link()
        run.inputs["contact_sensors"] = []
        run.fire("startup")
        self.assertEqual(run.calls, [])

    def test_renamed_contacts_and_unselected_events(self):
        """Selected contact IDs can be numbered, localized, or renamed."""
        # Explicit selections must survive every naming variant and ignore unrelated sources.
        def exercise(run, entity_ids):
            """Open a selected contact after an unrelated contact changes."""
            # Rebind input IDs as HA does when creating an automation from its selectors.
            run.inputs["contact_sensors"] = list(entity_ids.values())
            self.transition(run, {"binary_sensor.unselected": "on"})
            self.assertEqual(run.calls, [])
            self.transition(run, {entity_ids["binary_sensor.door"]: "on"})

        assert_entity_id_compatibility(
            self, door_link, exercise, "contacts",
            expected_actions=["zha.set_zigbee_cluster_attribute"],
        )
