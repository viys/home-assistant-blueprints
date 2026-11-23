---
title: Link TP-WGZBA Target Temperature to TRVs
description: Make supported ZHA radiator valves follow the target temperature set on TP-WGZBA.
slug: blueprints/tp-wgzba/trv_target_temperature_link_tp_wgzba
blueprint: trv_target_temperature_link_tp_wgzba
sidebar:
  label: Link target temperature
  order: 4
---

Make supported ZHA radiator valves follow the target temperature set on TP-WGZBA.

[![Make supported ZHA radiator valves follow the target temperature set on TP-WGZBA.](/home-assistant-blueprints/diagrams/trv_target_temperature_link_tp_wgzba.svg)](/home-assistant-blueprints/diagrams/trv_target_temperature_link_tp_wgzba.svg)

[Open full-size diagram](/home-assistant-blueprints/diagrams/trv_target_temperature_link_tp_wgzba.svg).

## Before you start

- Home Assistant Core **2025.4.0 or later**.
- Source: a TP-WGZBA connected through ZHA or Zigbee2MQTT.
- Targets: **ZHA TRV-ZBL or TRV-ZBT** with compatible device handlers.
- Forwarded setpoint range: **5 to 30 °C**.

Other selected models or integrations are skipped, even if listed by the selector.
This version does not forward to TRVZB or Zigbee2MQTT valves.

## Configure the automation

Follow [the import and creation steps](../../../getting-started/), then fill in
the fields below and save the automation.

| Input | What to select |
| --- | --- |
| **TP-WGZBA target temperature source** | Select the TP-WGZBA device that provides the target temperature. |
| **SONOFF TRV devices** | Select one or more ZHA SONOFF TRV-ZBL or TRV-ZBT valves. Other selections are skipped. |

## When it synchronizes

When the panel target temperature changes. Saving the automation, restarting Home Assistant, and changing only the measured temperature do not trigger an initial setpoint broadcast.

## Example

Select a TP-WGZBA and two supported ZHA valves. Change the panel target from **20 °C** to **21 °C**. Both valves receive a **21 °C** setpoint. A measured room-temperature change alone does not trigger this automation.

## Confirm the result

1. Change the TP-WGZBA target temperature to **21 °C**.
2. Open each selected ZHA TRV-ZBL or TRV-ZBT under **Settings > Devices & services**.
   Its climate entity should show a **21 °C target**, not a 21 °C measured room temperature.
3. Open the automation's **Traces** and confirm the setpoint action ran for each supported valve.

Saving alone does not broadcast a setpoint; change the panel target to test it.

See [Check your automation](../../../checking/) and
[Update a blueprint](../../../updating/) for the common procedures.
