# Release a tagged version

Contributions enter the default `dev` branch through pull requests, using
**Squash and merge**. A stable version tag triggers validation and moves
`master` to the same tested commit. No new commit is created during release.

## Repository settings

- Keep `dev` protected: require PRs, the six existing CI checks, Squash only,
  linear history, no bypass actors, no force pushes, and no deletion.
- On `master`, keep linear history, the six CI checks, no bypass actors,
  no force pushes, and no deletion. Remove **Require a pull request before
  merging** and the **Master PR source** check. Fast-forward publication is a
  direct branch update, so a PR-only rule would reject the built-in token.
  This also means other authorized writers can update `master` when its
  remaining protections are satisfied; it is not restricted to the release job.
  The previous `master-source.yml` PR-only workflow is retired by this flow.
- In the `github-pages` environment, allow the `master` and `dev` branches and
  tags matching `v*`. Tag-triggered Pages jobs run in the tag's environment
  context, even after they advance `master`.
- The workflow uses GitHub's built-in `GITHUB_TOKEN`; no PAT, GitHub App, or
  user-created secret is needed. Only the promotion job receives `contents: write`.

Do not squash `dev` into `master`, merge `master` back into `dev`, or reset either
branch as part of a release. If their histories diverge or include new merge
commits, publication stops. Resolve the history separately after reviewing it.

## Create a stable version tag

After the desired changes are merged into `dev`, run:

```powershell
git fetch origin
git tag -a v1.0.0 origin/dev -m "Release v1.0.0"
git push origin refs/tags/v1.0.0
```

Replace `v1.0.0` with the next unused version. Only stable `vMAJOR.MINOR.PATCH`
tags are supported; prerelease tags such as `v1.0.0-rc.1` fail validation and
cannot update `master`. Maintainers should create version tags only from
reviewed commits. Do not move an existing tag to another commit.

Open **Actions > Release tagged version**. The workflow:

1. Resolves the tag to a commit, verifies it belongs to remote `dev`, and checks
   that remote `master` can advance without adding merge commits.
2. Runs the reusable blueprint checks, Python 3.11–3.14 tests, simulated YAML
   coverage against the captured `master` baseline, and production docs build.
3. Rechecks the remote tag, development history, and unchanged stable baseline,
   then pushes the exact tested SHA to `master` without `--force`.
4. Deploys the Pages artifact already built from that tag in the same run.

Both lightweight and annotated tags are supported. If `dev` advances during
validation, the release still publishes the tagged snapshot, not newer commits.
The two branch tips are identical only when `dev` still points at that snapshot.
The workflow does not create a GitHub Release entry or upload release binaries.

GitHub does not normally trigger new `push` workflows for a push made using
`GITHUB_TOKEN`. Therefore this flow runs CI before promotion and deploys the
validated Pages artifact explicitly afterwards. Do not rely on another
`master` push event to run these tasks.

If validation fails, `master` stays unchanged. If Pages fails after promotion,
`master` remains at the released commit; fix the environment/deployment issue
and rerun the failed job. If the baseline, tag, or dev history changes, rerun
all jobs so the release is checked again against fresh refs.

Sources: [GitHub token workflow triggering](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
and [Git fast-forward behavior](https://git-scm.com/docs/git-merge#_fast_forward_merge).

## Offline validation

```powershell
python -m unittest tests.common.test_release_master -v
python -m unittest discover -s tests -v
npm run build --prefix docs
python tools/check_site.py docs/dist
```

Release tests use disposable local bare repositories; they never write to
the real repository. To inspect a real tag without publishing:

```powershell
python -m tools.release_master --tag v1.0.0 --candidate <full_commit_sha>
```

This refreshes local remote-tracking refs but does not push. The privileged
workflow adds `--expected-master <validated_baseline_sha> --push` only after
all validation jobs pass. Real protected-branch token publication still needs
an end-to-end GitHub run after this workflow is merged into `dev`.
