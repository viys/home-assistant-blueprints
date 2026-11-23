---
title: Start using a blueprint
description: Import a SONOFF blueprint, select your sources, and create an automation.
---

Import a blueprint once, then create an automation with your own devices and
sources. Importing the definition alone does not start synchronization.

## Before importing

- Add your target SONOFF device and external source sensors to Home Assistant.
- Check that source readings are available. Temperature sensors must report
  numeric readings in °C, °F, or K; temperature blueprints convert them to Celsius.
- Use a compatible ZHA device handler (quirk) or Zigbee2MQTT converter. Read the
  chosen guide for device, firmware, and integration requirements.
- Choose external sensors from other devices. A selected target's own sensor is
  not a valid external source.
- For measured-temperature synchronization, configure external temperature mode
  where the guide requires it. Avoid multiple automations writing temperatures
  to the same target or remote slot.

Check device support in the [ZHA quirks project](https://github.com/zigpy/zha-device-handlers)
or [Zigbee2MQTT converters project](https://github.com/Koenkk/zigbee-herdsman-converters).
Pairing a device does not establish support for every remote-source feature.

## Home Assistant version

Check your Core version in **Settings > About** and compare it with the
minimum version in the selected blueprint's **Before you start** section.
Upgrade before importing if your version is older than the requirement.

Core compatibility and device support are separate requirements: the correct
HA version alone does not ensure that the firmware or integration provides
the features needed by your chosen blueprint.

## Check device support

1. Read the selected blueprint's **Before you start** section for supported
   integrations, firmware requirements, and required device features.
2. Open the target under **Settings > Devices & services**. For Zigbee2MQTT,
   also check the device's **Exposes** tab. Confirm the required inputs and
   settings are available; labels vary by integration and language.
3. If a required feature is missing, check the device's support in the
   [ZHA handlers](https://github.com/zigpy/zha-device-handlers) or
   [Zigbee2MQTT converters](https://github.com/Koenkk/zigbee-herdsman-converters).

Pairing alone does not establish support for every blueprint feature. Some
capabilities are not exposed as individual entities; check the handler or
converter's support as well. Model-specific limits are listed in each
blueprint guide.

## Import the blueprint

1. Open the blueprint's guide and select **Import blueprint**.
2. Review the preview in your Home Assistant instance and import it.
3. If the button cannot open your instance, expand **Other download options**
   and copy the guide's **Raw YAML** link.
   Go to **Settings > Automations & scenes > Blueprints > Import blueprint**,
   paste the address, then select **Preview** and **Import blueprint**.

Import buttons in this manual use the stable `master` branch. **Dev YAML**, under
**Other download options**, is for testing development changes.

## Create an automation

1. Select the imported blueprint in **Settings > Automations & scenes > Blueprints**.
2. Fill in the target device, source sensors, and optional settings using the
   guide's input table.
3. Save with a recognizable name, such as **Living room external temperature**.
4. Confirm the automation is enabled.

For another target, create another automation unless the chosen blueprint
supports multiple targets. For slot-based blueprints, follow the guide's
one-automation-per-slot instructions.

## Check the first update

Cause a selected sensor to update. For the target-temperature blueprint, change
the panel's setpoint instead. Check the target's exposed remote reading or
setpoint and the automation's **Traces**.

A manually executed action does not reproduce all the event data provided by a
real trigger. Follow [Check your automation](../checking/) if the result does
not arrive.

See Home Assistant's [official blueprint instructions](https://www.home-assistant.io/docs/automation/using_blueprints/)
for more about importing and creating automations.
