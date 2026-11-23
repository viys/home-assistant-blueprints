---
title: SNZB-02DR2
description: Choose a Home Assistant blueprint for SNZB-02DR2.
sidebar:
  label: Overview
  order: 0
---

Supply external temperature and optional humidity to remote slot 1 or 2 on SNZB-02DR2.

## Choose your blueprint

| You want to… | Sources → targets | Integration | Blueprint |
| --- | --- | --- | --- |
| Supply readings to a remote slot | Required temperature + optional humidity → 1 slot on 1 device | ZHA / Zigbee2MQTT | [Remote temperature and humidity](./remote_source_link_snzb02dr2/) |

## Two rooms, two slots

Create separate automations for slots 1 and 2. Avoid multiple writers to the
same slot. Temperature and humidity are sent independently. This supplies
readings; it does not choose the displayed source or configure relay rules.

**Minimum Home Assistant Core: 2025.4.0.** [Check integration and device support](../../getting-started/#check-device-support) before importing.
