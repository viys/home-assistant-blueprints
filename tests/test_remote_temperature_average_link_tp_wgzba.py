"""Execute averaging, freshness, and legacy T01 destination behavior offline."""

from datetime import timedelta
import unittest

from tests.common.single_source_checks import single_source
from tools.blueprint_runner import HandledServiceError


def average_runner(integration="zha", sources=None):
    """Bind the average blueprint to deterministic temperature and device fixtures."""
    # Reuse existing destination metadata; this blueprint has a multiple selector.
    run = single_source(("remote_temperature_average_link_tp_wgzba.yaml",
                         "TP-WGZBA", "Zigbee thermostat panel", 0x7009), integration)
    run.inputs["source_entities"] = sources if sources is not None else ["sensor.source", "sensor.second"]
    run.set_state("sensor.second", "24", "°C")
    if integration == "mqtt":
        run.set_state("select.target_temperature_sensor_select", "remote_temperature")
    return run


class AverageTemperatureTests(unittest.TestCase):
    """Verify observable service calls for both declared integrations."""

    def test_mixed_units_are_averaged_before_destination_rounding(self):
        """Convert each source before averaging and encode the single legacy input."""
        # Three different units all participate; no remote slot attributes are used.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration, ["sensor.source", "sensor.second", "sensor.third"])
            run.set_state("sensor.source", "68", "°F")
            run.set_state("sensor.second", "297.15", "K")
            run.set_state("sensor.third", "21", "°C")
            run.fire("periodic_sync")
            self.assertEqual(len(run.calls), 1)
            if integration == "zha":
                self.assertEqual(run.calls[0]["data"], dict(ieee="00:11", endpoint_id=1,
                                 cluster_id=0xFC11, cluster_type="in", attribute=0x7009, value=2167))
            else:
                self.assertEqual(run.calls[0]["target"], {"entity_id": "number.target_external_temperature_input"})
                self.assertEqual(run.calls[0]["data"], {"value": 21.7})

    def test_distinct_sources_have_equal_weight_and_self_sources_are_excluded(self):
        """Duplicate selections and target feedback cannot bias the average."""
        # The extra target sensor would otherwise dominate the result.
        run = average_runner(sources=["sensor.source", "sensor.source", "sensor.second", "sensor.self"])
        run.entity_map["target"].append("sensor.self")
        run.set_state("sensor.self", "100", "°C")
        run.fire("periodic_sync")
        self.assertEqual(run.calls[0]["data"]["value"], 2200)

    def test_expired_source_is_excluded_at_exact_timeout_and_recovers(self):
        """One stale source drops out even if the other source remains unchanged."""
        # Test the boundary and recovery without refreshing source timestamps on send.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration)
            run.inputs["source_timeout"] = 10
            run.states["sensor.source"]["last_changed"] = run.clock - timedelta(minutes=10)
            run.fire("periodic_sync")
            self.assertEqual(run.calls[-1]["data"]["value"], 2400 if integration == "zha" else 24)
            run.set_state("sensor.source", "22", "°C")
            run.fire("source_changed")
            self.assertEqual(run.calls[-1]["data"]["value"], 2300 if integration == "zha" else 23)

    def test_all_expired_stops_every_service_call_until_a_source_changes(self):
        """Let the thermostat time out naturally rather than sending offline or zero."""
        # The default validity is 60 minutes; startup and reload must not bypass it.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration)
            run.clock += timedelta(minutes=61)
            for trigger in ("periodic_sync", "ha_started", "automation_reloaded"):
                run.fire(trigger)
            self.assertEqual(run.calls, [])
            run.set_state("sensor.second", "25", "°C")
            run.fire("source_changed")
            self.assertEqual(len(run.calls), 1)

    def test_maximum_validity_cannot_exceed_two_hours_and_expires_at_boundary(self):
        """Cap the selectable lifetime at the device's two-hour timeout."""
        # Use the selector's actual maximum to exercise the expiry boundary.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration, sources=["sensor.source"])
            setting = run.doc["blueprint"]["input"]["source_timeout"]
            self.assertEqual(setting["selector"]["number"]["max"], 120)
            run.inputs["source_timeout"] = setting["selector"]["number"]["max"]
            run.clock = run.states["sensor.source"]["last_changed"] + timedelta(minutes=120)
            run.fire("periodic_sync")
            self.assertEqual(run.calls, [])

    def test_identical_values_and_attribute_updates_do_not_extend_validity(self):
        """Accept the agreed risk of excluding an unchanged reporting sensor."""
        # Both repeats and attributes preserve last_changed in the runner as in HA.
        run = average_runner(sources=["sensor.source"])
        original = run.states["sensor.source"]["last_changed"]
        run.clock += timedelta(minutes=61)
        run.set_state("sensor.source", "20", "°C", battery=90)
        run.fire("source_changed")
        self.assertEqual(run.states["sensor.source"]["last_changed"], original)
        self.assertEqual(run.calls, [])

    def test_invalid_missing_and_unsupported_sources_are_skipped_individually(self):
        """Bad input cannot become zero or prevent another valid source being sent."""
        # Include deleted entities, nonfinite values, and unsupported units.
        cases = [("unavailable", "°C"), ("unknown", "°C"), ("NaN", "°C"),
                 ("inf", "°C"), ("bad", "°C"), ("20", "bad")]
        for integration in ("zha", "mqtt"):
            for value, unit in cases:
                run = average_runner(integration)
                run.set_state("sensor.source", value, unit)
                run.fire("source_changed")
                self.assertEqual(run.calls[0]["data"]["value"], 2400 if integration == "zha" else 24)
            run = average_runner(integration)
            del run.states["sensor.source"]
            run.fire("periodic_sync")
            self.assertEqual(len(run.calls), 1)
            run.inputs["source_entities"] = []
            run.calls.clear()
            run.fire("periodic_sync")
            self.assertEqual(run.calls, [])

    def test_numeric_sources_are_averaged_without_a_blueprint_temperature_limit(self):
        """Match the reference blueprint's numeric validation for both integrations."""
        # Transport limits belong to the selected integration, not source membership.
        for integration in ("zha", "mqtt"):
            for value, unit, expected in (("-5", "°C", 9.5), ("120", "°C", 72),
                                          ("23", "°F", 9.5), ("393.15", "K", 72),
                                          ("-274", "°C", -125), ("328", "°C", 176)):
                with self.subTest(integration=integration, value=value, unit=unit):
                    run = average_runner(integration)
                    run.set_state("sensor.source", value, unit)
                    run.fire("periodic_sync")
                    self.assertEqual(run.calls[0]["data"]["value"], expected * 100 if integration == "zha" else expected)

    def test_single_source_uses_the_same_service_value_as_reference_blueprint(self):
        """The averaging blueprint adds no clamp or exclusion to the reference path."""
        # Compare actual YAML service calls; these tests do not model device acceptance.
        for integration in ("zha", "mqtt"):
            for value in ("-5", "120"):
                run = average_runner(integration, sources=["sensor.source"])
                run.set_state("sensor.source", value, "°C")
                run.fire("periodic_sync")
                reference = single_source(("remote_temperature_link_tp_wgzba.yaml",
                                           "TP-WGZBA", "Zigbee thermostat panel", 0x7009), integration)
                reference.set_state("sensor.source", value, "°C")
                reference.fire("source_temperature")
                self.assertEqual(run.calls, reference.calls)

    def test_legacy_input_boundaries_survive_all_unit_conversions(self):
        """Accept exact supported endpoints without floating-point conversion exclusions."""
        # Kelvin's upper boundary introduces binary floating-point subtraction noise.
        for integration in ("zha", "mqtt"):
            for value, unit, expected in (("0", "°C", 0), ("32", "°F", 0),
                                          ("273.15", "K", 0), ("99.9", "°C", 99.9),
                                          ("211.82", "°F", 99.9), ("373.05", "K", 99.9)):
                with self.subTest(integration=integration, value=value, unit=unit):
                    run = average_runner(integration, sources=["sensor.source"])
                    run.set_state("sensor.source", value, unit)
                    run.fire("periodic_sync")
                    self.assertEqual(len(run.calls), 1)
                    self.assertEqual(run.calls[0]["data"]["value"], round(expected * 100) if integration == "zha" else expected)

    def test_device_filter_uses_fields_supported_by_minimum_home_assistant(self):
        """Retain model_id with the HA 2025.4 selector schema that supports it."""
        # https://github.com/home-assistant/core/blob/2025.4.0/homeassistant/helpers/selector.py
        run = average_runner()
        filters = run.doc["blueprint"]["input"]["target_device"]["selector"]["device"]["filter"]
        self.assertEqual(run.doc["blueprint"]["homeassistant"]["min_version"], "2025.4.0")
        reference = single_source(("remote_temperature_link_tp_wgzba.yaml",
                                   "TP-WGZBA", "Zigbee thermostat panel", 0x7009))
        self.assertEqual(filters, reference.doc["blueprint"]["input"]["target_device"]["selector"]["device"]["filter"])
        supported_fields = {"integration", "manufacturer", "model", "model_id", "entity"}
        for target_filter in filters:
            self.assertLessEqual(set(target_filter), supported_fields)
            integration = target_filter["integration"]
            target = average_runner(integration).devices["target"]
            self.assertEqual(target_filter["manufacturer"], target["manufacturer"])
            self.assertEqual(target_filter["model"], target["model"])
            if integration == "mqtt":
                self.assertEqual(target_filter["model_id"], target["model_id"])

    def test_start_reload_and_periodic_refresh_keep_fresh_unchanged_average(self):
        """Refreshing the receiver never refreshes the sources' validity clock."""
        # This models admitted time triggers, not Home Assistant wall-clock scheduling.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration)
            original = run.states["sensor.source"]["last_changed"]
            for trigger in ("ha_started", "automation_reloaded", "periodic_sync"):
                run.fire(trigger)
            self.assertEqual(len(run.calls), 3)
            self.assertEqual(run.states["sensor.source"]["last_changed"], original)

    def test_unavailable_source_event_recalculates_and_recovery_rejoins(self):
        """State events include unavailable transitions rather than filtering them out."""
        # An offline transition must cause an immediate recalculation with the survivor.
        run = average_runner()
        old = run.states["sensor.source"]
        new = run.set_state("sensor.source", "unavailable", "°C")
        run.dispatch_state("sensor.source", old, new)
        self.assertEqual(len(run.calls), 1)
        self.assertEqual(run.calls[-1]["data"]["value"], 2400)
        recovered = run.set_state("sensor.source", "20", "°C")
        run.dispatch_state("sensor.source", new, recovered)
        self.assertEqual(run.calls[-1]["data"]["value"], 2200)

    def test_disabled_mode_wrong_targets_and_missing_destination_do_not_send(self):
        """Only supported targets with an enabled external source can receive values."""
        # No automatic switch from a deliberately selected internal sensor.
        for integration in ("zha", "mqtt"):
            for field, value in (("manufacturer", "OTHER"), ("model", "OTHER"), ("identifiers", [])):
                run = average_runner(integration)
                run.devices["target"][field] = value
                run.fire("periodic_sync")
                self.assertEqual(run.calls, [])
            run = average_runner(integration)
            mode = run.entity_map["target"][0] if integration == "zha" else "select.target_temperature_sensor_select"
            run.set_state(mode, "internal_sensor" if integration == "zha" else "local_temperature")
            run.fire("periodic_sync")
            self.assertEqual(run.calls, [])
            run.entity_map["target"] = []
            run.fire("periodic_sync")
            self.assertEqual(run.calls, [])

    def test_mode_enable_syncs_and_unrelated_events_do_nothing(self):
        """The broad event listener admits only the target mode entity."""
        # Source changes are handled by their dedicated state trigger only.
        for integration in ("zha", "mqtt"):
            run = average_runner(integration)
            mode = run.entity_map["target"][0] if integration == "zha" else "select.target_temperature_sensor_select"
            new = run.states[mode]
            run.dispatch_state(mode, {"state": "internal"}, new)
            self.assertEqual(len(run.calls), 1)
            run.calls.clear()
            run.dispatch_state("sensor.unrelated", None, {"state": "on"})
            self.assertEqual(run.calls, [])

    def test_mqtt_offline_recovery_refreshes_value_before_enabling(self):
        """Restore the converter's offline state without replaying its old temperature."""
        # The first write updates the cached value used by the subsequent selector write.
        run = average_runner("mqtt")
        run.set_state("select.target_temperature_sensor_select", "remote_source_offline")
        run.set_state("number.target_external_temperature_input", "22", "°C")
        run.fire("periodic_sync")
        self.assertEqual([call["action"] for call in run.calls], ["number.set_value", "select.select_option"])
        self.assertEqual(run.calls[0]["data"], {"value": 22})
        self.assertEqual(run.calls[1]["data"], {"option": "remote_temperature"})
        run.calls.clear()
        run.clock += timedelta(minutes=61)
        run.fire("periodic_sync")
        self.assertEqual(run.calls, [])

    def test_mqtt_offline_recovery_waits_for_new_value_acknowledgement(self):
        """Publishing a number cannot enable an offline source using an old cache."""
        # With no echoed update, the simulated wait times out and skips the selector.
        run = average_runner("mqtt")
        run.set_state("select.target_temperature_sensor_select", "remote_source_offline")
        run.fire("periodic_sync")
        self.assertEqual([call["action"] for call in run.calls], ["number.set_value"])
        run.calls.clear()
        run.set_state("number.target_external_temperature_input", "22", "°C")
        run.fire("periodic_sync")
        self.assertEqual([call["action"] for call in run.calls], ["number.set_value", "select.select_option"])

    def test_failed_write_is_retried_on_next_periodic_run(self):
        """A failed temperature update cannot progress to enabling an offline source."""
        # The following minute provides a fresh attempt without a retry loop.
        run = average_runner("mqtt")
        run.set_state("select.target_temperature_sensor_select", "remote_source_offline")
        run.fail.add("number.target_external_temperature_input")
        with self.assertRaises(HandledServiceError):
            run.fire("periodic_sync")
        self.assertEqual(len(run.calls), 1)
        run.fail.clear()
        run.calls.clear()
        run.set_state("number.target_external_temperature_input", "22", "°C")
        run.fire("periodic_sync")
        self.assertEqual(len(run.calls), 2)

    def test_mqtt_acknowledgement_after_expiration_does_not_restore_source(self):
        """An average that expires during the MQTT wait must not enable the source."""
        # Model an echoed value after all contributors cross their validity boundary.
        run = average_runner("mqtt")
        run.set_state("select.target_temperature_sensor_select", "remote_source_offline")
        for entity in run.inputs["source_entities"]:
            run.states[entity]["last_changed"] = run.clock - timedelta(minutes=59, seconds=55)

        def acknowledge_after_expiration(runner, call):
            """Deliver the temperature acknowledgement after six seconds."""
            # The send succeeds, but the source data must still be checked afterward.
            runner.clock += timedelta(seconds=6)
            runner.set_state("number.target_external_temperature_input", "22", "°C")

        run.hook = acknowledge_after_expiration
        run.fire("periodic_sync")
        self.assertEqual([call["action"] for call in run.calls], ["number.set_value"])

    def test_switching_to_local_during_acknowledgement_preserves_user_choice(self):
        """A pending recovery cannot override a newly selected local source."""
        # Global conditions may reject the mode event without stopping an active run.
        run = average_runner("mqtt")
        run.set_state("select.target_temperature_sensor_select", "remote_source_offline")

        def acknowledge_after_local_selection(runner, call):
            """Echo the number after the user changes the temperature source."""
            # The post-wait guard must check live mode as well as source expiry.
            runner.set_state("select.target_temperature_sensor_select", "local_temperature")
            runner.set_state("number.target_external_temperature_input", "22", "°C")

        run.hook = acknowledge_after_local_selection
        run.fire("periodic_sync")
        self.assertEqual([call["action"] for call in run.calls], ["number.set_value"])
