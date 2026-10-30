# Blueprint tests and CI

Requires Python 3.11 or newer. From the repository root:

```powershell
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -v
git diff --check
```

## GitHub Actions

The `CI` workflow runs on pushes, pull requests, and manual dispatch. It shows
these checks in the pull request:

- `Blueprint validation`: checks every blueprint's YAML, duplicate keys,
  required structure, declared input references, Jinja syntax, and README
  import/raw-download paths.
- `Unit tests (Python 3.11)` through `Unit tests (Python 3.14)`: runs the whole
  test suite independently on each Python version.

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

## Validation scope

Structural checks cover all discovered blueprints. Behavior coverage depends
on the available test cases; a passing CI run does not imply every blueprint
behavior is tested. These checks do not validate the complete Home Assistant
schema or replace integration and device testing. Before release, import the
changed blueprint into its supported Home Assistant version and exercise each
declared integration.
