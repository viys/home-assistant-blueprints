"""Regression checks for the shared simulator's explicitly supported semantics."""

import unittest

from tools.blueprint_coverage import ROOT
from tools.blueprint_runner import BlueprintRunner, ha_bool, is_number


class RunnerSemanticsTests(unittest.TestCase):
    """Prevent fixture coercions from fabricating firmware routing or valid readings."""

    def test_render_preserves_hex_scientific_and_quoted_strings(self):
        """Do not turn firmware version strings into integers before YAML validation."""
        # HA's result parser accepts simple decimals, unlike NativeEnvironment's literals.
        run = BlueprintRunner(ROOT / "automation/sonoff/remote_temperature_sources_link_tp_wgzba.yaml", {})
        for value in ("0x00001006", "1e3", "1_000", "'quoted'", "1+2j"):
            self.assertEqual(run.render("{{ value }}", {"value": value}), value)
        for value, expected in (("20", 20), ("-5.5", -5.5), ("True", True),
                                ("False", False), ("[1, 2]", [1, 2]), ("{'a': 1}", {"a": 1})):
            self.assertEqual(run.render("{{ value }}", {"value": value}), expected)

    def test_boolean_filter_handles_lowercase_false(self):
        """Legacy firmware fallback outputs lowercase false and must stay false."""
        # A plain Python bool('false') would incorrectly enable the newer-firmware branch.
        for value in ("false", "False", "off", "0", False):
            self.assertFalse(ha_bool(value))
        for value in ("true", "True", "on", "1", True):
            self.assertTrue(ha_bool(value))

    def test_numeric_validation_rejects_nonfinite_values(self):
        """Match the numeric validity distinction used in real source guards."""
        # Unknown, infinity, and NaN must never pass only because float() accepts some.
        for value in ("unknown", "unavailable", "NaN", "inf", "-inf", None, "--1"):
            self.assertFalse(is_number(value))
        for value in ("-5", "20.5", 0, 20):
            self.assertTrue(is_number(value))


if __name__ == "__main__":
    unittest.main()
