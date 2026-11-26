"""Behavior checks for the TP_WGZBA remote temperature blueprint."""

from functools import partial
import unittest

from tests.common.single_source_checks import SingleSourceChecks, single_source
from tests.common.entity_discovery import assert_entity_id_compatibility


class RemoteTemperatureTests(SingleSourceChecks, unittest.TestCase):
    """Run the shared single-source scenarios for this blueprint."""

    cases = (("remote_temperature_link_tp_wgzba.yaml", "TP-WGZBA",
              "Zigbee thermostat panel", 0x7009),)

    def test_source_mode_discovery_is_independent_of_entity_names(self):
        """Use the shared numbering/localization matrix for updates and mode-enable events."""
        # The diagnostic raw enum contract must survive localized IDs on the selected device.
        def exercise(run, entity_ids):
            """Send one source update and enable the renamed diagnostic mode entity."""
            # Dispatch through the actual event filter rather than calling the recovery action directly.
            run.fire("source_temperature")
            mode = entity_ids["sensor.target_temperature_source_mode"]
            old = run.set_state(mode, "internal_sensor", device_class="enum")
            run.fire("source_temperature")
            new = run.set_state(mode, "external_sensor", device_class="enum")
            run.dispatch_state(mode, old, new)

        assert_entity_id_compatibility(self, partial(single_source, self.cases[0]), exercise, "target",
                                       expected_actions=["zha.set_zigbee_cluster_attribute"] * 2)

    def test_localized_mode_sensor_controls_sync(self):
        """Detect the mode sensor by its raw state regardless of its ID."""
        # Replace the fixture mode entity with a localized ID.
        run = single_source(self.cases[0])
        mode = "sensor.target_temperaturquelle"
        run.entity_map["target"][0] = mode
        off = run.set_state(mode, "internal_sensor", device_class="enum")
        run.fire("source_temperature")
        self.assertEqual(run.calls, [])

        on = run.set_state(mode, "external_sensor", device_class="enum")
        run.dispatch_state(mode, off, on)
        self.assertEqual(len(run.calls), 1)
        run.fire("source_temperature")
        self.assertEqual(len(run.calls), 2)

    def test_mode_sensor_must_belong_to_target(self):
        """A mode sensor from another device cannot enable temperature writes."""
        # The target exposes only its legacy switch while another device enters external mode.
        run = single_source(self.cases[0])
        run.entity_map["target"][0] = "switch.target_external_temperature_sensor"
        mode = "sensor.other_device"
        run.entity_map["other"] = [mode]
        off = run.set_state(mode, "internal_sensor", device_class="enum")
        on = run.set_state(mode, "external_sensor", device_class="enum")
        run.dispatch_state(mode, off, on)
        run.fire("source_temperature")
        self.assertEqual(run.calls, [])

    def test_unavailable_mode_does_not_fall_back_to_switch(self):
        """Pause synchronization while the diagnostic state is unavailable."""
        # The English legacy switch is still on and must be ignored.
        run = single_source(self.cases[0])
        run.entity_map["target"].append("switch.target_external_temperature_sensor")
        run.set_state(run.entity_map["target"][0], "unavailable", device_class="enum")
        run.fire("source_temperature")
        self.assertEqual(run.calls, [])
