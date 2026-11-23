---
title: Sync Remote Temperature Sources to TP-WGZBA
description: Send up to three room temperatures separately to TP-WGZBA remote sources.
slug: blueprints/tp-wgzba/remote_temperature_sources_link_tp_wgzba
blueprint: remote_temperature_sources_link_tp_wgzba
sidebar:
  label: Separate temperature sources
  order: 3
---

Send up to three room temperatures separately to TP-WGZBA remote sources.

[![Send up to three room temperatures separately to TP-WGZBA remote sources.](/home-assistant-blueprints/diagrams/remote_temperature_sources_link_tp_wgzba.svg)](/home-assistant-blueprints/diagrams/remote_temperature_sources_link_tp_wgzba.svg)

[Open full-size diagram](/home-assistant-blueprints/diagrams/remote_temperature_sources_link_tp_wgzba.svg).

## Before you start

- Home Assistant Core **2025.4.0 or later**.
- [Check device support](../../../getting-started/#check-device-support) for your integration before importing.
- Select sensors from other devices, with numeric temperatures in °C, °F, or K.
- Enable external temperature mode. Use one temperature synchronization automation per target.

| Integration | Supported sources |
| --- | --- |
| ZHA | Up to three with multi-source firmware and a compatible quirk; source 1 with older firmware. |
| Zigbee2MQTT | Up to three with a compatible multi-source converter; source 1 with older converters. Converted readings must be 0 to 99.9 °C for multi-source inputs. |

Source 1 is required. Leave unused sources 2 and 3 empty to unbind them on
supported multi-source devices. This blueprint does not calculate an average
in Home Assistant.

## Configure the automation

Follow [the import and creation steps](../../../getting-started/), then fill in
the fields below and save the automation.

| Input | What to select |
| --- | --- |
| **TP-WGZBA device** | Select the ZHA or Zigbee2MQTT TP-WGZBA thermostat that should receive the temperatures. |
| **Remote temperature source 1** | Required · a temperature sensor from another device. |
| **Remote temperature source 2 (optional)** | Optional · default empty. With multi-source support, leave empty to unbind slot 2. |
| **Remote temperature source 3 (optional)** | Optional · default empty. With multi-source support, leave empty to unbind slot 3. |

## When it synchronizes

ZHA sends on source updates while external mode is enabled, and resends on enabling that mode, startup, or automation reload. Zigbee2MQTT sends source updates; a compatible multi-source converter also synchronizes all slots on startup or automation reload.

## Example

Assign a living-room sensor to source 1 and a bedroom sensor to source 2. With compatible support, **20 °C** and **22 °C** are sent to their respective slots. Home Assistant does not combine them into 21 °C.

## Confirm the result

1. Change one selected sensor, then open the TP-WGZBA device under
   **Settings > Devices & services**.
2. With multi-source support, check the corresponding remote input: source 1
   at **20 °C** and source 2 at **22 °C** should remain separate readings.
   With older single-source support, check source 1 only.
3. Open the automation's **Traces** and check that the matching source was sent.

Do not expect this blueprint to write an HA-calculated **21 °C average**.
The panel's displayed or control temperature can differ from an individual remote input.

See [Check your automation](../../../checking/) and
[Update a blueprint](../../../updating/) for the common procedures.
