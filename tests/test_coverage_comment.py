"""Run the real workflow comment script against mocked GitHub and filesystem APIs."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
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
        self.assertIn("https://github.com/owner/repo/actions/runs/101/artifacts/42", call["body"])

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

    def test_missing_report_posts_diagnostic_and_workflow_link(self):
        """Setup failure before report creation still gets a useful PR update."""
        # Do not invent a successful coverage percentage when no artifact exists.
        body = self.scenario(result="failure", hasReport=False, artifactId="")["calls"][0]["body"]
        self.assertIn("report unavailable", body)
        self.assertIn("**FAIL**", body)
        self.assertIn("Workflow run", body)
        self.assertNotIn("Full HTML/JSON report", body)

    def test_outdated_commit_and_closed_pr_are_not_updated(self):
        """Prevent old workflow runs from replacing current PR reports."""
        # A completed older run must not overwrite a newer commit's comment.
        for override in (dict(currentSha="new-head"), dict(state="closed")):
            result = self.scenario(**override)
            self.assertEqual(result["calls"], [])
            self.assertTrue(result["messages"])

    def test_large_report_is_bounded_and_retains_download_link(self):
        """Keep comments under the API size limit with a complete-report link."""
        # Artifact data remains complete even when the inline summary is shortened.
        report = dict(tests_passed=True, tests_run=1, gates=[], opportunities=[
            dict(file=f"automation/{index}-" + "x" * 1000 + ".yaml", kind="action", hits=0)
            for index in range(1000)])
        body = self.scenario(report=report)["calls"][0]["body"]
        self.assertLess(len(body), 65536)
        self.assertIn("More files in the full report", body)
        self.assertIn("Full HTML/JSON report", body)

    def test_empty_changed_denominator_remains_not_applicable(self):
        """Do not display a perfect changed percentage when no changed paths exist."""
        # Missing baseline/opportunities must remain visually distinct from 100%.
        report = dict(tests_passed=True, tests_run=1, gates=[
            dict(name=name, covered=0, total=0, percentage=None, minimum=90, passed=True)
            for name in ("changed_actions", "changed_branches")], opportunities=[])
        body = self.scenario(report=report)["calls"][0]["body"]
        self.assertIn("Changed coverage: actions **N/A**, branches **N/A**", body)
        self.assertNotIn("100.0%", body)

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
