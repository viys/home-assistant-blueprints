"""Validate a stable release tag and optionally fast-forward master without rewriting commits."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys


def git(repository, *arguments, check=True):
    """Run Git with argument boundaries preserved and capture diagnostics."""
    # Never invoke a shell or interpolate a revision into executable command text.
    try:
        return subprocess.run(["git", *arguments], cwd=repository, check=check,
                              capture_output=True, text=True, encoding="utf-8", timeout=120)
    except subprocess.CalledProcessError as error:
        error.add_note(error.stderr.strip())
        raise


def release_plan(repository, tag, candidate, expected_master=None):
    """Resolve fresh remote refs and reject releases that cannot preserve linear history."""
    # Stable tags only: prereleases and arbitrary Git revision expressions must not publish master.
    if not re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", tag):
        raise ValueError("Use a stable version tag such as v1.2.3.")
    if not re.fullmatch(r"[0-9a-f]{40}", candidate):
        raise ValueError("The candidate must be a full commit SHA.")
    git(repository, "fetch", "--no-tags", "origin",
        "refs/heads/dev:refs/remotes/origin/dev",
        "refs/heads/master:refs/remotes/origin/master")
    master = git(repository, "rev-parse", "refs/remotes/origin/master").stdout.strip()
    if expected_master is not None and master != expected_master:
        raise ValueError("master changed after validation; rerun the release to validate the new baseline.")
    tag_ref = f"refs/tags/{tag}"
    remote_tags = dict(line.split()[::-1] for line in
                       git(repository, "ls-remote", "origin", tag_ref, tag_ref + "^{}").stdout.splitlines())
    if remote_tags.get(tag_ref + "^{}", remote_tags.get(tag_ref)) != candidate:
        raise ValueError("The remote tag no longer identifies the validated candidate.")
    if git(repository, "merge-base", "--is-ancestor", candidate,
           "refs/remotes/origin/dev", check=False).returncode != 0:
        raise ValueError("The release tag must identify a commit in dev's history.")
    if git(repository, "merge-base", "--is-ancestor", master, candidate, check=False).returncode != 0:
        raise ValueError("master cannot fast-forward to this tag; no reset or force push will be attempted.")
    if git(repository, "rev-list", "--merges", f"{master}..{candidate}").stdout.strip():
        raise ValueError("The release would introduce merge commits into master.")
    return {"candidate": candidate, "master": master, "tag": tag}


def main(argv=None):
    """Plan by default; push only after explicit approval through the --push argument."""
    # The workflow runs the read-only plan before checks and repeats it in the write job.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--expected-master")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args(argv)
    if args.push and args.expected_master is None:
        parser.error("--push requires the --expected-master SHA captured before validation")
    try:
        plan = release_plan(args.repository, args.tag, args.candidate, args.expected_master)
        if args.push:
            git(args.repository, "push", "origin", f"{plan['candidate']}:refs/heads/master")
            published = git(args.repository, "ls-remote", "origin", "refs/heads/master").stdout.split()[0]
            if published != plan["candidate"]:
                raise ValueError("master changed before publication could be confirmed.")
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as output:
                output.write(f"candidate={plan['candidate']}\nmaster={plan['master']}\n")
        print(json.dumps(plan))
        return 0
    except (ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(f"Release stopped: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
