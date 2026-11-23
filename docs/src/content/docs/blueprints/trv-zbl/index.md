---
title: TRV-ZBL
description: Choose a Home Assistant blueprint for TRV-ZBL.
sidebar:
  label: Overview
  order: 0
---

Send separate temperature readings to a TRV-ZBL valve. The valve can calculate their average when used with compatible ZHA support.

## Choose your blueprint

| Integration | Sources → targets | Calculation | Blueprint |
| --- | --- | --- | --- |
| ZHA | 1–5 distinct sensors → 1 valve | The valve averages the readings | [Remote temperature sources](./remote_temperature_link_trv_zbl/) |
| Zigbee2MQTT | 1 sensor → 1 valve | Source 1 only | [Remote temperature sources](./remote_temperature_link_trv_zbl/) |

## Before you choose

ZHA needs firmware and a handler supporting five remote sources. For
Zigbee2MQTT, leave sources 2–5 empty. Enable external temperature mode and use
one temperature synchronization automation per valve.

**Minimum Home Assistant Core: 2025.10.0.** [Check integration and device support](../../getting-started/#check-device-support) before importing.
