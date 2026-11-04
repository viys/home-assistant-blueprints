"""Repository-wide blueprint, runner, and coverage tests."""

from contextlib import redirect_stdout
from dataclasses import dataclass
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlparse

from jinja2 import Environment
import yaml

from tools.blueprint_coverage import Recorder
from tools.blueprint_runner import BlueprintRunner, ha_bool, is_number
from tools.run_coverage import (
    changed_lines, evaluate_gates, load_thresholds, main, metric, write_reports,
)


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class InputReference:
    """Keep !input references distinct from ordinary YAML strings."""

    name: str


class BlueprintLoader(yaml.SafeLoader):
    """Load HA input tags and reject silently overwritten YAML mapping keys."""

    def construct_mapping(self, node, deep=False):
        """Reject duplicate keys with a useful YAML source location."""
        # SafeLoader would otherwise keep only the last occurrence of a key.
        keys = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                raise yaml.constructor.ConstructorError(
                    "while reading a blueprint", node.start_mark,
                    f"duplicate key: {key}", key_node.start_mark,
                )
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def input_reference(loader, node):
    """Preserve each input name for declaration checks."""
    # Register on this loader only; unrelated YAML readers stay unchanged.
    return InputReference(loader.construct_scalar(node))


BlueprintLoader.add_constructor("!input", input_reference)


def walk(value):
    """Visit nested YAML values for input-reference and template checks."""
    # Include containers so callers can inspect values without reparsing YAML.
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


class BlueprintTests(unittest.TestCase):
    """Catch malformed YAML, broken inputs/templates, and stale catalogue paths."""

    @classmethod
    def setUpClass(cls):
        """Load every automation blueprint, failing if discovery finds none."""
        # Future vendor directories are automatically included.
        paths = sorted((ROOT / "automation").rglob("*.yaml"))
        if not paths:
            raise AssertionError("No automation blueprints discovered")
        cls.documents = {
            path: yaml.load(path.read_text(encoding="utf-8"), Loader=BlueprintLoader)
            for path in paths
        }

    def test_blueprint_structure(self):
        """Require usable automation metadata and nonempty trigger/action lists."""
        # This checks repository contracts, not the complete Home Assistant schema.
        for path, document in self.documents.items():
            with self.subTest(blueprint=path.name):
                self.assertIsInstance(document, dict)
                blueprint = document["blueprint"]
                for field in ("name", "author", "description"):
                    self.assertIsInstance(blueprint[field], str)
                    self.assertTrue(blueprint[field].strip())
                self.assertEqual(blueprint["domain"], "automation")
                self.assertIsInstance(blueprint["input"], dict)
                for field in ("triggers", "actions"):
                    self.assertIsInstance(document[field], list)
                    self.assertTrue(document[field])
                self.assertIn(document.get("mode", "single"),
                              ("single", "restart", "queued", "parallel"))
                minimum = blueprint.get("homeassistant", {}).get("min_version")
                if minimum is not None:
                    self.assertRegex(str(minimum), r"^\d{4}\.\d{1,2}\.\d+$")

    def test_each_blueprint_has_one_dedicated_test_file(self):
        """Require matching test names and catch stale or extra test modules."""
        expected = {f"test_{path.stem}.py" for path in self.documents}
        self.assertEqual(len(expected), len(self.documents), "Blueprint stems must be unique")
        # Shared tests have their own directory; all other tests must match blueprints.
        tests = ROOT / "tests"
        actual = {path.relative_to(tests).as_posix() for path in tests.rglob("test_*.py")
                  if not path.is_relative_to(tests / "common")}
        self.assertEqual(actual, expected)

    def test_input_references_are_declared(self):
        """Catch misspelled or removed inputs used anywhere in a blueprint."""
        # Input section groups may contain nested input declarations.
        for path, document in self.documents.items():
            declared = set(document["blueprint"]["input"])
            for item in walk(document["blueprint"]["input"]):
                if isinstance(item, dict) and isinstance(item.get("input"), dict):
                    declared.update(item["input"])
            for item in walk(document):
                if isinstance(item, InputReference):
                    with self.subTest(blueprint=path.name, input=item.name):
                        self.assertIn(item.name, declared)

    def test_template_syntax(self):
        """Parse every Jinja template without pretending to provide HA runtime state."""
        # Parsing catches syntax errors while allowing HA-specific functions/filters.
        environment = Environment()
        for path, document in self.documents.items():
            for value in walk(document):
                if isinstance(value, str) and any(tag in value for tag in ("{{", "{%", "{#")):
                    with self.subTest(blueprint=path.name, template=value[:100]):
                        environment.parse(value)

    def test_readme_catalogue_matches_files(self):
        """Verify master import badges and both branches' raw links."""
        # Compare decoded paths, including each URL-encoded blueprint_url parameter.
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        expected = {path.relative_to(ROOT).as_posix() for path in self.documents}
        imports = {branch: set() for branch in ("master", "dev")}
        raw_links = {branch: set() for branch in ("master", "dev")}
        for url in re.findall(r'https://[^\s"<>\)]+', text):
            parsed = urlparse(url)
            if parsed.netloc == "my.home-assistant.io":
                for source in parse_qs(parsed.query).get("blueprint_url", []):
                    source_url = urlparse(source)
                    self.assertEqual(source_url.netloc, "github.com")
                    for branch in imports:
                        prefix = f"/viys/home-assistant-blueprints/blob/{branch}/"
                        if source_url.path.startswith(prefix):
                            imports[branch].add(unquote(source_url.path[len(prefix):]))
                            break
                    else:
                        self.fail(f"Unexpected blueprint import URL: {source}")
            elif parsed.netloc == "raw.githubusercontent.com":
                for branch in raw_links:
                    prefix = f"/viys/home-assistant-blueprints/{branch}/"
                    if parsed.path.startswith(prefix):
                        raw_links[branch].add(unquote(parsed.path[len(prefix):]))
                        break
                else:
                    self.fail(f"Unexpected raw YAML URL: {url}")
        for branch in imports:
            with self.subTest(branch=branch):
                self.assertEqual(imports[branch], expected if branch == "master" else set())
                self.assertEqual(raw_links[branch], expected)

    def test_duplicate_yaml_keys_are_rejected(self):
        """Ensure malformed mappings cannot produce a misleading passing check."""
        # A duplicate top-level key must fail instead of hiding earlier definitions.
        with self.assertRaises(yaml.constructor.ConstructorError):
            yaml.load("mode: queued\nmode: parallel\n", Loader=BlueprintLoader)


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


HARNESS = r"""
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const calls = [];
const messages = [];
const outputs = {};
const requests = [];
// Record API writes without issuing any network request.
const record = kind => async params => { calls.push({kind, ...params}); };
const github = {
  paginate: async (method, params) => {
    requests.push(params);
    return method === github.rest.actions.listWorkflowRunArtifacts ? input.artifacts : input.comments;
  },
  rest: {
    actions: {listWorkflowRunArtifacts: async () => {}},
    issues: {
      listComments: async () => {},
      createComment: record('create'), updateComment: record('update'),
    },
    pulls: {get: async () => ({data: {state: input.state, head: {sha: input.currentSha}}})},
  },
};
const context = {repo: {owner: 'owner', repo: 'repo'}, runId: 101,
  payload: {pull_request: {number: 12, head: {sha: 'abc123'}}}};
const core = {info: message => messages.push(message), warning: message => messages.push(message),
  setOutput: (key, value) => { outputs[key] = value; }};
const fakeRequire = name => {
  // Report artifacts are data only; the script must not import executable code.
  if (name !== 'node:fs') throw Error('Unexpected module: ' + name);
  return {existsSync: () => input.hasReport,
    readFileSync: () => input.rawReport ?? JSON.stringify(input.report)};
};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github', 'context', 'core', 'require', 'process', input.script)(
  github, context, core, fakeRequire, {env: {
    GITHUB_SERVER_URL: 'https://github.com', COVERAGE_RESULT: input.result,
    REPORT_ARTIFACT_ID: input.artifactId,
  }}
).then(() => process.stdout.write(JSON.stringify({calls, messages, outputs, requests})))
 .catch(error => { console.error(error); process.exitCode = 1; });
"""


class CoverageCommentTests(unittest.TestCase):
    """Validate bot-comment behavior without posting comments or requiring a token."""

    @classmethod
    def setUpClass(cls):
        """Load the exact inline JavaScript that GitHub Actions will execute."""
        # Python-only local environments can skip these checks; hosted CI has Node.
        cls.node = shutil.which("node")
        if cls.node is None:
            raise unittest.SkipTest("Node.js is required for workflow comment-script tests")
        cls.workflow = yaml.safe_load((ROOT / ".github/workflows/pr.yml").read_text(encoding="utf-8"))
        steps = cls.workflow["jobs"]["coverage-comment"]["steps"]
        step = next(step for step in steps if step["name"] == "Create or update coverage comment")
        cls.script = step["with"]["script"]
        cls.lookup_script = next(step for step in steps if step["name"] == "Find coverage report")["with"]["script"]

    def scenario(self, **overrides):
        """Execute one isolated API scenario and return captured create/update calls."""
        # Pass JSON through stdin, never through shell-expanded command text.
        branch_hits = overrides.pop("branch_hits", 92)
        report = dict(tests_passed=True, tests_run=62, coverage_passed=branch_hits >= 80,
                      changed_files=["automation/sonoff/example.yaml"],
                      gates=[dict(name=name, covered=covered, total=total,
                                  percentage=covered * 100 / total if total else None,
                                  minimum=minimum, passed=not total or covered * 100 >= total * minimum)
                             for name, covered, total, minimum in (
                                 ("changed_actions", 17, 17, 90), ("changed_branches", 26, 26, 80),
                                 ("overall_actions", 49, 49, 90), ("overall_branches", branch_hits, 100, 80))],
                      opportunities=[dict(file="automation/sonoff/example.yaml", kind="action", hits=1)
                                     for _ in range(49)]
                      + [dict(file="automation/sonoff/example.yaml", kind="condition", hits=int(index < branch_hits))
                         for index in range(100)])
        data = dict(script=self.script, comments=[], artifacts=[], state="open", currentSha="abc123",
                    hasReport=True, report=report,
                    result="success", artifactId="42")
        data.update(overrides)
        result = subprocess.run([self.node, "-e", HARNESS], input=json.dumps(data),
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_creates_report_with_commit_status_and_links(self):
        """A first run publishes a marked report in the correct PR."""
        # The marker allows subsequent runs to find and update the same bot comment.
        call = self.scenario()["calls"][0]
        self.assertEqual((call["kind"], call["issue_number"]), ("create", 12))
        self.assertIn("<!-- blueprint-simulated-coverage -->", call["body"])
        self.assertIn("abc123", call["body"])
        self.assertIn("**PASS**", call["body"])
        self.assertIn("Project coverage: actions **100.0%**, branches **92.0%**", call["body"])
        self.assertIn("<details>", call["body"])
        self.assertIn("```diff", call["body"])
        self.assertLess(len(call["body"].split("<details>")[0]), 750)
        self.assertNotIn("Full HTML/JSON report", call["body"])
        self.assertNotIn("Workflow run", call["body"])
        self.assertNotIn("| Blueprint |", call["body"])

    def test_updates_only_its_own_existing_bot_comment(self):
        """Do not edit human comments even when they contain the report marker."""
        # A copied marker is insufficient without the expected bot identity.
        marker = "<!-- blueprint-simulated-coverage -->"
        comments = [dict(id=1, user={"login": "owner"}, body=marker),
                    dict(id=2, user={"login": "github-actions[bot]"}, body=marker)]
        calls = self.scenario(comments=comments)["calls"]
        self.assertEqual(len(calls), 1)
        self.assertEqual((calls[0]["kind"], calls[0]["comment_id"]), ("update", 2))

    def test_failure_still_publishes_report(self):
        """Coverage gate failure is visible rather than suppressing the comment."""
        # Report publication must not make a failing coverage job appear passed.
        body = self.scenario(result="failure", branch_hits=70)["calls"][0]["body"]
        self.assertIn("**FAIL**", body)
        self.assertIn("70.0%", body)
        self.assertIn("❌ Project coverage", body)

    def test_missing_report_posts_diagnostic(self):
        """Setup failure before report creation still gets a useful PR update."""
        # Do not invent a successful coverage percentage when no artifact exists.
        body = self.scenario(result="failure", hasReport=False, artifactId="")["calls"][0]["body"]
        self.assertIn("report unavailable", body)
        self.assertIn("**FAIL**", body)
        self.assertIn("https://github.com/owner/repo/actions/runs/101", body)
        self.assertNotIn("Full HTML/JSON report", body)

    def test_outdated_commit_and_closed_pr_are_not_updated(self):
        """Prevent old workflow runs from replacing current PR reports."""
        # A completed older run must not overwrite a newer commit's comment.
        for override in (dict(currentSha="new-head"), dict(state="closed")):
            result = self.scenario(**override)
            self.assertEqual(result["calls"], [])
            self.assertTrue(result["messages"])

    def test_large_changed_report_is_bounded(self):
        """Keep changed-file details under the API size limit."""
        # Artifact data remains complete even when the inline summary is shortened.
        report = dict(tests_passed=True, tests_run=1, gates=[], opportunities=[
            dict(file=f"automation/{index}-" + "x" * 1000 + ".yaml", kind="action", hits=0, changed=True)
            for index in range(1000)])
        body = self.scenario(report=report)["calls"][0]["body"]
        self.assertLess(len(body), 65536)
        self.assertIn("950 more changed blueprints", body)
        self.assertNotIn("Full HTML/JSON report", body)

    def test_empty_changed_denominator_remains_not_applicable(self):
        """Do not display a perfect changed percentage when no changed paths exist."""
        # Missing baseline/opportunities must remain visually distinct from 100%.
        report = dict(tests_passed=True, tests_run=1, gates=[
            dict(name=name, covered=0, total=0, percentage=None, minimum=90, passed=True)
            for name in ("changed_actions", "changed_branches")], opportunities=[])
        body = self.scenario(report=report)["calls"][0]["body"]
        self.assertIn("Changed coverage: actions **N/A**, branches **N/A**", body)
        self.assertNotIn("100.0%", body)

    def test_only_changed_blueprints_have_file_details(self):
        """Keep unrelated blueprints out of the PR's file list."""
        # Explicit changed paths also retain files changed only outside measured blocks.
        report = dict(tests_passed=True, tests_run=1, gates=[],
                      changed_files=["automation/sonoff/mine.yaml"], opportunities=[
                          dict(file="automation/sonoff/mine.yaml", kind="action", hits=1),
                          dict(file="automation/sonoff/other.yaml", kind="action", hits=0)])
        body = self.scenario(report=report)["calls"][0]["body"]
        self.assertIn("`mine.yaml`", body)
        self.assertNotIn("other.yaml", body)
        report["changed_files"] = []
        body = self.scenario(report=report)["calls"][0]["body"]
        self.assertNotIn("Changed blueprints", body)
        self.assertNotIn("mine.yaml", body)

    def test_invalid_json_uses_diagnostic_instead_of_partial_metrics(self):
        """A malformed report does not prevent an informative comment update."""
        # Corrupt JSON must not fabricate numbers or break the whole publishing step.
        result = self.scenario(result="failure", rawReport="{broken")
        self.assertIn("report unavailable", result["calls"][0]["body"])
        self.assertTrue(result["messages"])

    def test_write_permissions_are_isolated_from_test_execution(self):
        """Only the no-checkout comment job receives PR write permission."""
        # The test-producing jobs retain the workflow's read-only token permissions.
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        job = self.workflow["jobs"]["coverage-comment"]
        self.assertEqual(job["permissions"], {"actions": "read", "pull-requests": "write"})
        self.assertEqual(job["needs"], "checks")
        self.assertIn("head.repo.full_name == github.repository", job["if"])
        self.assertFalse(any("checkout@" in step.get("uses", "") for step in job["steps"]))

    def test_push_and_pr_entries_share_checks_without_skipped_push_comment(self):
        """Push runs contain only checks; PR runs add their own comment task."""
        # A separate workflow entry removes the irrelevant comment job from push runs.
        workflows = {name: yaml.load((ROOT / f".github/workflows/{name}.yml").read_text(encoding="utf-8"),
                                    Loader=yaml.BaseLoader) for name in ("ci", "pr", "checks")}
        self.assertEqual(set(workflows["ci"]["on"]), {"push"})
        self.assertEqual(set(workflows["pr"]["on"]), {"pull_request"})
        self.assertEqual(set(workflows["checks"]["on"]), {"workflow_call"})
        self.assertNotIn("coverage-comment", workflows["ci"]["jobs"])
        self.assertNotIn("coverage-comment", workflows["checks"]["jobs"])
        for name in ("ci", "pr"):
            self.assertEqual(workflows[name]["jobs"]["checks"]["uses"], "./.github/workflows/checks.yml")
        self.assertEqual(workflows["ci"]["jobs"]["checks"]["with"]["base-sha"], "${{ github.event.before }}")
        self.assertEqual(workflows["pr"]["jobs"]["checks"]["with"]["base-sha"], "${{ github.event.pull_request.base.sha }}")

    def test_report_lookup_uses_current_run_and_latest_nonexpired_artifact(self):
        """Failure of reusable checks must not prevent finding their uploaded report."""
        # The comment job consumes only known report data from its own workflow run.
        result = self.scenario(script=self.lookup_script, artifacts=[
            dict(id=10, name="other", expired=False),
            dict(id=20, name="blueprint-coverage", expired=False),
            dict(id=30, name="blueprint-coverage", expired=True),
            dict(id=25, name="blueprint-coverage", expired=False)])
        self.assertEqual(result["outputs"], {"artifact-id": "25"})
        self.assertEqual(result["requests"][0]["run_id"], 101)
        self.assertEqual(self.scenario(script=self.lookup_script)["outputs"], {"artifact-id": ""})


if __name__ == "__main__":
    unittest.main()
