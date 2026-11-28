---
title: TRV-ZBT
description: Choose a Home Assistant blueprint for TRV-ZBT.
sidebar:
  label: Overview
  order: 0
---

Use one room reading with a single valve, or send an HA-calculated average to one or more TRV-ZBT valves.

## Choose your blueprint

To share one HA average across different SONOFF models, use
[Shared average temperature](../sonoff-thermostatic/remote_temperature_average_link_sonoff_thermostatic/)
(**Core 2025.10.0+**, development YAML). It supports one or more targets, including
mixed ZHA and Zigbee2MQTT devices.

| You want to… | Sources → targets | Calculation | Blueprint |
| --- | --- | --- | --- |
| Use one room reading | 1 sensor → 1 valve | No averaging | [One temperature source](./remote_temperature_link_trvzbt/) |
| Combine room readings | 1+ sensors → 1+ valves | Equal-weight average in HA | [Average temperature](./remote_temperature_average_link_trvzbt/) |

Both support **ZHA and Zigbee2MQTT**. Choose external temperature mode yourself;
the blueprints do not select it for you. Use one temperature synchronization
automation per valve. For the average blueprint, targets can use different integrations.

**Minimum Home Assistant Core: 2025.4.0** for the model-specific blueprints;
**2025.10.0** for the shared average blueprint. [Check integration and device support](../../getting-started/#check-device-support) before importing.
