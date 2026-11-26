"""Reusable behavior checks for entity IDs that vary independently of device capabilities."""

NUMBERED_ENTITY_IDS = ("numbered_2", "numbered_3", "numbered_12")
LOCALIZED_ENTITY_IDS = ("zh_pinyin", "de", "fr", "renamed")


def _restore_entity_ids(value, reverse_mapping):
    """Restore exact entity-ID values in service data without chained substitution."""
    # Look up each string once so a restored slot ID cannot become another substitution's input.
    if isinstance(value, str):
        return reverse_mapping.get(value, value)
    if isinstance(value, list):
        return [_restore_entity_ids(item, reverse_mapping) for item in value]
    if isinstance(value, dict):
        return {key: _restore_entity_ids(item, reverse_mapping) for key, item in value.items()}
    return value


def assert_entity_id_compatibility(test_case, make_runner, exercise, device_id, *,
                                   expected_actions, variants=NUMBERED_ENTITY_IDS + LOCALIZED_ENTITY_IDS):
    """Compare service writes across naming variants using fresh runner fixtures.

    ``exercise(runner, entity_ids)`` receives the original-to-current ID mapping
    for the selected device, including an identity mapping for the baseline.
    Use that mapping when dispatching events from a renamed entity. Fixtures
    must use original IDs without HA conflict suffixes; functional slot indices
    are retained. Localized IDs are
    adversarial examples, not complete HA translation catalogs.
    """
    # Require actual baseline writes so broken discovery cannot pass by doing nothing in every case.
    test_case.assertTrue(expected_actions, "Declare the service actions this scenario must perform")
    variants = tuple(variants)
    test_case.assertTrue(variants, "Select at least one entity-ID compatibility variant")
    known_variants = NUMBERED_ENTITY_IDS + LOCALIZED_ENTITY_IDS
    for variant in variants:
        if variant not in known_variants:
            raise ValueError(f"Unknown entity-ID compatibility variant: {variant}")
    baseline = make_runner()
    original_ids = list(baseline.entity_map[device_id])
    test_case.assertTrue(original_ids, "The fixture must expose entities on the selected device")
    test_case.assertEqual(len(original_ids), len(set(original_ids)))
    exercise(baseline, {entity: entity for entity in original_ids})
    expected = [call for call in baseline.calls if call["action"] != "system_log.write"]
    test_case.assertEqual([call["action"] for call in expected], list(expected_actions),
                         "Baseline discovery did not perform the declared service actions")

    # These labels exercise name independence; raw enum states and capability attributes stay intact.
    labels = {"zh_pinyin": "wai_bu_wen_du_chuan_gan_qi", "de": "externer_temperatursensor",
              "fr": "capteur_de_temperature_externe", "renamed": "my_custom_control"}
    for variant in variants:
        with test_case.subTest(entity_id_variant=variant, device=device_id):
            runner = make_runner()
            test_case.assertEqual(runner.entity_map[device_id], original_ids,
                                  "Each naming case needs the same fresh fixture")
            mapping = {}
            for index, entity in enumerate(original_ids, 1):
                domain, _ = entity.split(".", 1)
                mapping[entity] = (entity + "_" + variant.split("_", 1)[1]
                                   if variant in NUMBERED_ENTITY_IDS
                                   else f"{domain}.test_device_{labels[variant]}_{index}")
            # Remove all old IDs first; a new ID may overlap a functional slot's old ID.
            moved_states = {entity: runner.states.pop(entity) for entity in original_ids
                            if entity in runner.states}
            for original, renamed in mapping.items():
                test_case.assertNotIn(renamed, runner.states)
                if original in moved_states:
                    runner.states[renamed] = moved_states[original]
            runner.entity_map[device_id] = [mapping[entity] for entity in original_ids]
            runner.fail = {mapping.get(entity, entity) for entity in runner.fail}
            exercise(runner, mapping)
            actual = [call for call in runner.calls if call["action"] != "system_log.write"]
            # Canonicalize exact entity-ID values only; destination, order, payload and counts must agree.
            reverse_mapping = {renamed: original for original, renamed in mapping.items()}
            test_case.assertEqual(_restore_entity_ids(actual, reverse_mapping), expected,
                                  f"Entity discovery or event handling depends on {variant} IDs")
