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
// Record API writes without issuing any network request.
const record = kind => async params => { calls.push({kind, ...params}); };
const github = {
  paginate: async () => input.comments,
  rest: {
    issues: {
      listComments: async () => {},
      createComment: record('create'), updateComment: record('update'),
    },
    pulls: {get: async () => ({data: {state: input.state, head: {sha: input.currentSha}}})},
  },
};
const context = {repo: {owner: 'owner', repo: 'repo'}, runId: 101,
  payload: {pull_request: {number: 12, head: {sha: 'abc123'}}}};
const core = {info: message => messages.push(message)};
const fakeRequire = name => {
  // Report artifacts are data only; the script must not import executable code.
  if (name !== 'node:fs') throw Error('Unexpected module: ' + name);
  return {existsSync: () => input.hasReport, readFileSync: () => input.summary};
};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github', 'context', 'core', 'require', 'process', input.script)(
  github, context, core, fakeRequire, {env: {
    GITHUB_SERVER_URL: 'https://github.com', COVERAGE_RESULT: input.result,
    REPORT_ARTIFACT_ID: input.artifactId,
  }}
).then(() => process.stdout.write(JSON.stringify({calls, messages})))
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
        cls.workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        step = next(step for step in cls.workflow["jobs"]["coverage-comment"]["steps"] if "script" in step.get("with", {}))
        cls.script = step["with"]["script"]

    def scenario(self, **overrides):
        """Execute one isolated API scenario and return captured create/update calls."""
        # Pass JSON through stdin, never through shell-expanded command text.
        data = dict(script=self.script, comments=[], state="open", currentSha="abc123",
                    hasReport=True, summary="# Simulated coverage\nActions: 100%\nBranches: 92%",
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
        self.assertIn("Actions: 100%", call["body"])
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
        body = self.scenario(result="failure", summary="Overall branches: 70% (FAIL)")["calls"][0]["body"]
        self.assertIn("**FAIL**", body)
        self.assertIn("70%", body)

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
        body = self.scenario(summary="x" * 100000)["calls"][0]["body"]
        self.assertLess(len(body), 65536)
        self.assertIn("Report truncated", body)
        self.assertIn("Full HTML/JSON report", body)

    def test_write_permissions_are_isolated_from_test_execution(self):
        """Only the no-checkout comment job receives PR write permission."""
        # The test-producing jobs retain the workflow's read-only token permissions.
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        job = self.workflow["jobs"]["coverage-comment"]
        self.assertEqual(job["permissions"], {"actions": "read", "pull-requests": "write"})
        self.assertEqual(job["needs"], "coverage")
        self.assertIn("head.repo.full_name == github.repository", job["if"])
        self.assertFalse(any("checkout@" in step.get("uses", "") for step in job["steps"]))

    def test_workflow_runs_only_on_pull_requests(self):
        """Prevent duplicate push runs and their skipped PR-comment jobs."""
        # BaseLoader preserves the YAML key 'on' rather than coercing it to True.
        workflow = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        self.assertEqual(set(workflow["on"]), {"pull_request"})


if __name__ == "__main__":
    unittest.main()
