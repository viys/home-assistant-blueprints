# Repository Guidelines

## Project Structure & Module Organization

This repository contains Home Assistant automation blueprints for SONOFF devices. Blueprint definitions live in `automation/sonoff/`, with one `.yaml` file per user-facing automation. `README.md` is the catalogue and import guide: it gives a brief user-facing summary of each blueprint and provides Home Assistant import, GitHub, and raw-download links. Keep device-specific additions in the existing vendor directory; add a new top-level directory only when introducing another vendor or automation family.

The illustrated user manual is an Astro + Starlight site under `docs/`.
Maintain user-facing guides in `docs/src/content/docs/`, grouped by device,
and standalone SVG illustrations in `docs/public/diagrams/`. The selection
homepage uses MDX; individual blueprint guides use ordinary Markdown. Keep
site configuration, shared components, and styling separate from blueprint
YAML. See `docs/MAINTAINING.md` for authoring and publishing conventions.

## Development and Validation

Blueprints have no compilation step. Run the offline test suite and focused checks:

```powershell
python -m pip install -r config/testing/requirements.txt
python -m unittest discover -s tests -v
git diff --check                 # detect whitespace errors
Get-Content automation/sonoff/<blueprint>.yaml
```

For documentation or site changes, also build and check the production site:

```powershell
npm ci --prefix docs
npm run build --prefix docs
python tools/check_site.py docs/dist
```

Use a Node.js version accepted by `docs/package.json`; the Pages workflow uses
Node 24. Preview with `npm run preview --prefix docs` and check navigation,
search, diagrams, and import links on desktop and mobile widths. Search must
be checked against the production build because its index is generated at
build time. Do not commit `node_modules/`, `.astro/`, or `dist/` output.

GitHub Actions runs blueprint validation and the test suite on Python 3.11–3.14
for pushes and pull requests. Structural and behavior checks cover every current
blueprint.

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

Every blueprint using `model_id` in a device selector must declare
`blueprint.homeassistant.min_version` of at least `2025.4.0`. Preserve any
higher minimum required by other features. Keep the matching guide and device
overview synchronized. The offline version guard checks this known
feature boundary; it does not replace validation in the declared HA version.

Use two-space indentation, never tabs. Preserve the existing Home Assistant blueprint layout: `blueprint`, `variables`, `triggers`, `conditions`, `actions`, then `mode`. Use descriptive snake_case filenames and blueprint input/variable IDs, such as `remote_temperature_link_tp_wgzba.yaml` and `source_temperature`. Keep human-facing labels concise and explain device, integration, units, and optional behavior in descriptions. Avoid unrelated reformatting.

Keep `blueprint.description` consistent across all blueprints from the same author. Follow this fixed structure, using the same wording and sentence order as the existing blueprints:

`<action> + <source> → <SONOFF model> (<integration>) → <trigger / behavior> → (temperature only) unit conversion`

Describe only what the blueprint supports and does for the user. Do not leak implementation details such as entity IDs, Zigbee cluster or attribute IDs, quirk frame formats, or firmware leases.

## Documentation and Link Integrity

### Required skill for SVG work

When adding or modifying SVG illustrations, use the `svg-diagram` skill and
read its `SKILL.md` before editing. The current user-level installation is
`C:\Users\Sonoff_yzy\.agents\skills\svg-diagram\SKILL.md`
(`~/.agents/skills/svg-diagram/SKILL.md` on other machines). If unavailable,
report the missing skill; its source is
[bybit-exchange/svg-diagram](https://github.com/bybit-exchange/svg-diagram).

The primary purpose of each blueprint SVG is to explain its function to users.
Check the blueprint and matching guide first. Show where readings originate,
what is calculated or forwarded, and which devices receive which values.
Distinguish HA averaging from device-side averaging, separate remote inputs
from a combined reading, and measured temperatures from target setpoints.
Make relevant integration limits, optional inputs, and multiple targets clear.
Use different layouts where behaviors differ rather than repeating one generic
three-box flow. Render and inspect every changed SVG for readable labels,
accurate connections, overlap, clipping, and desktop/mobile presentation.

The repository's `docs/public/diagrams/` location, matching filename stems,
published image URLs, and Home Assistant color roles take precedence over the
skill's generic output-location and palette defaults. See `docs/MAINTAINING.md`
for the shared illustration conventions.

### Synchronization and links

Keep documentation synchronized throughout development, in the same change as
the implementation. A blueprint or script change is incomplete until affected
documentation has been reviewed and updated; do not defer it to a later task or
wait for the user to request it. Complete this check before requesting review
or committing. If a change has no documentation impact, explain why in the
change summary or PR description instead of making unrelated documentation edits.

For blueprint changes, check the YAML metadata and input descriptions, matching
Markdown guide and SVG, device overview, selection homepage, README catalogue,
and corresponding tests. Update every affected explanation of inputs, defaults,
units, source/target counts, integration and firmware support, triggers,
timeouts, invalid-source handling, and examples. Distinguish ZHA from
Zigbee2MQTT behavior and device-side averaging from averaging in Home Assistant.
Keep claims grounded in the current implementation and identify unverified
Home Assistant or hardware behavior accurately.

Every blueprint must have exactly one dedicated Markdown guide and one SVG
using its YAML filename stem. Set the guide's `blueprint` front matter to that
stem and its `title` to `blueprint.name`; the shared component derives import
and download links from it. When adding, renaming, merging, or removing a
blueprint, update its guides, diagrams, navigation, catalogue links, and tests
in the same change. Remove obsolete documentation and preserve applicable
instructions when merging guides.

For tooling, validation, or publishing script changes, update affected command
examples, prerequisites, paths, and workflow instructions in `AGENTS.md`,
`docs/MAINTAINING.md`, and other relevant documentation in the same change.

Keep `README.md` focused on the repository overview, common import/re-import instructions, and the blueprint catalogue, with links to the manual. Keep concise blueprint-specific requirements and supported behavior in the YAML metadata and input descriptions; put illustrated setup steps and examples in the manual. Track unresolved defects and implementation limitations in GitHub Issues. Do not maintain a separate project-level test README; describe test scenarios and limitations in the relevant test names and comments. Do not add per-blueprint troubleshooting, pending-work lists, or issue status paragraphs to the root README.

Keep shared website pages generic: put model-specific requirements, version
floors, examples, and integration limits in device overviews and blueprint
guides. The homepage's **Find your device** section may name devices; its other
sections and the shared getting-started, updating, checking, and 404 pages
should link to the relevant guides instead of listing model-specific details.

Use the same short, action-oriented name in the README catalogue and in
`blueprint.name`. Follow the existing action-and-device naming pattern. Do not
use parentheses or append explanations to blueprint names. Put source limits,
integration details, and behavior in the blueprint description.

Every new blueprint needs a matching entry in `README.md` with its summary, stable `master` import badge and raw-download link, plus a `dev` raw-download link. Do not add a `dev` import badge. When adding, moving, renaming, or deleting a file, update every affected relative and GitHub URL in the README in the same change. Verify each path segment, branch, and URL-encoded `blueprint_url` points to the final filename; do not leave stale links behind.

## Commits & Pull Requests

Contributions to `dev` must use PRs and squash merging. Stable `vMAJOR.MINOR.PATCH`
tags trigger `release.yml`, which validates the tag's exact commit and then
fast-forwards `master` without rewriting history. Keep write credentials out of
validation jobs, reject divergent or non-linear release ranges, and recheck
the baseline before updating the remote. See `docs/RELEASING.md` for repository
rules and tag creation. Never create or push a real release tag as a test.

Use short, imperative Conventional Commit-style subjects, for example `feat: add TRV temperature sync blueprint` or `docs: fix blueprint import links`. Keep each commit focused. Pull requests should state the supported device and integrations, describe behavior changes and synchronized documentation, link related issues when applicable, and include the Home Assistant version used for manual validation or state that manual validation was not performed. Include screenshots only when a UI-facing documentation change benefits from one.
