---
title: TP-WGZBA
description: Choose a Home Assistant blueprint for TP-WGZBA.
sidebar:
  label: Overview
  order: 0
---

Choose how the panel receives measured temperatures, forward its setpoint to
supported radiator valves, or pause it when a door or window opens.

## Choose your blueprint

To share one HA average across different SONOFF models, use
[Shared average temperature](../sonoff-thermostatic/remote_temperature_average_link_sonoff_thermostatic/)
(**Core 2025.10.0+**, development YAML). It supports one or more targets, including
mixed ZHA and Zigbee2MQTT devices.

| You want to… | Sources → targets | Integration | Blueprint |
| --- | --- | --- | --- |
| Use one room sensor | 1 sensor → 1 panel | ZHA / Zigbee2MQTT | [One temperature source](./remote_temperature_link_tp_wgzba/) |
| Combine room readings in HA | 1+ sensors → 1 panel | ZHA / Zigbee2MQTT | [Average temperature](./remote_temperature_average_link_tp_wgzba/) |
| Send readings separately to the panel | Up to 3 sensors → 1 panel | ZHA / Zigbee2MQTT, with multi-source support | [Separate temperature sources](./remote_temperature_sources_link_tp_wgzba/) |
| Make valves follow the panel setting | 1 panel → 1+ ZHA TRV-ZBL / TRV-ZBT / TRVZB valves | Panel: ZHA / Zigbee2MQTT; valves: ZHA | [Link target temperature](./trv_target_temperature_link_tp_wgzba/) |
| Pause when a door or window opens | 1+ contacts → 1 panel | Panel: ZHA with a compatible custom quirk; awaiting release | [Door and window sensors](./door_window_link_tp_wgzba/) |

## Average or separate sources?

**Average temperature** calculates one equal-weight value in Home Assistant.
**Separate temperature sources** sends individual readings to the panel's
remote slots; older firmware or converters support source 1 only.

Use one measured-temperature synchronization automation per panel.
Target-temperature linking can serve a different purpose: it forwards the
**desired setpoint**, not a measured room temperature. In Off mode it forwards
the panel's available frost protection target and refreshes it every 30 minutes.

**Door and window sensors** combines contact states in HA: any open contact
sends open, and only all contacts closed sends closed. Contacts may use any
integration; the receiving panel must use ZHA. See the guide for manual exit,
unavailable contacts, and clearing the input when stopping the automation.

**Minimum Home Assistant Core: 2025.4.0** for the model-specific blueprints;
**2025.10.0** for the shared average blueprint. [Check integration and device support](../../getting-started/#check-device-support) before importing.
