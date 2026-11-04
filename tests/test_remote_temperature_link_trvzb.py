"""Behavior checks for the TRVZB remote temperature blueprint."""

import unittest

from common.single_source_checks import SingleSourceChecks


class RemoteTemperatureTests(SingleSourceChecks, unittest.TestCase):
    """Run the shared single-source scenarios for this blueprint."""

    cases = (("remote_temperature_link_trvzb.yaml", "TRVZB",
              "Zigbee thermostatic radiator valve", None),)
