---
title: Sync Average Temperature to SONOFF Thermostatic Devices
description: Share one Home Assistant temperature average across SONOFF thermostats and radiator valves.
slug: blueprints/sonoff-thermostatic/remote_temperature_average_link_sonoff_thermostatic
blueprint: remote_temperature_average_link_sonoff_thermostatic
sidebar:
  label: Shared average temperature
  order: 1
---

Calculate one equal-weight temperature average in Home Assistant and send it to
one or more TRVZB, TRV-ZBT, TRV-ZBL, or TP-WGZBA devices. Models and integrations
can be mixed in the same automation.

[![External room readings converge into one HA average, then reach multiple SONOFF models.](/home-assistant-blueprints/diagrams/remote_temperature_average_link_sonoff_thermostatic.svg)](/home-assistant-blueprints/diagrams/remote_temperature_average_link_sonoff_thermostatic.svg)

## Before you start

- Home Assistant Core **2025.10.0 or later**.
- Enable external temperature mode on every target. Use one measured-temperature
  synchronization automation per target to avoid competing writes.
- Select sensors from other devices, with numeric temperatures in °C, °F, or K.
- TRV-ZBL needs a compatible ZHA device handler or Zigbee2MQTT converter that
  accepts a single external temperature input. Its separate multi-source feature
  is not used by this blueprint.

This blueprint is a development addition. Until it is released, use **Dev YAML**
under **Other download options** for manual import; the stable import button
becomes usable after release. See [Update a blueprint](../../../updating/).

## Configure the automation

Follow [the import and creation steps](../../../getting-started/), then set:

| Input | Selection and default |
| --- | --- |
| **Temperature source notifications** | Optional · off by default. Show source issues in Home Assistant. |
| **Temperature validity period** | Default **60 min**, range **1–120 min**, shared by all sources. |
| **External temperature sensors** | One or more sensors, each counted once with equal weight. |
| **SONOFF thermostatic devices** | One or more supported devices; models and ZHA / Zigbee2MQTT targets can be mixed. |

When replacing an existing temperature automation, disable it before enabling
this one. Sensors belonging to **any** selected target are excluded from the
shared source pool, even when sending to another target.

## When it synchronizes

On source updates, Home Assistant startup, automation reload, target mode
changes, and every minute. Recovery of a writable temperature input also
triggers a check. Each target must still be in external mode when its turn runs.
An unavailable or failed target does not prevent updates to the others.

## Source validity and notifications

Home Assistant converts valid °C, °F, and K readings to Celsius before averaging.
Unavailable, nonnumeric, unsupported-unit, and expired readings are excluded.
If none remain, updates stop until a valid source returns; the blueprint does
not switch targets back to internal mode.

Validity measures time since the temperature **state last changed**. Identical
readings and attribute-only updates do not extend it. Expiration is checked
every minute; restarting Home Assistant may extend validity.

Enable **Temperature source notifications** for one English persistent
notification listing unavailable, invalid, or expired sources. It clears when
no issues remain. Sources belonging to selected targets are omitted from alerts.
After turning notifications off, reload automations to clear an existing alert.

The average is converted to each writable input's unit. Values must fit that
target's accepted range; TRV-ZBL through ZHA accepts **−30 to 100 °C**.

## Example and verification

Two external sensors read **20 °C** and **22 °C**. Select a TP-WGZBA and a TRVZB:
both receive a **21 °C measured external temperature**, not a heating setpoint.
If the 20 °C source expires, the remaining source supplies **22 °C**.

1. Enable external mode on each target and cause a real source temperature change.
2. Check each device's external temperature input or remote reading. With the
   example above, expect **21 °C** on every eligible target.
3. Open the automation's **Traces** and confirm the writes ran for each target.
4. If notifications are enabled, make a source unavailable and check the alert;
   restore a valid reading and confirm it clears when no other issues remain.

The device's main display may show a different quantity. See
[Check your automation](../../../checking/) for common checks. The guide is
based on source and offline validation; live Home Assistant and hardware
validation has not been performed here.
