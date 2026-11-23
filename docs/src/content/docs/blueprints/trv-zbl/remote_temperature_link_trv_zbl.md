---
title: Sync Remote Temperature Sources to TRV-ZBL
description: Send separate readings to TRV-ZBL. With ZHA, the valve averages up to five sources.
slug: blueprints/trv-zbl/remote_temperature_link_trv_zbl
blueprint: remote_temperature_link_trv_zbl
sidebar:
  label: Remote temperature sources
  order: 1
---

Send separate readings to TRV-ZBL. With ZHA, the valve averages up to five sources.

[![Send separate readings to TRV-ZBL. With ZHA, the valve averages up to five sources.](/home-assistant-blueprints/diagrams/remote_temperature_link_trv_zbl.svg)](/home-assistant-blueprints/diagrams/remote_temperature_link_trv_zbl.svg)

[Open full-size diagram](/home-assistant-blueprints/diagrams/remote_temperature_link_trv_zbl.svg).

## Before you start

- Home Assistant Core **2025.10.0 or later**.
- [Check device support](../../../getting-started/#check-device-support) for your integration before importing.
- Select sensors from other devices, with numeric temperatures in °C, °F, or K.
- Enable external temperature mode. Use one temperature synchronization automation per target.

| Integration | Supported sources |
| --- | --- |
| ZHA | One to five distinct sensors, with compatible firmware and a five-source device handler. The valve calculates their average. |
| Zigbee2MQTT | Source 1 only; leave sources 2–5 empty. |

For ZHA, invalid sources are removed from the device average until they recover.
Numeric readings are forwarded for the valve to validate, without temperature
range filtering by this blueprint.

## Configure the automation

Follow [the import and creation steps](../../../getting-started/), then fill in
the fields below and save the automation.

| Input | What to select |
| --- | --- |
| **TRV-ZBL device** | Required · one ZHA or Zigbee2MQTT TRV-ZBL valve in external mode. |
| **Remote temperature source 1** | Required · a temperature sensor from another device. Use a distinct sensor per slot. |
| **Remote temperature source 2 (optional)** | ZHA only. Leave empty when a second remote source is not used. |
| **Remote temperature source 3 (optional)** | ZHA only. Leave empty when a third remote source is not used. |
| **Remote temperature source 4 (optional)** | ZHA only. Leave empty when a fourth remote source is not used. |
| **Remote temperature source 5 (optional)** | ZHA only. Leave empty when a fifth remote source is not used. |

## When it synchronizes

ZHA sends on source updates while external mode is enabled, and resends on enabling that mode, startup, or automation reload. Zigbee2MQTT sends source 1 updates only.

## Example

With ZHA, assign sensors reading **20 °C** and **22 °C** to sources 1 and 2; leave the rest empty. The valve handles their average. With Zigbee2MQTT, configure source 1 only.

## Confirm the result

1. Change a selected source, then open the TRV-ZBL device under
   **Settings > Devices & services**.
2. With ZHA, check the configured remote readings where exposed and the valve's
   resulting external temperature. The valve calculates the average.
   With Zigbee2MQTT, check that its external input follows source 1.
3. Open the automation's **Traces** and check the source-update branch.

Compare measured temperatures, not the heating target setpoint. If remote
slots are not exposed by your integration, use the trace and device-side
external reading together rather than assuming the screen represents one slot.

See [Check your automation](../../../checking/) and
[Update a blueprint](../../../updating/) for the common procedures.
