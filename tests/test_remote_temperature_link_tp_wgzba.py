"""Behavior checks for the TP_WGZBA remote temperature blueprint."""

import unittest

from common.single_source_checks import SingleSourceChecks


class RemoteTemperatureTests(SingleSourceChecks, unittest.TestCase):
    """Run the shared single-source scenarios for this blueprint."""

    cases = (("remote_temperature_link_tp_wgzba.yaml", "TP-WGZBA",
              "Zigbee thermostat panel", 0x7009),)
