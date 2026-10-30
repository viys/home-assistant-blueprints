# Home Assistant Blueprints

Automation blueprints for SONOFF devices in Home Assistant.

For official import and re-import instructions, see [Using automation blueprints](https://www.home-assistant.io/docs/automation/using_blueprints/).

## Import a blueprint

### Option 1: Open the import dialog in Home Assistant

Select an **Import blueprint** button below. It opens the Blueprint import dialog in your Home Assistant instance; review the blueprint and select **Import Blueprint**.

### Option 2: Import manually

1. Copy the **Raw YAML** URL for the blueprint you want below.
2. In Home Assistant, go to **Settings > Automations & scenes > Blueprints**.
3. Select **Import Blueprint**, paste the URL, select **Preview**, then select **Import Blueprint**.

## Update an imported blueprint

1. In Home Assistant, go to **Settings > Automations & scenes > Blueprints**.
2. Open the three-dot menu for the blueprint and select **Re-import blueprint**.
3. Select **Re-import** to replace the imported copy with the latest version from its source URL.

If the updated blueprint changes its inputs, review and adjust any automations that use it. Re-import is available only for blueprints with a source URL.

## SONOFF blueprints

All SONOFF blueprints are under [`automation/sonoff`](automation/sonoff).

### Remote source

| Blueprint | Import | Links |
| --- | --- | --- |
| **Sync Remote Sensor to SNZB-02DR2** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_source_link_snzb02dr2.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_source_link_snzb02dr2.yaml) |
| **Sync Remote Temperature to TP-WGZBA** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_temperature_link_tp_wgzba.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_temperature_link_tp_wgzba.yaml) |
| **Sync Remote Temperature Sources to TP-WGZBA** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_temperature_sources_link_tp_wgzba.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_temperature_sources_link_tp_wgzba.yaml) |
| **Sync Remote Temperature to TRV-ZBL** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_temperature_link_trv_zbl.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_temperature_link_trv_zbl.yaml) |
| **Sync Remote Temperature to TRV-ZBT** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_temperature_link_trvzbt.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_temperature_link_trvzbt.yaml) |
| **Sync Remote Temperature to TRVZB** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_temperature_link_trvzb.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_temperature_link_trvzb.yaml) |

The SNZB-02DR2 blueprint requires Home Assistant 2025.3 or newer. Temperature
and optional humidity synchronize independently; updates received during a send
are combined using each source's latest reading. Writes are serialized within
one automation; avoid running separate automations against the same device
concurrently, including automations for different remote slots.
Home Assistant can continue after supported service errors, but raw ZHA
exceptions/timeouts can still stop a run and leave pending readings unsent.
The blueprint cannot impose a hard service-call timeout or check ZCL failure
statuses that the ZHA service does not expose.

### Target control

| Blueprint | Import | Links |
| --- | --- | --- |
| **Link TP-WGZBA Target Temperature to TRVs** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Ftrv_target_temperature_link_tp_wgzba.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/trv_target_temperature_link_tp_wgzba.yaml) |

## Notes

- Importing a blueprint installs its definition. Create and configure an automation from the imported blueprint before it can run.
- Requirements vary by blueprint. Read the input descriptions in Home Assistant before creating the automation.

## Tests

GitHub Actions validates all blueprint definitions and catalogue links, and
runs the test suite on Python 3.11–3.14 for pushes and pull requests. See
[test instructions and coverage scope](tests/README.md) for local commands,
manual CI runs, and the distinction between offline checks and device testing.
