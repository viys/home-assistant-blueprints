---
title: Sync Remote Sensor to SNZB-02DR2
description: Supply temperature and optional humidity to a remote slot on SNZB-02DR2.
slug: blueprints/snzb02dr2/remote_source_link_snzb02dr2
blueprint: remote_source_link_snzb02dr2
sidebar:
  label: Remote temperature and humidity
  order: 1
---

Supply temperature and optional humidity to a remote slot on SNZB-02DR2.

[![Supply temperature and optional humidity to a remote slot on SNZB-02DR2.](/home-assistant-blueprints/diagrams/remote_source_link_snzb02dr2.svg)](/home-assistant-blueprints/diagrams/remote_source_link_snzb02dr2.svg)

[Open full-size diagram](/home-assistant-blueprints/diagrams/remote_source_link_snzb02dr2.svg).

## Before you start

- Home Assistant Core **2025.4.0 or later**.
- [Check device support](../../../getting-started/#check-device-support) for your integration before importing.
- Select sensors from other devices, with numeric temperatures in °C, °F, or K.
- Temperature is required in the form; humidity is optional. Humidity readings must be between 0 and 99.9%.
- Use one automation per populated slot, with no competing writers.

Temperature and humidity are validated and sent independently. An invalid source
does not prevent the other valid source from being sent. Supplying remote readings
does not select the device display or configure relay rules.

## Configure the automation

Follow [the import and creation steps](../../../getting-started/), then fill in
the fields below and save the automation.

| Input | What to select |
| --- | --- |
| **SNZB-02DR2 device** | Select the ZHA or Zigbee2MQTT SNZB-02DR2 to receive the reading. |
| **External temperature sensor** | Required. Select a temperature sensor from a different device. |
| **External humidity sensor (optional)** | Select a relative humidity sensor from a different device. |
| **Remote slot** | Slot 1 or Slot 2. Default: **Slot 1**. |

## When it synchronizes

On selected source updates. Zigbee2MQTT also synchronizes on Home Assistant startup; ZHA waits for source updates. Changes received during a send are handled afterwards using the latest readings.

## Example

Choose a bedroom temperature sensor, optional humidity sensor, and **Slot 1**. A **21 °C** update supplies its temperature; a **45%** humidity update supplies its humidity independently. Create another automation for **Slot 2** if needed.

## Confirm the result

1. Change the selected temperature or humidity source and open the SNZB-02DR2
   device under **Settings > Devices & services**.
2. Check the selected remote slot: for a **21 °C** source and **45%** humidity,
   expect those values in that slot where the integration exposes them.
3. Open the automation's **Traces**. Temperature and humidity are sent independently;
   check the branch for the reading you changed.

If the device screen shows another value, check its selected display source.
This blueprint supplies readings but does not select what the screen displays.

See [Check your automation](../../../checking/) and
[Update a blueprint](../../../updating/) for the common procedures.
