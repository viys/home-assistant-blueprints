"""Verify compatibility assertions reject ineffective tests and name-dependent discovery."""

from types import SimpleNamespace
import unittest

from tests.common.entity_discovery import assert_entity_id_compatibility


def fixture():
    """Create a small runner-shaped fixture with a foreign device and a raw enum state."""
    # No real blueprint behavior is duplicated here; these fixtures exercise the shared assertion itself.
    return SimpleNamespace(
        entity_map={"target": ["number.valve_external_temperature_input", "sensor.valve_mode"],
                    "foreign": ["number.foreign_control"]},
        states={"number.valve_external_temperature_input": {"state": "20", "min": 0},
                "sensor.valve_mode": {"state": "external_sensor", "device_class": "enum"},
                "number.foreign_control": {"state": "99"}}, calls=[], fail=set())


def write_by_domain(runner, entity_ids):
    """Emit an observable write while checking state and device isolation."""
    # The helper may rename IDs, but must not translate raw states or mutate unrelated devices.
    assert runner.states[entity_ids["sensor.valve_mode"]]["state"] == "external_sensor"
    assert runner.entity_map["foreign"] == ["number.foreign_control"]
    assert runner.states["number.foreign_control"]["state"] == "99"
    for original, renamed in entity_ids.items():
        if original != renamed:
            assert original not in runner.states
    entity = next(entity for entity in runner.entity_map["target"] if entity.startswith("number."))
    runner.calls.append({"action": "number.set_value", "target": {"entity_id": entity},
                         "data": {"value": int(runner.states[entity]["state"])}})


def write_by_english_suffix(runner, entity_ids):
    """Stand in for broken discovery that only accepts an English suffix."""
    # This deliberate defect must be caught by a localized naming case.
    if any(entity.endswith("_external_temperature_input") for entity in runner.entity_map["target"]):
        write_by_domain(runner, entity_ids)


def write_nothing(runner, entity_ids):
    """Stand in for a scenario that accidentally exercises no write behavior."""
    # Matching empty output in every naming case must not count as compatibility.
    runner.calls.append({"action": "system_log.write", "data": {"message": "skipped"}})


class EntityDiscoveryHelperTests(unittest.TestCase):
    """Check that failures in the shared compatibility tool remain visible."""

    def test_name_independent_writes_pass_all_variants(self):
        """Retain payloads, raw enum values, and device scope through every rename."""
        # The default suite includes Chinese pinyin, German, French, custom names and numeric suffixes.
        assert_entity_id_compatibility(self, fixture, write_by_domain, "target",
                                       expected_actions=["number.set_value"])

    def test_localization_check_catches_english_only_discovery(self):
        """An otherwise valid English baseline must fail after localized IDs replace it."""
        # An unbound TestCase propagates subtest assertions so the expected failure can be verified.
        with self.assertRaisesRegex(AssertionError, "zh_pinyin"):
            assert_entity_id_compatibility(unittest.TestCase(), fixture, write_by_english_suffix,
                                           "target", expected_actions=["number.set_value"],
                                           variants=("zh_pinyin",))

    def test_empty_baseline_is_rejected(self):
        """Do not falsely certify a blueprint that never reaches its intended write."""
        # A logging-only run is not a successful service-write scenario.
        with self.assertRaisesRegex(AssertionError, "Baseline discovery"):
            assert_entity_id_compatibility(unittest.TestCase(), fixture, write_nothing, "target",
                                           expected_actions=["number.set_value"])

    def test_numbering_check_catches_a_strict_suffix_matcher(self):
        """Require discovery to keep working when HA appends a conflict suffix."""
        # The same defective English matcher also demonstrates missing numeric-suffix support.
        with self.assertRaisesRegex(AssertionError, "numbered_12"):
            assert_entity_id_compatibility(unittest.TestCase(), fixture, write_by_english_suffix,
                                           "target", expected_actions=["number.set_value"],
                                           variants=("numbered_12",))

    def test_empty_matrix_is_rejected(self):
        """Require compatibility cases instead of silently testing only the baseline."""
        # An empty matrix must not certify localization or numbering support.
        with self.assertRaisesRegex(AssertionError, "at least one"):
            assert_entity_id_compatibility(self, fixture, write_by_domain, "target",
                                           expected_actions=["number.set_value"], variants=())

    def test_unknown_variant_is_rejected(self):
        """Do not silently ignore a misspelled compatibility case."""
        # Test authors must see invalid case names immediately.
        with self.assertRaisesRegex(ValueError, "Unknown entity-ID"):
            assert_entity_id_compatibility(self, fixture, write_by_domain, "target",
                                           expected_actions=["number.set_value"], variants=("typo",))

    def test_functional_slot_ids_can_overlap_old_ids_in_either_order(self):
        """Move slot states together and normalize renamed IDs without chained replacement."""
        # A functional _2 slot is not necessarily an HA conflict suffix.
        base = "number.valve_external_temperature_input"
        slot = base + "_2"
        for order in ((base, slot), (slot, base)):
            with self.subTest(order=order):
                def make_runner():
                    """Expose an unsuffixed control and a functional second slot."""
                    # Distinct values make state overwrite or alias corruption observable.
                    run = fixture()
                    run.entity_map["target"] = [*order, "sensor.valve_mode"]
                    run.states[slot] = {"state": "21", "min": 0}
                    return run

                def exercise(run, entity_ids):
                    """Write each number using its own state after discovery."""
                    # Compare both payloads and targets after the compatibility tool normalizes IDs.
                    for entity in run.entity_map["target"]:
                        if entity.startswith("number."):
                            run.calls.append({"action": "number.set_value", "target": {"entity_id": entity},
                                              "data": {"value": int(run.states[entity]["state"])}})

                assert_entity_id_compatibility(self, make_runner, exercise, "target",
                                               expected_actions=["number.set_value"] * 2,
                                               variants=("numbered_2",))

    def test_numbering_still_rejects_collisions_with_a_foreign_device(self):
        """Moving target states must not permit overwriting another device's entity."""
        # Only overlap with IDs being moved is valid; foreign destination IDs remain protected.
        def make_runner():
            """Place a numbered destination on an unrelated device."""
            # Preserve the original foreign fixture so baseline checks still exercise their contract.
            run = fixture()
            entity = "number.valve_external_temperature_input_2"
            run.entity_map["peer"] = [entity]
            run.states[entity] = {"state": "99"}
            return run

        with self.assertRaises(AssertionError):
            assert_entity_id_compatibility(unittest.TestCase(), make_runner, write_by_domain, "target",
                                           expected_actions=["number.set_value"], variants=("numbered_2",))
