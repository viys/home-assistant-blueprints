---
title: Sync Remote Temperature to TRV-ZBT
description: Use one external room temperature sensor with your TRV-ZBT.
slug: blueprints/trv-zbt/remote_temperature_link_trvzbt
blueprint: remote_temperature_link_trvzbt
sidebar:
  label: One temperature source
  order: 1
---

Use one external room temperature sensor with your TRV-ZBT.

[![Use one external room temperature sensor with your TRV-ZBT.](/home-assistant-blueprints/diagrams/remote_temperature_link_trvzbt.svg)](/home-assistant-blueprints/diagrams/remote_temperature_link_trvzbt.svg)

[Open full-size diagram](/home-assistant-blueprints/diagrams/remote_temperature_link_trvzbt.svg).

## Before you start

- Home Assistant Core **2025.4.0 or later**.
- [Check device support](../../../getting-started/#check-device-support) for your integration before importing.
- Select sensors from other devices, with numeric temperatures in °C, °F, or K.
- Enable external temperature mode. Use one temperature synchronization automation per target.

| Integration | When readings are sent |
| --- | --- |
| ZHA | On source updates while external mode is enabled, and when external mode is turned on. |
| Zigbee2MQTT | On source updates. Select external temperature mode yourself so the device uses the supplied reading. |

Saving or reloading the automation alone does not send an initial reading.

This blueprint never changes the selected temperature source.

## Configure the automation

Follow [the import and creation steps](../../../getting-started/), then fill in
the fields below and save the automation.

| Input | What to select |
| --- | --- |
| **TRV-ZBT device** | Select the ZHA or Zigbee2MQTT radiator valve that should receive the temperature. |
| **External temperature sensor** | Select a temperature sensor from another device. The target TRV-ZBT's own temperature is not a valid source. |

## When it synchronizes

On source updates. ZHA also sends when external mode is enabled. Startup and automation reload do not trigger this blueprint.

## Example

Select a living-room sensor and your TRV-ZBT. A **21.5 °C** update is forwarded as **21.5 °C**. Enable external mode so the device uses that reading.

## Confirm the result

1. Cause a real selected-source update, then open the TRV-ZBT device under
   **Settings > Devices & services**.
2. Check its external temperature input or remote temperature reading.
   For a source at **21.5 °C**, expect an external input of **21.5 °C**, subject to supported precision.
3. Open the automation's **Traces** and check that the temperature action ran.

Keep external mode enabled. Compare the remote measured reading, not the
heating target setpoint; the device's main display may show a different quantity.

See [Check your automation](../../../checking/) and
[Update a blueprint](../../../updating/) for the common procedures.
