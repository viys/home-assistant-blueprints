"""Behavior checks for the TRVZBT remote temperature blueprint."""

import unittest

from common.single_source_checks import SingleSourceChecks, single_source


class RemoteTemperatureTests(SingleSourceChecks, unittest.TestCase):
    """Run the shared single-source scenarios for this blueprint."""

    cases = (("remote_temperature_link_trvzbt.yaml", "TRV-ZBT",
              "Zigbee thermostatic radiator valve", None),)

    def test_trvzbt_accepts_alternative_zha_switch_name(self):
        """Support both selector-switch entity suffixes declared in the ZBT YAML."""
        # The fixture must not hard-code only the older switch naming pattern.
        run = single_source(self.cases[0])
        run.entity_map["target"][0] = "switch.target_temperature_sensor_select"
        run.set_state("switch.target_temperature_sensor_select", "on")
        run.fire("source_temperature")
        self.assertEqual(run.calls[0]["data"]["value"], 20)
