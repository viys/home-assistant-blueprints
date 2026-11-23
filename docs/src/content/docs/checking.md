---
title: Check your automation
description: Check sources, integration support, triggers, and automation traces.
---

Start with the source reading and target settings, then exercise a real trigger
and inspect the automation trace.

## The target device is missing

Check that it is paired through an integration supported by your chosen blueprint
and has the correct model. The device guide describes source and target support
separately where they differ.

## A source is unavailable

Choose a sensor from another device. Temperature readings must be numeric and
report °C, °F, or K. `unknown` and `unavailable` cannot be sent as temperatures.
For optional humidity, choose a relative humidity sensor.

## A reading does not arrive

1. Confirm the automation is saved and enabled.
2. Check the target's external temperature setting where required.
3. Check the guide's supported integration, firmware, converter or quirk, and
   source count.
4. Cause a real source update and open **Traces** on the automation. For target
   temperature linking, change the selected source device's setpoint instead.
5. Check that another automation is not overwriting the target reading.

Startup, automation reload, and temperature-mode changes are not universal
triggers. The individual guide lists when its blueprint synchronizes.

## An average excludes a source

Average blueprints exclude invalid, unavailable, self-sourced, and expired
readings. Their validity period measures time since the numeric state last
changed. Identical reports and attribute-only updates do not extend it.
Expiration is checked every minute; a Home Assistant restart may extend validity.

If no valid source remains, synchronization stops. These blueprints do not send
zero as a replacement reading. Choose a validity period suitable for how often
your source temperatures change.

## Report a problem

Check [GitHub Issues](https://github.com/viys/home-assistant-blueprints/issues) for
known defects. Include the blueprint name and source branch, Home Assistant
version, device firmware, integration and quirk/converter version, the expected
and observed result, and an automation trace with personal information removed.
