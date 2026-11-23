---
title: Sync Average Temperature to TRV-ZBT
description: Calculate an equal-weight average in Home Assistant and send it to one or more TRV-ZBT valves.
slug: blueprints/trv-zbt/remote_temperature_average_link_trvzbt
blueprint: remote_temperature_average_link_trvzbt
sidebar:
  label: Average temperature
  order: 2
---

Calculate an equal-weight average in Home Assistant and send it to one or more TRV-ZBT valves.

[![Calculate an equal-weight average in Home Assistant and send it to one or more TRV-ZBT valves.](/home-assistant-blueprints/diagrams/remote_temperature_average_link_trvzbt.svg)](/home-assistant-blueprints/diagrams/remote_temperature_average_link_trvzbt.svg)

[Open full-size diagram](/home-assistant-blueprints/diagrams/remote_temperature_average_link_trvzbt.svg).

## Before you start

- Home Assistant Core **2025.4.0 or later**.
- [Check device support](../../../getting-started/#check-device-support) for your integration before importing.
- Select sensors from other devices, with numeric temperatures in °C, °F, or K.
- Enable external temperature mode. Use one temperature synchronization automation per target.

## Configure the automation

Follow [the import and creation steps](../../../getting-started/), then fill in
the fields below and save the automation.

| Input | Selection and default |
| --- | --- |
| **TRV-ZBT devices** | Required · one or more radiator valves; ZHA and Zigbee2MQTT targets can be mixed. |
| **Temperature validity period** | Optional · default **60 min**, range **1–120 min**. Applies to every source. |
| **External temperature sensors** | Required · one or more distinct external temperature sensors. Each has equal weight. |

Use sensors from other devices; a selected target's own sensors are excluded.
The converted average must fit the target integration's external temperature range.

## When it synchronizes

On source updates, Home Assistant startup, automation reload, mode changes, and every minute, while external mode is enabled and at least one valid source remains.

## Source validity

Each distinct valid source has equal weight. Unavailable, invalid, self-sourced,
and expired readings are excluded. If no valid source remains, sending stops
until one returns.

The validity period measures time since the temperature **state last changed**.
Identical reports and attribute-only updates do not renew it. Expiration is
checked every minute; Home Assistant restarts may extend validity.

Select one or more valves. Each must have external mode enabled; unavailable
or failed targets do not prevent the others from receiving the average.

## Example

Two valid sensors read **20 °C** and **22 °C**. The blueprint sends **21 °C** to TRV-ZBT. If the 20 °C source expires, the next check sends **22 °C** from the remaining source.

## Confirm the result

1. Cause a real selected-source update, then open the TRV-ZBT device under
   **Settings > Devices & services**.
2. Check its external temperature input or remote temperature reading.
   For valid sources at **20 °C** and **22 °C**, expect an external input of **21 °C**.
3. Open the automation's **Traces** and check that the temperature action ran.
   Check every selected valve, not just the first one.

Keep external mode enabled. Compare the remote measured reading, not the
heating target setpoint; the device's main display may show a different quantity.

See [Check your automation](../../../checking/) and
[Update a blueprint](../../../updating/) for the common procedures.
