# Home Assistant Blueprints

Automation blueprints for SONOFF devices in Home Assistant.

This README lists the available blueprints and explains how to import or update them. Check each blueprint's inputs for its requirements and [GitHub Issues](https://github.com/viys/home-assistant-blueprints/issues) for known problems.

For official import and re-import instructions, see [Using automation blueprints](https://www.home-assistant.io/docs/automation/using_blueprints/).

## Before importing a blueprint

Use the latest compatible ZHA quirk or Zigbee2MQTT (Z2M) converter for your SONOFF device. Search for your device model in the GitHub pull requests for the integration you use.

- [ZHA quirks — GitHub pull requests](https://github.com/zigpy/zha-device-handlers/pulls)
- [Zigbee2MQTT converters — GitHub pull requests](https://github.com/Koenkk/zigbee-herdsman-converters/pulls)

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

**Import** and **Links** use the stable `master` branch. **Dev links** provides raw YAML links for the `dev` branch.

Expand a device below to browse its blueprints.

<details>
<summary><strong>SNZB-02DR2</strong></summary>

| Blueprint | Import | Links | Dev links |
| --- | --- | --- | --- |
| **Sync Remote Sensor to SNZB-02DR2** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_source_link_snzb02dr2.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_source_link_snzb02dr2.yaml) | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/dev/automation/sonoff/remote_source_link_snzb02dr2.yaml) |

</details>

---

<details>
<summary><strong>TP-WGZBA</strong></summary>

| Blueprint | Import | Links | Dev links |
| --- | --- | --- | --- |
| **Sync Remote Temperature to TP-WGZBA** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_temperature_link_tp_wgzba.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_temperature_link_tp_wgzba.yaml) | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/dev/automation/sonoff/remote_temperature_link_tp_wgzba.yaml) |
| **Sync Average Temperature to TP-WGZBA** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_temperature_average_link_tp_wgzba.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_temperature_average_link_tp_wgzba.yaml) | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/dev/automation/sonoff/remote_temperature_average_link_tp_wgzba.yaml) |
| **Sync Remote Temperature Sources to TP-WGZBA** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_temperature_sources_link_tp_wgzba.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_temperature_sources_link_tp_wgzba.yaml) | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/dev/automation/sonoff/remote_temperature_sources_link_tp_wgzba.yaml) |
| **Link TP-WGZBA Target Temperature to TRVs** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Ftrv_target_temperature_link_tp_wgzba.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/trv_target_temperature_link_tp_wgzba.yaml) | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/dev/automation/sonoff/trv_target_temperature_link_tp_wgzba.yaml) |

</details>

---

<details>
<summary><strong>TRV-ZBL</strong></summary>

| Blueprint | Import | Links | Dev links |
| --- | --- | --- | --- |
| **Sync Remote Temperature Sources to TRV-ZBL** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_temperature_link_trv_zbl.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_temperature_link_trv_zbl.yaml) | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/dev/automation/sonoff/remote_temperature_link_trv_zbl.yaml) |

</details>

---

<details>
<summary><strong>TRV-ZBT</strong></summary>

| Blueprint | Import | Links | Dev links |
| --- | --- | --- | --- |
| **Sync Remote Temperature to TRV-ZBT** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_temperature_link_trvzbt.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_temperature_link_trvzbt.yaml) | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/dev/automation/sonoff/remote_temperature_link_trvzbt.yaml) |

</details>

---

<details>
<summary><strong>TRVZB</strong></summary>

| Blueprint | Import | Links | Dev links |
| --- | --- | --- | --- |
| **Sync Remote Temperature to TRVZB** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_temperature_link_trvzb.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_temperature_link_trvzb.yaml) | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/dev/automation/sonoff/remote_temperature_link_trvzb.yaml) |
| **Sync Average Temperature to TRVZB** | <a href="https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fremote_temperature_average_link_trvzb.yaml"><img src="https://my.home-assistant.io/badges/blueprint_import.svg" alt="Import blueprint" height="28"></a> | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/master/automation/sonoff/remote_temperature_average_link_trvzb.yaml) | [Raw YAML](https://raw.githubusercontent.com/viys/home-assistant-blueprints/dev/automation/sonoff/remote_temperature_average_link_trvzb.yaml) |

</details>

## Notes

- Importing a blueprint installs its definition. Create and configure an automation from the imported blueprint before it can run.
- Requirements vary by blueprint. Read the input descriptions in Home Assistant before creating the automation.
