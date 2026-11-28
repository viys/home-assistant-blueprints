---
title: Link Door and Window Sensors to TP-WGZBA
description: Pause a TP-WGZBA when any selected door or window opens.
slug: blueprints/tp-wgzba/door_window_link_tp_wgzba
blueprint: door_window_link_tp_wgzba
sidebar:
  label: Door and window sensors
  order: 5
---

Link one or more door and window sensors to a TP-WGZBA. Home Assistant sends
an open input when any selected sensor opens, and a closed input only when
every selected sensor is closed.

[![Selected contacts feed Home Assistant, which sends one combined open or closed input to a TP-WGZBA.](/home-assistant-blueprints/diagrams/door_window_link_tp_wgzba.svg)](/home-assistant-blueprints/diagrams/door_window_link_tp_wgzba.svg)

## Before you start

- Home Assistant Core **2025.4.0 or later**.
- One TP-WGZBA connected through **ZHA**, with firmware and a custom quirk
  that support external contact sensor input.
- One or more binary sensors with the **door**, **window**, or **opening**
  device class. Their raw states must be `on` for open and `off` for closed.
  The contacts can use any integration that supplies these states.

This blueprint is awaiting release. Use **Development YAML** under
**Other download options** once the change is available on `dev`;
the stable import becomes available after release.

## Configure the automation

Follow [the import and creation steps](../../../getting-started/), then select
the panel and contacts below.

| Input | What to select |
| --- | --- |
| **TP-WGZBA device** | The ZHA panel that should receive the combined contact state. |
| **Door and window sensors** | One or more door, window, or opening sensors to monitor together. |

Use one contact-linking automation per panel so separate automations do not
overwrite each other's open and closed inputs. This automation sends contact
state; it does not forward measured temperatures or target setpoints.

## When it synchronizes

- When the combined state changes from no open contacts to at least one open
  contact, it sends **open**.
- When every selected contact becomes explicitly closed, it sends **closed**.
- After Home Assistant starts, it sends the current state if at least one
  contact is open or every contact is closed.

Saving or re-enabling the automation does not explicitly synchronize the current
state. Change a contact state to test it. There is no periodic refresh.

## Multiple contacts and manual exit

If a door opens and then a window opens, the second opening does not resend
**open**. Closing just the door also sends nothing while the window remains
open. Closing the last open contact sends **closed**.

This allows a manual exit from the panel's contact pause to remain in effect
while the combined open state stays unchanged. A new open cycle can apply the
pause again. Restarting Home Assistant can also reapply an open input.

## Unavailable contacts

`unknown`, `unavailable`, and missing contacts never count as closed. If no
contact is open but a selected contact is unavailable, the automation sends
nothing; it does not clear an earlier open input.

When an open contact recovers after all open contacts became unavailable,
the combined state becomes open again and sends a new **open** input. This
can reapply the pause after a manual exit on the panel.

## Confirm the result

1. Start with all selected contacts closed, then open one. Confirm the panel
   shows **OP** for contact pause and the automation's **Traces** shows an open write.
2. Open a second contact, then close the first. Confirm there is no additional
   write while at least one contact remains open.
3. Close the last contact. Confirm the trace shows a closed write and the
   panel clears its external open input.

Offline tests cover aggregation and action data. Import in the declared minimum
HA version and real panel behavior have not been validated for this blueprint.
A failed write is not retried periodically; check the trace if the panel does
not respond.

## Stop using the automation

After disabling or deleting the automation, turn off the panel's **External
contact sensor** switch to clear any remaining input. Disabling the automation
does not send a final closed state.

See [Check your automation](../../../checking/) and
[Update a blueprint](../../../updating/) for the common procedures.
