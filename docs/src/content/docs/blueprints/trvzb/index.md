---
title: TRVZB
description: Choose a Home Assistant blueprint for TRVZB.
sidebar:
  label: Overview
  order: 0
---

Use an external room sensor or an average of several readings with one or more TRVZB radiator valves.

## Choose your blueprint

| You want to… | Sources → targets | Calculation | Blueprint |
| --- | --- | --- | --- |
| Use one room reading | 1 sensor → 1+ valves | No averaging | [One temperature source](./remote_temperature_link_trvzb/) |
| Combine room readings | 1+ sensors → 1+ valves | Equal-weight average in HA | [Average temperature](./remote_temperature_average_link_trvzb/) |

Both temperature-source blueprints support **ZHA and Zigbee2MQTT**, including mixed targets in one automation.

## Follow a panel target

To follow a TP-WGZBA target setpoint, use [Link target temperature](../tp-wgzba/trv_target_temperature_link_tp_wgzba/).
TRVZB targets currently support **ZHA only**, with a compatible linkage firmware
and quirk. Enable **Panel target temperature linkage** on each valve first.
This forwards target setpoints rather than measured room temperatures.

## Using multiple valves

Select all target valves in one automation. Enable external temperature mode
on each valve and avoid another temperature automation writing to it.
Unavailable or failed valves do not prevent updates to the others.

**Minimum Home Assistant Core: 2025.4.0.** [Check integration and device support](../../getting-started/#check-device-support) before importing.
