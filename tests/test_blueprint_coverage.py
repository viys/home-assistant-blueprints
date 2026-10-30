"""Regression checks for source coverage accounting and changed-block gates."""

import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from tools.blueprint_coverage import Recorder
from tools.run_coverage import changed_lines, evaluate_gates, load_thresholds, main, metric, write_reports


SOURCE = """blueprint:
  name: Example
conditions:
  - condition: template
    value_template: '{{ allowed }}'
actions:
  - choose:
      - conditions:
          - condition: template
            value_template: '{{ ready }}'
        sequence:
          - action: number.set_value
            data:
              value: 10
"""


class CoverageTests(unittest.TestCase):
    """Check that static loading and successful test counts cannot fabricate coverage."""

    def setUp(self):
        """Create a fresh two-blueprint inventory for each recorder test."""
        # An unbound second file must still contribute uncovered opportunities.
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / "thresholds.json"
        self.thresholds = dict(changed_actions=90, changed_branches=80,
                               overall_actions=90, overall_branches=80)
        self.config.write_text(json.dumps(self.thresholds), encoding="utf-8")
        (self.root / "automation").mkdir()
        self.file = self.root / "automation/example.yaml"
        self.file.write_text(SOURCE, encoding="utf-8")
        (self.root / "automation/untested.yaml").write_text(SOURCE, encoding="utf-8")
        self.recorder = Recorder(self.root)
        self.document = yaml.safe_load(SOURCE)
        self.recorder.bind(self.file, self.document)

    def test_loading_records_no_execution(self):
        """Inventory and object binding must leave every point uncovered."""
        # A file merely passing structural validation has zero behavior coverage.
        self.assertEqual(sum(row["hits"] for row in self.recorder.rows()), 0)
        self.assertEqual(len(self.recorder.rows()), 16)
        self.assertEqual(metric([]), "N/A")

    def test_true_false_and_no_match_are_distinct(self):
        """Record only actually evaluated outcomes at their exact source locations."""
        # A true condition does not imply its false or the choose no-match path ran.
        condition = self.document["conditions"][0]
        action = self.document["actions"][0]
        self.recorder.hit(condition, "condition", "true")
        self.recorder.hit(action, "choose", 0)
        self.recorder.hit(action, "action", "reached")
        rows = self.recorder.rows()
        self.assertEqual(sum(row["hits"] > 0 for row in rows), 3)
        self.assertTrue(all(row["hits"] == 0 for row in rows if "untested" in row["file"]))
        self.assertTrue(all(row["hits"] == 0 for row in rows if row["outcome"] in ("false", "none")))
        self.assertEqual(next(row["line"] for row in rows if row["hits"] and row["kind"] == "condition"), 4)

    def test_unknown_execution_point_fails_loudly(self):
        """Do not create an opportunity dynamically when instrumentation is wrong."""
        # Fabricated branch labels must fail rather than improve a coverage score.
        with self.assertRaises(KeyError):
            self.recorder.hit(self.document["actions"][0], "choose", 5)

    def test_block_span_excludes_next_siblings_indentation(self):
        """An edit to a sibling must not mark the preceding action as changed."""
        # PyYAML end marks can point at the next line's nonzero indentation column.
        self.file.write_text("actions:\n  - action: first.service\n  - action: second.service\n", encoding="utf-8")
        rows = [row for row in Recorder(self.root).rows() if row["file"] == "automation/example.yaml"]
        self.assertEqual([(row["line"], row["end_line"]) for row in rows], [(2, 2), (3, 3)])
        with patch("tools.run_coverage.ROOT", self.root):
            missing = write_reports(rows, self.root / "report",
                                    {"automation/example.yaml": {3}}, unittest.TestResult(), "base")
        self.assertEqual([row["path"] for row in missing], ["actions/1"])

    def test_changed_nested_value_requires_its_action_and_branches(self):
        """A change inside service data must be assigned to containing YAML blocks."""
        # The action's start line alone would miss this value-only modification.
        output = self.root / "report"
        passed = unittest.TestResult()
        with patch("tools.run_coverage.ROOT", self.root):
            missing = write_reports(self.recorder.rows(), output,
                                    {"automation/example.yaml": {14}}, passed, "base")
        self.assertTrue(missing)
        self.assertTrue(any(row["path"].endswith("sequence/0") for row in missing))
        payload = json.loads((output / "coverage.json").read_text(encoding="utf-8"))
        self.assertTrue(payload["tests_passed"])
        self.assertEqual(payload["changed_files"], ["automation/example.yaml"])
        self.assertIn("Simulated", (output / "summary.md").read_text(encoding="utf-8"))
        self.assertTrue((output / "index.html").is_file())

    def test_failed_test_run_is_not_reported_as_passed(self):
        """Failed runs still export diagnostic data without claiming success."""
        # The tests result, rather than coverage percentage, determines run success.
        result = unittest.TestResult()
        result.failures.append((self, "deliberate failure"))
        with patch("tools.run_coverage.ROOT", self.root):
            write_reports(self.recorder.rows(), self.root / "report", {}, result, None)
        report = json.loads((self.root / "report/coverage.json").read_text(encoding="utf-8"))
        self.assertFalse(report["tests_passed"])

    def test_deleted_file_does_not_inherit_previous_path(self):
        """Reset diff file tracking at a deletion's /dev/null header."""
        # Deletion hunks must not be attributed to the preceding changed file.
        diff = "+++ b/automation/example.yaml\n@@ -14 +14 @@\n+++ /dev/null\n@@ -1,14 +0,0 @@\n"
        with patch("tools.run_coverage.subprocess.run") as run:
            run.return_value.stdout = diff
            self.assertEqual(changed_lines("base"), {"automation/example.yaml": {14}})

    def test_gate_fails_uncovered_and_passes_covered_changes(self):
        """Exercise the CLI exit status independently of passing test results."""
        # Passing assertions alone cannot bypass uncovered changed opportunities.
        arguments = ["run_coverage.py", "--base", "base", "--thresholds", str(self.config),
                     "--output", str(self.root / "report")]
        with (patch("tools.run_coverage.ROOT", self.root),
              patch("tools.run_coverage.RECORDER", self.recorder),
              patch("tools.run_coverage.changed_lines", return_value={"automation/example.yaml": {14}}),
              patch("tools.run_coverage.unittest.defaultTestLoader.discover", return_value=unittest.TestSuite()),
              patch("tools.run_coverage.unittest.TextTestRunner") as runner,
              patch("sys.argv", arguments), redirect_stdout(io.StringIO())):
            runner.return_value.run.return_value = unittest.TestResult()
            self.assertEqual(main(), 1)
            for point in self.recorder.points.values():
                point.hits = 1
            self.assertEqual(main(), 0)
            failed = unittest.TestResult()
            failed.failures.append((self, "deliberate failure"))
            runner.return_value.run.return_value = failed
            self.assertEqual(main(), 1)

    def test_exact_thresholds_pass_and_each_gate_can_fail_independently(self):
        """Check inclusive 90/80 boundaries and independent action/branch gates."""
        # Integer cross-multiplication avoids passing a rounded-up below-threshold score.
        rows = ([dict(kind="action", hits=int(index < 9), changed=True) for index in range(10)]
                + [dict(kind="condition", hits=int(index < 8), changed=True) for index in range(10)])
        self.assertTrue(all(gate["passed"] for gate in evaluate_gates(rows, self.thresholds, True)))
        rows[0]["hits"] = 0
        gates = {gate["name"]: gate for gate in evaluate_gates(rows, self.thresholds, True)}
        self.assertFalse(gates["changed_actions"]["passed"])
        self.assertFalse(gates["overall_actions"]["passed"])
        self.assertTrue(gates["changed_branches"]["passed"])
        rows[0]["hits"] = 1
        rows[10]["hits"] = 0
        gates = {gate["name"]: gate for gate in evaluate_gates(rows, self.thresholds, True)}
        self.assertFalse(gates["changed_branches"]["passed"])
        self.assertFalse(gates["overall_branches"]["passed"])
        self.assertTrue(gates["overall_actions"]["passed"])

    def test_no_baseline_still_enforces_global_thresholds(self):
        """Manual/new-branch runs skip only changed gates, never overall gates."""
        # A missing baseline must not be a way to bypass the global quality gate.
        rows = [dict(kind="action", hits=0, changed=False),
                dict(kind="condition", hits=0, changed=False)]
        gates = {gate["name"]: gate for gate in evaluate_gates(rows, self.thresholds, False)}
        self.assertTrue(gates["changed_actions"]["passed"])
        self.assertIsNone(gates["changed_actions"]["percentage"])
        self.assertFalse(gates["overall_actions"]["passed"])
        self.assertFalse(gates["overall_branches"]["passed"])

    def test_display_rounding_cannot_bypass_threshold(self):
        """A score that rounds to the minimum still fails if it is actually lower."""
        # 8,999/10,000 displays as 90.0% to one decimal, but is below 90%.
        rows = [dict(kind="action", hits=int(index < 8999), changed=True)
                for index in range(10000)]
        gate = evaluate_gates(rows, {"overall_actions": 90}, False)[0]
        self.assertEqual(f"{gate['percentage']:.1f}", "90.0")
        self.assertFalse(gate["passed"])

    def test_invalid_threshold_configuration_fails_closed(self):
        """Reject missing gates, non-numeric values, invalid ranges, and NaN."""
        # Invalid configuration cannot silently lower or disable a threshold.
        for value in (-1, 101, True, "90", float("nan")):
            config = dict(self.thresholds, overall_actions=value)
            self.config.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_thresholds(self.config)
        self.config.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_thresholds(self.config)


if __name__ == "__main__":
    unittest.main()
