---
title: Update a blueprint
description: Re-import a blueprint and check the automations that use it.
---

Re-importing replaces a blueprint's definition. Review changed inputs before
relying on automations that use the new version.

## Re-import

1. Open **Settings > Automations & scenes > Blueprints**.
2. Find the blueprint and open its three-dot menu.
3. Select **Re-import blueprint**, then confirm **Re-import**.
4. Open each automation that uses it. Check the target, sources, and any new or
   changed settings, and save if needed.
5. Exercise a real trigger and confirm the result again.

Re-import requires a source URL and retrieves that same source. A blueprint
imported from `dev` does not automatically switch to `master` on update.

## Automations you took control of

Home Assistant's **Take control** converts a blueprint automation to a regular
automation. Re-importing the blueprint does not update that independent copy.

Read [Home Assistant's update instructions](https://www.home-assistant.io/docs/automation/using_blueprints/#re-importing-a-blueprint)
for the full procedure.
