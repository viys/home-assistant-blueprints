# Focused blueprint checks

Requires Python, PyYAML, and Jinja2. From the repository root:

```powershell
python -m unittest discover -s tests -v
git diff --check
```

The SNZB-02DR2 checks interpret the actual blueprint YAML with a small test
runner. They inject source changes during service calls, supported HA errors,
and queue overflow to verify independent validation, latest-value draining,
slot-selection ordering, startup behavior, and temperature conversion. Separate
tests verify that raw exceptions/timeouts propagate instead of claiming they
are handled by `continue_on_error`.

These are logic checks, not a Home Assistant integration test. Import into
Home Assistant 2025.3 or newer and exercise both ZHA and Zigbee2MQTT before
release. In particular, verify actual service timeout completion and logs.

The blueprint has the following explicit limitations:

- `continue_on_error` handles supported `HomeAssistantError` subclasses only.
  The raw ZHA attribute service can propagate external ZHA exceptions and raw
  timeouts; those still abort the active worker and can leave pending readings
  unsent. A later fresh trigger can start a new run, but recovery without that
  trigger is not guaranteed for these exceptions.
- A YAML service action has no generic hard-deadline option. The blueprint
  relies on integration/transport timeouts and cannot release an indefinitely
  suspended service or impose a fixed whole-call deadline on coordinator backlogs.
- If ZHA returns a negative ZCL status without raising, the service does not
  expose that status to this blueprint. The blueprint cannot detect a failed
  slot selection in that case. It skips the value write only when selection raises.
- Serialization applies within one automation instance, not across separate
  automations writing to the same device.

Consequently this change does not close every acceptance criterion of issue #8.
Strict ZHA failure isolation and hard timeouts need integration-level support
or an execution component beyond a standalone automation blueprint.
