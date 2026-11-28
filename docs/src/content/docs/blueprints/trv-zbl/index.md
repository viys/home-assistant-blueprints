---
title: TRV-ZBL
description: Choose a Home Assistant blueprint for TRV-ZBL.
sidebar:
  label: Overview
  order: 0
---

Send separate temperature readings to a TRV-ZBL valve for device-side averaging.

## Choose your blueprint

To share one HA average across different SONOFF models, use
[Shared average temperature](../sonoff-thermostatic/remote_temperature_average_link_sonoff_thermostatic/)
(**Core 2025.10.0+**).

| You want to… | Targets | Blueprint |
| --- | --- | --- |
| Send separate room readings | 1 valve | [Remote temperature sources](./remote_temperature_link_trv_zbl/) |

## HA or valve averaging?

The shared average blueprint calculates one reading in Home Assistant and can
send it to multiple models. The model-specific remote-sources blueprint keeps readings
separate for averaging inside one valve. See its guide for source-count limits.

## Before you choose

Enable external temperature mode and use one temperature synchronization
automation per valve. Follow the chosen guide for source-slot configuration.

**Minimum Home Assistant Core: 2025.10.0.** [Check integration and device support](../../getting-started/#check-device-support) before importing.
