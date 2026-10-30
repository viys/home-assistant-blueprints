# Blueprint tests and CI

The repository separates test cases, tools, and configuration:

```text
tests/                    Test cases and test instructions
tools/                    Coverage collection and report generation
config/testing/           Test dependencies and coverage thresholds
.github/workflows/        GitHub Actions workflows
```

Requires Python 3.11 or newer. From the repository root:

```powershell
python -m pip install -r config/testing/requirements.txt
python -m unittest discover -s tests -v
git diff --check
```

Workflow comment-script tests also use Node.js when available. GitHub-hosted
CI runners provide Node; Python-only local environments skip those checks.

## GitHub Actions

The `CI` workflow runs on pushes, pull requests, and manual dispatch. It shows
these checks in the pull request:

- `Blueprint validation`: checks every blueprint's YAML, duplicate keys,
  required structure, declared input references, Jinja syntax, and README
  import/raw-download paths.
- `Unit tests (Python 3.11)` through `Unit tests (Python 3.14)`: runs the whole
  test suite independently on each Python version.
- `Simulated YAML coverage`: records executed action blocks and branch outcomes,
  publishes a job summary, and uploads the `blueprint-coverage` report artifact.
- `PR coverage report`: creates or updates one bot comment with the coverage
  summary, threshold results, tested commit, and full report download link.

Automatic comments run for pull requests from branches in this repository,
including when coverage gates fail. Fork pull requests retain the read-only
test jobs, job summary, and report artifact; they skip automatic comments
because their standard workflow token cannot write PR comments. No personal
access token is required. Test jobs keep read-only permissions; a separate job
publishes report data without checking out or executing the test code.

To run manually after the workflow is pushed, open **Actions → CI → Run workflow**.
To require passing checks before merging, configure a ruleset or branch
protection rule in GitHub repository settings after the check names have
appeared in a run. Adding this workflow alone does not make checks required.

Add new files named `test_*.py` under `tests/`; discovery includes them
automatically. Tests run offline without Home Assistant credentials or devices.

## Adding tests

- Keep tests independent and runnable without network access or a live device.
- Read the actual blueprint YAML when checking its behavior.
- Cover relevant normal, invalid-input, and failure cases.
- Keep device-specific scenarios and limitations with their corresponding tests.

Behavior tests share `tools/blueprint_runner.py` to load and execute the actual
YAML and record coverage at action/condition/choice execution sites. Fixtures
provide explicit states, devices, and mocked service outcomes; assertions must
check values, destinations, ordering, and skipped calls. Keep blueprint-specific
scheduling models separate from this shared sequential executor.

## Simulated YAML coverage

Run the suite and generate reports locally:

```powershell
python -m tools.run_coverage
python -m tools.run_coverage --base origin/master
```

Reports are written to the ignored `coverage-report/` directory:

- `index.html`: source-located action and branch hits, with the YAML source.
- `summary.md`: per-blueprint totals and uncovered changed opportunities.
- `coverage.json`: machine-readable source paths, line ranges, and hit counts.

Actions count as covered when the simulator reaches them. A service call that
raises still counts as attempted; coverage does not assert successful delivery.
Branches count whole-condition true/false results and each `choose` selection,
including no match. Short-circuited conditions are not recorded as evaluated.
Untested blueprints remain in the report with zero coverage. Empty denominators
are `N/A`, not 100%. A failed test run is marked failed even if coverage is high.

All runs enforce the thresholds in `config/testing/coverage_thresholds.json`:

| Gate | Minimum |
| --- | --- |
| Changed actions | 90% |
| Changed branch outcomes | 80% |
| Overall actions | 90% |
| Overall branch outcomes | 80% |

Each gate is checked independently using the exact hit counts, without rounding
the percentage first. Any unmet gate or test failure fails the coverage job;
reports are still exported. Every current blueprint has behavior tests, but
individual files may retain uncovered, unreachable choice outcomes because
tests do not bypass global conditions to inflate coverage.
Use `--thresholds <file>` to select another configuration for local experiments.

On pull requests and existing-branch pushes, the diff gates apply to measured
opportunities in changed YAML blocks. A change inside
a nested value/template counts as a change to the containing control-flow
blocks. This conservative check can require coverage of existing surrounding
branches. Deleted opportunities are not measurable after removal. Manual runs
and new-branch pushes without a baseline skip the diff gates but still enforce
both overall gates. An empty changed denominator is `N/A`, not 100%.
The local `--base` comparison uses Git-tracked changes; add new files to Git
before checking their changed-block coverage.

The measurement excludes Jinja internal branches and subexpressions, trigger
dispatch, top-level variables, Home Assistant execution semantics, and devices.
Changes wholly outside measured blocks have no coverage gate and are listed
separately. A new behavior runner must call `RECORDER.bind()` for its actual
YAML document and `RECORDER.hit()` at executed action, evaluated condition,
and selected/no-match choice sites; merely loading YAML gives no coverage.
Do not infer feature safety from the percentage alone: keep assertions about
values, command ordering, error behavior, and skipped writes.

## Validation scope

Structural checks cover all discovered blueprints. Behavior coverage depends
on the available test cases; a passing CI run does not imply every blueprint
behavior is tested. These checks do not validate the complete Home Assistant
schema or replace integration and device testing. Before release, import the
changed blueprint into its supported Home Assistant version and exercise each
declared integration.
