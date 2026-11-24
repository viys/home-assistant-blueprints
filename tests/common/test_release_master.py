"""Exercise fast-forward releases against disposable local Git remotes."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

import yaml

from tools.release_master import git, main, release_plan


ROOT = Path(__file__).resolve().parents[2]


class ReleaseMasterTests(unittest.TestCase):
    """Reject unsafe tag promotions without contacting the real repository."""

    def setUp(self):
        """Create a bare origin and one seed repository with aligned branches."""
        # Every test owns its remote, branch history, author identity, and working tree.
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.remote = self.root / "origin.git"
        self.repo = self.root / "work"
        git(self.root, "init", "--bare", str(self.remote))
        git(self.root, "clone", str(self.remote), str(self.repo))
        git(self.repo, "config", "user.name", "Release Test")
        git(self.repo, "config", "user.email", "release@example.invalid")
        git(self.repo, "checkout", "-b", "master")
        self.base = self.commit("baseline")
        git(self.repo, "push", "origin", "master")
        git(self.repo, "checkout", "-b", "dev")
        git(self.repo, "push", "origin", "dev")

    def commit(self, text):
        """Create one ordinary commit and return its exact object ID."""
        # A changing file makes the tree differ without depending on commit timestamps.
        (self.repo / "content.txt").write_text(text, encoding="utf-8")
        git(self.repo, "add", "--", "content.txt")
        git(self.repo, "commit", "-m", text)
        return git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def candidate(self, annotated=False):
        """Publish a candidate on dev and a stable version tag to the test origin."""
        # Cover both tag forms used by git tag and the GitHub release interface.
        sha = self.commit("release candidate")
        git(self.repo, "push", "origin", "dev")
        if annotated:
            git(self.repo, "tag", "-a", "v1.0.0", "-m", "Version 1.0.0")
        else:
            git(self.repo, "tag", "v1.0.0")
        git(self.repo, "push", "origin", "refs/tags/v1.0.0")
        return sha

    def test_dry_run_then_push_preserves_candidate_sha(self):
        """Planning does not publish, and a successful push creates no new commit."""
        # Verify the remote directly rather than only asserting subprocess arguments.
        sha = self.candidate()
        plan = release_plan(self.repo, "v1.0.0", sha)
        self.assertEqual(plan["master"], self.base)
        self.assertEqual(git(self.root, "--git-dir", str(self.remote), "rev-parse", "master").stdout.strip(), self.base)
        output = self.root / "outputs"
        with redirect_stdout(io.StringIO()):
            result = main(["--repository", str(self.repo), "--tag", "v1.0.0", "--candidate", sha,
                           "--expected-master", self.base, "--push", "--github-output", str(output)])
        self.assertEqual(result, 0)
        self.assertEqual(git(self.root, "--git-dir", str(self.remote), "rev-parse", "master").stdout.strip(), sha)
        self.assertIn(f"candidate={sha}\n", output.read_text(encoding="utf-8"))

    def test_annotated_tag_resolves_to_the_commit(self):
        """Annotated tag objects must not be mistaken for their commit IDs."""
        # ls-remote's peeled tag is the release candidate that checks actually execute.
        sha = self.candidate(annotated=True)
        self.assertEqual(release_plan(self.repo, "v1.0.0", sha)["candidate"], sha)

    def test_tag_must_still_match_the_tested_sha(self):
        """Reject a different commit even if it is valid dev history."""
        # No tag update or force push is used in the test or the implementation.
        self.candidate()
        with self.assertRaisesRegex(ValueError, "remote tag"):
            release_plan(self.repo, "v1.0.0", self.base)

    def test_tag_outside_dev_is_rejected(self):
        """A stable-looking tag on another branch cannot publish master."""
        # The candidate is known locally but deliberately absent from origin/dev.
        sha = self.commit("unreviewed commit")
        git(self.repo, "tag", "v1.0.0")
        git(self.repo, "push", "origin", "refs/tags/v1.0.0")
        with self.assertRaisesRegex(ValueError, "dev's history"):
            release_plan(self.repo, "v1.0.0", sha)

    def test_diverged_master_is_rejected(self):
        """Preserve stable changes that are not contained in the release candidate."""
        # Advancing master on a different tree makes an ordinary push non-fast-forward.
        sha = self.candidate()
        git(self.repo, "checkout", "master")
        self.commit("independent stable change")
        git(self.repo, "push", "origin", "master")
        with self.assertRaisesRegex(ValueError, "cannot fast-forward"):
            release_plan(self.repo, "v1.0.0", sha)

    def test_changed_baseline_stops_a_previously_checked_release(self):
        """Require another validation pass when master moves during CI."""
        # Even an otherwise valid fast-forward must use the same tested coverage baseline.
        sha = self.candidate()
        git(self.repo, "push", "origin", f"{sha}:refs/heads/master")
        with self.assertRaisesRegex(ValueError, "master changed"):
            release_plan(self.repo, "v1.0.0", sha, self.base)

    def test_merge_commit_cannot_enter_master(self):
        """Fast-forward eligibility alone is insufficient for a linear-history release."""
        # Create a non-conflicting merge whose second parent is not on master.
        git(self.repo, "checkout", "-b", "topic")
        self.commit("topic change")
        git(self.repo, "checkout", "dev")
        git(self.repo, "merge", "--no-ff", "topic", "-m", "merge topic")
        sha = git(self.repo, "rev-parse", "HEAD").stdout.strip()
        git(self.repo, "push", "origin", "dev")
        git(self.repo, "tag", "v1.0.0")
        git(self.repo, "push", "origin", "refs/tags/v1.0.0")
        with self.assertRaisesRegex(ValueError, "merge commits"):
            release_plan(self.repo, "v1.0.0", sha)

    def test_invalid_tag_and_candidate_are_rejected_before_git(self):
        """Only stable semantic versions and full GitHub commit SHAs are accepted."""
        # Prerelease tags must never silently promote the stable download branch.
        for tag in ("v1.0.0-rc.1", "v01.0.0", "v1.0", "latest"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release_plan(self.repo, tag, self.base)
        with self.assertRaisesRegex(ValueError, "full commit SHA"):
            release_plan(self.repo, "v1.0.0", "HEAD")

    def test_cli_failure_does_not_write_github_outputs(self):
        """Failed plans cannot make dependent publication jobs look ready."""
        # CI outputs only exist after every ancestry and tag check succeeds.
        output = self.root / "outputs"
        with redirect_stderr(io.StringIO()):
            result = main(["--repository", str(self.repo), "--tag", "v1.0.0-rc.1",
                           "--candidate", self.base, "--github-output", str(output)])
        self.assertEqual(result, 1)
        self.assertFalse(output.exists())


class ReleaseWorkflowTests(unittest.TestCase):
    """Keep publication behind tag validation, full CI, and read-only documentation builds."""

    def test_only_stable_tag_flow_can_reach_the_write_job(self):
        """Check the event and job dependency boundary for the privileged promotion."""
        # BaseLoader preserves GitHub Actions' on key and literal permission values.
        workflow = yaml.load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        self.assertEqual(workflow["on"], {"push": {"tags": ["v*"]}})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        jobs = workflow["jobs"]
        self.assertEqual(set(jobs["promote"]["needs"]), {"inspect", "checks", "manual"})
        self.assertEqual(jobs["promote"]["permissions"], {"contents": "write"})
        self.assertEqual(jobs["checks"]["uses"], "./.github/workflows/checks.yml")
        self.assertEqual(jobs["manual"]["uses"], "./.github/workflows/manual-build.yml")
        self.assertEqual(set(jobs["deploy"]["needs"]), {"promote", "manual"})


if __name__ == "__main__":
    unittest.main()
