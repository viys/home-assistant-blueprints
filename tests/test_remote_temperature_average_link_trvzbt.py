"""Offline behavior checks for TRV-ZBT source averaging and firmware-managed recovery."""

from datetime import timedelta
import unittest

from tests.common.single_source_checks import single_source


def average_runner(integration="zha", sources=None):
    """Bind the TRV-ZBT average blueprint to explicit source and destination entities."""
    # Reuse the single-source device fixture without changing existing blueprints.
    run = single_source(("remote_temperature_average_link_trvzbt.yaml", "TRV-ZBT",
                         "Zigbee thermostatic radiator valve", None), integration)
    run.inputs["source_entities"] = sources if sources is not None else ["sensor.source", "sensor.second"]
    run.set_state("sensor.second", "24", "°C")
    if integration == "mqtt":
        run.set_state("select.target_temperature_sensor_select", "remote_temperature")
    return run


class AverageTemperatureTests(unittest.TestCase):
    """Verify source membership, freshness, mode gating, and service destinations."""

    def test_mixed_units_average_before_rounding_and_use_correct_number(self):
        """Both integrations receive the same Celsius average at one decimal place."""
        # Average 20, 24, and 21 Celsius; round only the final result.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration, ["sensor.source", "sensor.second", "sensor.third"])
            run.set_state("sensor.source", "68", "°F")
            run.set_state("sensor.second", "297.15", "K")
            run.set_state("sensor.third", "21", "°C")
            run.fire("periodic_sync")
            suffix = "external_temperature_sensor_value" if integration == "zha" else "external_temperature_input"
            self.assertEqual(run.calls, [{"action": "number.set_value", "continue_on_error": True,
                                         "target": {"entity_id": f"number.target_{suffix}"},
                                         "data": {"value": 21.7}}])

    def test_four_sources_dedupe_self_exclusion_and_middle_removal_on_reload(self):
        """Removing a middle source cannot leave a slot or its old value in the mean."""
        # Removed source updates must no longer trigger this automation.
        for integration in ("zha", "mqtt"):
            sources = ["sensor.source", "sensor.second", "sensor.third", "sensor.fourth"]
            run = average_runner(integration, sources + ["sensor.source", "sensor.self"])
            run.set_state("sensor.third", "28", "°C")
            run.set_state("sensor.fourth", "32", "°C")
            run.set_state("sensor.self", "80", "°C")
            run.entity_map["target"].append("sensor.self")
            run.fire("automation_reloaded")
            self.assertEqual(run.calls[-1]["data"]["value"], 26)
            run.inputs["source_entities"] = [sources[0], sources[2], sources[3]]
            run.fire("automation_reloaded")
            self.assertEqual(run.calls[-1]["data"]["value"], 26.7)
            run.calls.clear()
            old = run.states["sensor.second"]
            new = run.set_state("sensor.second", "50", "°C")
            run.dispatch_state("sensor.second", old, new)
            self.assertEqual(run.calls, [])

    def test_expiration_is_independent_and_recovered_source_rejoins(self):
        """Drop only the expired source and resume using it after a value change."""
        # Reaching the configured boundary excludes a source even without a state event.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration)
            run.inputs["source_timeout"] = 10
            run.states["sensor.source"]["last_changed"] = run.clock - timedelta(minutes=10)
            run.fire("periodic_sync")
            self.assertEqual(run.calls[-1]["data"]["value"], 24)
            old = run.states["sensor.source"]
            new = run.set_state("sensor.source", "22", "°C")
            run.dispatch_state("sensor.source", old, new)
            self.assertEqual(run.calls[-1]["data"]["value"], 23)

    def test_all_invalid_or_expired_sources_stop_without_writing_mode(self):
        """Let firmware handle receiver timeout instead of sending zero or disabling it."""
        # Reload and startup must not revive expired data; missing and empty inputs stop.
        for integration in ("zha", "mqtt"):
            for state in ("unavailable", "unknown"):
                run = average_runner(integration)
                for source in run.inputs["source_entities"]:
                    run.set_state(source, state, "°C")
                run.fire("source_changed")
                self.assertEqual(run.calls, [])
            run = average_runner(integration)
            run.clock += timedelta(minutes=61)
            for trigger in ("ha_started", "automation_reloaded", "periodic_sync"):
                run.fire(trigger)
            self.assertEqual(run.calls, [])
            run.inputs["source_entities"] = ["sensor.deleted"]
            run.fire("periodic_sync")
            run.inputs["source_entities"] = []
            run.fire("periodic_sync")
            self.assertEqual(run.calls, [])

    def test_invalid_source_does_not_block_valid_peer(self):
        """Exclude nonnumeric, nonfinite, missing, and unsupported-unit sources."""
        # An unavailable transition must recalculate immediately with the remaining peer.
        for integration in ("zha", "mqtt"):
            for value, unit in (("unavailable", "°C"), ("unknown", "°C"), ("bad", "°C"),
                                ("nan", "°C"), ("inf", "°C"), ("20", "bad")):
                run = average_runner(integration)
                old = run.states["sensor.source"]
                new = run.set_state("sensor.source", value, unit)
                run.dispatch_state("sensor.source", old, new)
                self.assertEqual(len(run.calls), 1)
                self.assertEqual(run.calls[0]["data"]["value"], 24)
            run = average_runner(integration)
            del run.states["sensor.source"]
            run.fire("periodic_sync")
            self.assertEqual(run.calls[0]["data"]["value"], 24)

    def test_same_values_and_attributes_do_not_extend_source_validity(self):
        """Receiver refreshes and repeated source states cannot reset last_changed."""
        # The accepted constant-temperature expiry policy applies to both integrations.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration, ["sensor.source"])
            changed = run.states["sensor.source"]["last_changed"]
            for trigger in ("ha_started", "automation_reloaded", "periodic_sync"):
                run.fire(trigger)
            self.assertEqual(len(run.calls), 3)
            self.assertEqual(run.states["sensor.source"]["last_changed"], changed)
            run.calls.clear()
            run.clock += timedelta(minutes=61)
            run.set_state("sensor.source", "20", "°C", battery=90)
            run.fire("source_changed")
            self.assertEqual(run.calls, [])

    def test_timeout_configuration_and_two_hour_boundary(self):
        """All sources share a 1..120 minute input with a 60 minute default."""
        # Exercise the maximum's expiry behavior, not only the selector metadata.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration)
            setting = run.doc["blueprint"]["input"]["source_timeout"]
            self.assertEqual(setting["default"], 60)
            self.assertEqual(setting["selector"]["number"]["min"], 1)
            self.assertEqual(setting["selector"]["number"]["max"], 120)
            run.inputs["source_timeout"] = 120
            run.clock += timedelta(minutes=120)
            run.fire("periodic_sync")
            self.assertEqual(run.calls, [])

    def test_modes_disabled_unknown_and_missing_destinations_skip(self):
        """Do not override an explicit local selection or send through unknown modes."""
        # Internal, unavailable, and missing mode entities must fail closed.
        for integration, modes in (("zha", ("off", "unknown", "unavailable")),
                                   ("mqtt", ("internal", "local_temperature", "unknown", "unavailable", "external", "external_2", "external_3"))):
            for mode in modes:
                run = average_runner(integration)
                entity = ("switch.target_external_temperature_sensor" if integration == "zha"
                          else "select.target_temperature_sensor_select")
                run.set_state(entity, mode)
                run.fire("periodic_sync")
                self.assertEqual(run.calls, [])
            run = average_runner(integration)
            run.entity_map["target"] = []
            run.fire("periodic_sync")
            self.assertEqual(run.calls, [])

    def test_wrong_devices_skip_and_mode_changes_resync_without_echo_loops(self):
        """Admit only the selected target's temperature mode events."""
        # A number echo is not a mode change and cannot feed another write.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration)
            mode = ("switch.target_external_temperature_sensor" if integration == "zha"
                    else "select.target_temperature_sensor_select")
            run.dispatch_state(mode, {"state": "off"}, run.states[mode])
            self.assertEqual(len(run.calls), 1)
            run.calls.clear()
            for entity in ("sensor.unrelated", "number.target_external_temperature_sensor_value",
                           "number.target_external_temperature_input"):
                run.dispatch_state(entity, None, {"state": "22"})
            self.assertEqual(run.calls, [])
            for field, value in (("manufacturer", "OTHER"), ("model", "OTHER"), ("identifiers", [])):
                run = average_runner(integration)
                run.devices["target"][field] = value
                run.fire("periodic_sync")
                self.assertEqual(run.calls, [])

    def test_mqtt_remote_and_offline_modes_accept_same_temperature_recovery(self):
        """Write only the temperature and let TRV-ZBT firmware restore its remote source."""
        # No selector write or acknowledgement wait is needed for separate attributes.
        for mode in ("remote_source_offline", "remote_temperature"):
            run = average_runner("mqtt", ["sensor.source"])
            run.set_state("select.target_temperature_sensor_select", mode)
            run.set_state("number.target_external_temperature_input", "20", "°C")
            run.fire("periodic_sync")
            self.assertEqual(len(run.calls), 1)
            self.assertEqual(run.calls[0]["action"], "number.set_value")
            self.assertEqual(run.calls[0]["data"], {"value": 20})

    def test_all_expired_sources_recover_with_same_value_after_unavailable(self):
        """A valid reading restored after unavailability gets a new freshness window."""
        # This covers firmware recovery input; the runner does not emulate valve hardware.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration, ["sensor.source"])
            run.clock += timedelta(minutes=61)
            run.fire("periodic_sync")
            self.assertEqual(run.calls, [])
            if integration == "mqtt":
                run.set_state("select.target_temperature_sensor_select", "remote_source_offline")
            run.set_state("sensor.source", "unavailable", "°C")
            run.set_state("sensor.source", "20", "°C")
            run.fire("source_changed")
            self.assertEqual(run.calls[0]["data"]["value"], 20)

    def test_single_numeric_source_matches_reference_without_extra_range_filter(self):
        """Keep temperature range handling in the integration as in the single-source YAML."""
        # Compare service intent only: actual numbers may reject values outside their range.
        for integration in ("zha", "mqtt"):
            for value in ("-5", "120", "0", "99.9"):
                run = average_runner(integration, ["sensor.source"])
                reference = single_source(("remote_temperature_link_trvzbt.yaml", "TRV-ZBT",
                                           "Zigbee thermostatic radiator valve", None), integration)
                for runner in (run, reference):
                    runner.set_state("sensor.source", value, "°C")
                run.fire("periodic_sync")
                reference.fire("source_temperature")
                expected = dict(reference.calls[0], continue_on_error=True)
                self.assertEqual(run.calls, [expected])

    def test_service_failure_can_retry_on_next_periodic_run(self):
        """A failed temperature write does not permanently disable later synchronization."""
        # Integration failures are isolated, with the next periodic trigger making a fresh attempt.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration)
            suffix = "external_temperature_sensor_value" if integration == "zha" else "external_temperature_input"
            run.fail.add(f"number.target_{suffix}")
            run.fire("periodic_sync")
            self.assertEqual(len(run.errors), 1)
            run.fail.clear()
            run.calls.clear()
            run.set_state("sensor.source", "22", "°C")
            run.fire("periodic_sync")
            self.assertEqual(run.calls[0]["data"]["value"], 23)

    def test_alternative_zha_switch_name_supports_periodic_and_enable_sync(self):
        """Discover both ZBT switch suffixes and admit their mode transition events."""
        # Exercise the ZBT-specific suffix in discovery and the global event filter.
        run = average_runner()
        run.entity_map["target"][0] = "switch.target_temperature_sensor_select"
        old = run.set_state("switch.target_temperature_sensor_select", "off")
        run.fire("periodic_sync")
        self.assertEqual(run.calls, [])
        new = run.set_state("switch.target_temperature_sensor_select", "on")
        run.dispatch_state("switch.target_temperature_sensor_select", old, new)
        self.assertEqual(run.calls[0]["data"]["value"], 22)
        run.calls.clear()
        run.fire("periodic_sync")
        self.assertEqual(len(run.calls), 1)

    def test_device_filter_matches_reference_and_retains_model_id(self):
        """Use the reference device selection and its required HA baseline."""
        # The average blueprint must not accidentally select a different SONOFF valve.
        run = average_runner()
        reference = single_source(("remote_temperature_link_trvzbt.yaml", "TRV-ZBT",
                                   "Zigbee thermostatic radiator valve", None))
        self.assertEqual(run.doc["blueprint"]["input"]["target_device"]["selector"]["device"]["filter"],
                         reference.doc["blueprint"]["input"]["target_device"]["selector"]["device"]["filter"])
        self.assertTrue(run.doc["blueprint"]["input"]["target_device"]["selector"]["device"]["multiple"])
        self.assertEqual(run.doc["blueprint"]["homeassistant"]["min_version"], "2025.4.0")


class MultipleTargetAverageTests(unittest.TestCase):
    """Verify one shared average reaches independent ZHA and MQTT valves."""

    def setUp(self):
        """Bind an average source group to one target of each integration."""
        # Copy only destination fixtures so the source group remains shared.
        self.run = average_runner()
        peer = average_runner("mqtt")
        self.run.inputs["target_device"] = ["target", "peer", "target"]
        self.run.devices["peer"] = peer.devices["target"]
        self.run.entity_map["peer"] = [entity.replace("target_", "peer_")
                                       for entity in peer.entity_map["target"]]
        for entity in peer.entity_map["target"]:
            snapshot = peer.states[entity]
            if snapshot:
                self.run.set_state(entity.replace("target_", "peer_"), snapshot["state"],
                                   **snapshot["attributes"])

    def test_shared_average_reaches_both_targets_on_each_full_sync(self):
        """All full synchronization triggers update each distinct target once."""
        # Scalar target compatibility is also exercised by the existing average tests.
        for trigger in ("source_changed", "ha_started", "automation_reloaded", "periodic_sync"):
            self.run.calls.clear()
            self.run.fire(trigger)
            self.assertEqual([call["data"]["value"] for call in self.run.calls], [22, 22])
            self.assertEqual([call["target"]["entity_id"] for call in self.run.calls],
                             ["number.target_external_temperature_sensor_value",
                              "number.peer_external_temperature_input"])
        self.assertEqual(self.run.doc["mode"], "queued")

    def test_first_failure_and_disabled_mode_do_not_block_peer(self):
        """A broken first destination cannot abort the second destination."""
        # A handled error remains recorded while the healthy valve receives the mean.
        self.run.fail.add("number.target_external_temperature_sensor_value")
        self.run.fire("periodic_sync")
        self.assertEqual(len(self.run.errors), 1)
        self.assertEqual(self.run.calls[-1]["target"]["entity_id"], "number.peer_external_temperature_input")
        self.run.fail.clear()
        self.run.calls.clear()
        self.run.set_state("switch.target_external_temperature_sensor", "off")
        self.run.fire("periodic_sync")
        self.assertEqual(len(self.run.calls), 1)
        self.assertEqual(self.run.calls[0]["data"]["value"], 22)

    def test_mode_and_recovery_events_only_update_their_owner(self):
        """An MQTT mode enable or recovered number does not refresh the ZHA peer."""
        # Number echoes remain excluded by the global event filter.
        for entity, before, after in (
            ("select.peer_temperature_sensor_select", "internal", "remote_temperature"),
            ("number.peer_external_temperature_input", "unavailable", "22"),
        ):
            self.run.calls.clear()
            old = self.run.set_state(entity, before)
            new = self.run.set_state(entity, after)
            self.run.dispatch_state(entity, old, new)
            self.assertEqual(len(self.run.calls), 1)
            self.assertEqual(self.run.calls[0]["target"]["entity_id"], "number.peer_external_temperature_input")
        self.run.calls.clear()
        self.run.dispatch_state("number.peer_external_temperature_input", {"state": "22"}, {"state": "23"})
        self.assertEqual(self.run.calls, [])

    def test_group_sources_exclude_all_selected_valves_and_expire_together(self):
        """Every target receives the same mean after excluding any valve's sensors."""
        # A sensor from the second valve cannot influence the first valve's result.
        self.run.entity_map["peer"].append("sensor.second")
        self.run.fire("periodic_sync")
        self.assertEqual([call["data"]["value"] for call in self.run.calls], [20, 20])
        self.run.calls.clear()
        self.run.clock += timedelta(minutes=61)
        self.run.fire("periodic_sync")
        self.assertEqual(self.run.calls, [])
        self.run.set_state("sensor.source", "21", "°C")
        self.run.fire("source_changed")
        self.assertEqual([call["data"]["value"] for call in self.run.calls], [21, 21])

    def test_empty_target_list_sends_nothing(self):
        """An automation with no selected destinations makes no service calls."""
        # This must not turn an empty target into a broadcast service target.
        self.run.inputs["target_device"] = []
        self.run.fire("periodic_sync")
        self.assertEqual(self.run.calls, [])

    def test_numbered_same_model_targets_receive_updates_and_recovery(self):
        """HA duplicate-name suffixes must not hide any selected valve or its events."""
        # Reproduce same-name devices: only the appended entity number differs.
        for integration in ("zha", "mqtt"):
            for suffix in ("_2", "_3", "_12"):
                with self.subTest(integration=integration, suffix=suffix):
                    run = average_runner(integration)
                    run.inputs["target_device"] = ["target", "peer"]
                    run.devices["peer"] = dict(run.devices["target"])
                    run.entity_map["peer"] = [entity + suffix for entity in run.entity_map["target"]]
                    for entity in run.entity_map["target"]:
                        snapshot = run.states[entity]
                        if snapshot:
                            run.set_state(entity + suffix, snapshot["state"], **snapshot["attributes"])
                    destination = ("number.target_external_temperature_sensor_value" if integration == "zha"
                                   else "number.target_external_temperature_input")
                    run.fire("periodic_sync")
                    self.assertEqual([call["target"]["entity_id"] for call in run.calls],
                                     [destination, destination + suffix])
                    self.assertEqual([call["data"]["value"] for call in run.calls], [22, 22])
                    run.calls.clear()
                    run.fail.add(destination)
                    run.fire("periodic_sync")
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
                    new = run.set_state(destination + suffix, "22", "°C")
                    run.dispatch_state(destination + suffix, old, new)
                    self.assertEqual([call["target"]["entity_id"] for call in run.calls], [destination + suffix])
                    run.calls.clear()
                    newer = run.set_state(destination + suffix, "23", "°C")
                    run.dispatch_state(destination + suffix, new, newer)
                    self.assertEqual(run.calls, [])
