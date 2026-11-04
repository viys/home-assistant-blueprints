# Repository Guidelines

## Project Structure & Module Organization

This repository contains Home Assistant automation blueprints for SONOFF devices. Blueprint definitions live in `automation/sonoff/`, with one `.yaml` file per user-facing automation. `README.md` is the catalogue and import guide: it gives a brief user-facing summary of each blueprint and provides Home Assistant import, GitHub, and raw-download links. Keep device-specific additions in the existing vendor directory; add a new top-level directory only when introducing another vendor or automation family.

## Development and Validation

There is no build system. Run the offline test suite and focused checks:

```powershell
python -m pip install -r config/testing/requirements.txt
python -m unittest discover -s tests -v
git diff --check                 # detect whitespace errors
Get-Content automation/sonoff/<blueprint>.yaml
```

GitHub Actions runs blueprint validation and the test suite on Python 3.11–3.14
for pushes and pull requests. Structural and behavior checks cover every current
blueprint. See `tests/README.md` for scope and runtime limitations.

Each blueprint must have exactly one dedicated test file. For
`automation/sonoff/<blueprint>.yaml`, use `tests/test_<blueprint>.py` with the
same filename stem. Put all blueprint-specific tests, including regressions,
in that file. Use separate test classes within it to group scenarios by behavior
or integration. Put repository-wide test cases and shared test utilities in
`tests/common/`. Give utility modules names without the `test_` prefix.

Rename, consolidate, or remove the corresponding dedicated tests in the same
change that renames, merges, or removes a blueprint. When merging blueprints,
move all still-applicable cases into the surviving blueprint's test file.

Import the changed blueprint into a Home Assistant test instance, create an automation from it, and exercise its triggers and service calls for each declared integration (for example, ZHA and Zigbee2MQTT). Check the minimum Home Assistant version and selectors against the intended target version.

## YAML Style & Naming

Use two-space indentation, never tabs. Preserve the existing Home Assistant blueprint layout: `blueprint`, `variables`, `triggers`, `conditions`, `actions`, then `mode`. Use descriptive snake_case filenames and blueprint input/variable IDs, such as `remote_temperature_link_tp_wgzba.yaml` and `source_temperature`. Keep human-facing labels concise and explain device, integration, units, and optional behavior in descriptions. Avoid unrelated reformatting.

Keep `blueprint.description` consistent across all blueprints from the same author. Follow this fixed structure, using the same wording and sentence order as the existing blueprints:

`<action> + <source> → <SONOFF model> (<integration>) → <trigger / behavior> → (temperature only) unit conversion`

Describe only what the blueprint supports and does for the user. Do not leak implementation details such as entity IDs, Zigbee cluster or attribute IDs, quirk frame formats, or firmware leases.

## Documentation and Link Integrity

Keep `README.md` focused on the repository overview, common import/re-import instructions, and the blueprint catalogue. Put blueprint-specific requirements and supported behavior in that blueprint's metadata and input descriptions; track unresolved defects and implementation limitations in GitHub Issues. Keep test procedures and coverage details in `tests/README.md`. Do not add per-blueprint troubleshooting, pending-work lists, or issue status paragraphs to the root README.

Use the same short, action-oriented name in the README catalogue and in
`blueprint.name`. Follow the existing action-and-device naming pattern. Do not
use parentheses or append explanations to blueprint names. Put source limits,
integration details, and behavior in the blueprint description.

Every new blueprint needs a matching entry in `README.md` with its summary, stable `master` import badge and raw-download link, plus a `dev` raw-download link. Do not add a `dev` import badge. When adding, moving, renaming, or deleting a file, update every affected relative and GitHub URL in the README in the same change. Verify each path segment, branch, and URL-encoded `blueprint_url` points to the final filename; do not leave stale links behind.

## Commits & Pull Requests

This repository has no established commit history yet. Use short, imperative Conventional Commit-style subjects, for example `feat: add TRV temperature sync blueprint` or `docs: fix blueprint import links`. Keep each commit focused. Pull requests should state the supported device and integrations, describe behavior changes, link related issues when applicable, and include the Home Assistant version used for manual validation. Include screenshots only when a UI-facing documentation change benefits from one.
