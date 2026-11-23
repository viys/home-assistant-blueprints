---
title: Sync Remote Temperature to TRVZB
description: Send one room temperature to one or more TRVZB valves, through ZHA or Zigbee2MQTT.
slug: blueprints/trvzb/remote_temperature_link_trvzb
blueprint: remote_temperature_link_trvzb
sidebar:
  label: One temperature source
  order: 1
---

Send one room temperature to one or more TRVZB valves, through ZHA or Zigbee2MQTT.

[![Send one room temperature to one or more TRVZB valves, through ZHA or Zigbee2MQTT.](/home-assistant-blueprints/diagrams/remote_temperature_link_trvzb.svg)](/home-assistant-blueprints/diagrams/remote_temperature_link_trvzb.svg)

[Open full-size diagram](/home-assistant-blueprints/diagrams/remote_temperature_link_trvzb.svg).

## Before you start

- Home Assistant Core **2025.4.0 or later**.
- [Check device support](../../../getting-started/#check-device-support) for your integration before importing.
- Select sensors from other devices, with numeric temperatures in °C, °F, or K.
- Enable external temperature mode. Use one temperature synchronization automation per target.

Both integrations require external mode on each selected valve. One automation
can serve multiple valves, including a mixture of ZHA and Zigbee2MQTT devices.
Unavailable or failed valves do not prevent updates to the others.

## Configure the automation

Follow [the import and creation steps](../../../getting-started/), then fill in
the fields below and save the automation.

| Input | What to select |
| --- | --- |
| **TRVZB devices** | Required · one or more ZHA or Zigbee2MQTT TRVZB valves in external mode. |
| **External temperature sensor** | Select a temperature sensor from another device. Temperatures from any selected TRVZB are not valid sources. |

## When it synchronizes

On source updates, Home Assistant startup, and automation reload. External-mode changes and recovery of unavailable external inputs resynchronize affected valves. Each target must be in external mode when its update is sent.

## Example

Select your living-room sensor and two TRVZB valves. A **21.5 °C** update is forwarded to both valves that are available and in external mode.

## Confirm the result

1. Cause a real selected-source update, then open the TRVZB device under
   **Settings > Devices & services**.
2. Check its external temperature input or remote temperature reading.
   For a source at **21.5 °C**, expect an external input of **21.5 °C**, subject to supported precision.
3. Open the automation's **Traces** and check that the temperature action ran.
   Check every selected valve, not just the first one.

Keep external mode enabled. Compare the remote measured reading, not the
heating target setpoint; the device's main display may show a different quantity.

See [Check your automation](../../../checking/) and
[Update a blueprint](../../../updating/) for the common procedures.
