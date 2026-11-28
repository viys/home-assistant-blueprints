---
title: Link TP-WGZBA Target Temperature to TRVs
description: Make radiator valves follow the target temperature set on TP-WGZBA.
slug: blueprints/tp-wgzba/trv_target_temperature_link_tp_wgzba
blueprint: trv_target_temperature_link_tp_wgzba
sidebar:
  label: Link target temperature
  order: 4
---

Make radiator valves follow the target temperature set on TP-WGZBA.

[![Make radiator valves follow the target temperature set on TP-WGZBA.](/home-assistant-blueprints/diagrams/trv_target_temperature_link_tp_wgzba.svg)](/home-assistant-blueprints/diagrams/trv_target_temperature_link_tp_wgzba.svg)

## Before you start

- Home Assistant Core **2025.4.0 or later**.
- Source: a TP-WGZBA.
- Targets: TRV-ZBL, TRV-ZBT, or TRVZB with compatible device handlers.
- Forwarded setpoint range: **5 to 30 °C**.

For TRVZB, use firmware and a ZHA quirk that expose **Panel target temperature
linkage** and **Panel linked target temperature**. Turn on the linkage switch
before forwarding panel targets. Turning it on does not send a cached target;
the next panel change or an Off-mode refresh supplies the temperature. This is separate from
the external room-temperature sensor feature.

## Configure the automation

Follow [the import and creation steps](../../../getting-started/), then fill in
the fields below and save the automation.

| Input | What to select |
| --- | --- |
| **TP-WGZBA target temperature source** | Select the TP-WGZBA device that provides the target temperature. |
| **SONOFF TRV devices** | Select one or more SONOFF TRV-ZBL, TRV-ZBT, or TRVZB valves. |

## When it synchronizes

When the panel target temperature changes, when the panel enters or leaves
**Off**, and when its frost protection setting changes while Off. While Off,
the frost protection target is also refreshed every **30 minutes** (on the hour
and half-hour).

Turning on linkage, saving the automation, restarting Home Assistant, and
changing only the measured temperature do not trigger an initial broadcast.
While Off, the next scheduled refresh can send the frost target.

## Off mode and frost protection

Off mode forwards the panel's available **frost protection temperature** as the
valve target; it does not turn the valves off. Leaving Off forwards the current
heating setpoint again. Each forwarded value must remain within **5–30 °C**.
If the frost setting is missing, ambiguous, unavailable, or nonnumeric, forwarding
is skipped and a warning is recorded in Home Assistant's system log.

For example, entering Off with frost protection set to **7 °C** sends a **7 °C
target** to the linked valves and refreshes it every 30 minutes while Off.

## Example

Select a TP-WGZBA and two target valves. Change the panel target from **20 °C** to **21 °C**. Both valves receive a **21 °C** setpoint. A measured room-temperature change alone does not trigger this automation.

## Confirm the result

1. Change the TP-WGZBA target temperature to **21 °C**.
2. Open each selected TRV-ZBL, TRV-ZBT, or TRVZB under **Settings > Devices & services**.
   Its climate entity should show a **21 °C target**, not a 21 °C measured room temperature.
3. Open the automation's **Traces** and confirm the setpoint action ran for each supported valve.

Saving alone does not broadcast a setpoint; change the panel target to test it.
Also enter Off and check that the valves receive the configured frost target,
then leave Off and confirm they receive the heating setpoint again.

See [Check your automation](../../../checking/) and
[Update a blueprint](../../../updating/) for the common procedures.
