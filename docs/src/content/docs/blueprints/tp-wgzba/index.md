---
title: TP-WGZBA
description: Choose a Home Assistant blueprint for TP-WGZBA.
sidebar:
  label: Overview
  order: 0
---

Choose how the panel receives measured temperatures, or forward its setpoint to supported radiator valves.

## Choose your blueprint

| You want to… | Sources → targets | Integration | Blueprint |
| --- | --- | --- | --- |
| Use one room sensor | 1 sensor → 1 panel | ZHA / Zigbee2MQTT | [One temperature source](./remote_temperature_link_tp_wgzba/) |
| Combine room readings in HA | 1+ sensors → 1 panel | ZHA / Zigbee2MQTT | [Average temperature](./remote_temperature_average_link_tp_wgzba/) |
| Send readings separately to the panel | Up to 3 sensors → 1 panel | ZHA / Zigbee2MQTT, with multi-source support | [Separate temperature sources](./remote_temperature_sources_link_tp_wgzba/) |
| Make valves follow the panel setting | 1 panel → 1+ ZHA TRV-ZBL / TRV-ZBT valves | Panel: ZHA / Zigbee2MQTT; valves: ZHA | [Link target temperature](./trv_target_temperature_link_tp_wgzba/) |

## Average or separate sources?

**Average temperature** calculates one equal-weight value in Home Assistant.
**Separate temperature sources** sends individual readings to the panel's
remote slots; older firmware or converters support source 1 only.

Use one measured-temperature synchronization automation per panel.
Target-temperature linking can serve a different purpose: it forwards the
**desired setpoint**, not a measured room temperature.

**Minimum Home Assistant Core: 2025.4.0.** [Check integration and device support](../../getting-started/#check-device-support) before importing.
