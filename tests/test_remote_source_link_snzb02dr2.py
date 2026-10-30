"""Focused blueprint execution tests; requires PyYAML and Jinja2, not a HA server."""

from collections import deque
from pathlib import Path
import unittest

from tools.blueprint_runner import BlueprintRunner, is_number


BLUEPRINT = Path(__file__).resolve().parents[1] / "automation/sonoff/remote_source_link_snzb02dr2.yaml"


class Runner(BlueprintRunner):
    """Interpret this blueprint's YAML control flow with injected service outcomes."""

    def __init__(self, integration="zha", humidity="sensor.humidity"):
        """Create one automation instance with independently mutable sources."""
        # Scheduling remains specific to this blueprint's queued latest-value worker.
        super().__init__(BLUEPRINT, dict(target_device="target", source_temperature="sensor.temperature",
                                        source_humidity=humidity, source_slot="1"))
        self.integration = integration
        self.set_state("sensor.temperature", "20", "°C")
        self.set_state("sensor.humidity", "45", "%")
        self.pending = deque()
        self.running = False
        self.rejected = 0
        self.target_entities = ["number.target_source_1_temperature", "number.target_source_1_humidity"]

    def submit(self, trigger_id):
        """Render a trigger context and model HA's queued/single admission limit."""
        # The retained queued context records both source versions before later events.
        scope = dict(states=self.states, trigger={"id": trigger_id},
                     is_number=is_number,
                     state_attr=lambda entity, key: self.states[entity]["attributes"].get(key) if self.states[entity] else None,
                     device_entities=lambda device: self.target_entities,
                     device_attr=lambda device, key: {"manufacturer": "SONOFF", "model": "SNZB-02DR2", "model_id": "SNZB-02DR2", "identifiers": [(self.integration, "00:11")]}[key])
        self.variables(self.doc["variables"], scope)
        if not self.condition(self.doc.get("conditions", []), scope):
            return
        scope = self.scope_factory(scope)
        maximum = self.doc.get("max", 10) if self.doc.get("mode") == "queued" else 1
        if int(self.running) + len(self.pending) >= maximum:
            self.rejected += 1
            return
        self.pending.append(scope)
        if self.running:
            return
        self.running = True
        try:
            while self.pending:
                self.execute(self.doc["actions"], self.pending.popleft())
        finally:
            self.running = False

    def values(self):
        """Return value writes, separating them from ZHA slot-selection commands."""
        # MQTT identifies the source via its number entity; ZHA uses separate attributes.
        result = []
        for call in self.calls:
            data = call["data"]
            if call["action"] == "number.set_value":
                kind = "temperature" if "temperature" in call["target"]["entity_id"] else "humidity"
                result.append((kind, data["value"]))
            elif data["attribute"] in (0xFFF3, 0xFFF4):
                result.append(("temperature" if data["attribute"] == 0xFFF3 else "humidity", data["value"] / 100))
        return result


class SourceSyncTests(unittest.TestCase):
    """Verify independent data paths and recovery using the real YAML definitions."""

    def test_independent_updates_and_units(self):
        """A source event writes only that source, including F/K conversion."""
        # Both integrations must preserve the optional-input and conversion contracts.
        for integration in ("zha", "mqtt"):
            for unit, value in (("°C", "20"), ("°F", "68"), ("K", "293.15")):
                run = Runner(integration, humidity="")
                run.set_state("sensor.temperature", value, unit)
                run.submit("temperature_changed")
                self.assertEqual(run.values(), [("temperature", 20)])
            run = Runner(integration)
            run.set_state("sensor.temperature", "unavailable")
            run.submit("humidity_changed")
            self.assertEqual(run.values(), [("humidity", 45)])
            run = Runner(integration)
            run.set_state("sensor.humidity", "unavailable")
            run.submit("temperature_changed")
            self.assertEqual(run.values(), [("temperature", 20)])

    def test_startup_and_missing_mqtt_temperature_target(self):
        """Startup retains integration-specific behavior and independent validity."""
        # Missing temperature entities must not suppress an available humidity target.
        run = Runner("zha")
        run.submit("ha_started")
        self.assertEqual(run.calls, [])
        run = Runner("mqtt")
        run.target_entities.remove("number.target_source_1_temperature")
        run.submit("ha_started")
        self.assertEqual(run.values(), [("humidity", 45)])

    def test_slot_failure_does_not_send_value_or_block_other_source(self):
        """Abort a failed ZHA pair while allowing later independent measurements."""
        # Never send a value after failing to select its target slot.
        run = Runner()
        run.fail.add(0xFFF1)
        run.submit("temperature_changed")
        self.assertEqual(run.values(), [])
        run.submit("humidity_changed")
        self.assertEqual(run.values(), [("humidity", 45)])
        run.fail.clear()
        run.submit("temperature_changed")
        self.assertEqual(run.values()[-1], ("temperature", 20))

    def test_pending_burst_survives_handled_errors_and_queue_overflow(self):
        """Retain latest readings when an HA-supported error overlaps a full queue."""
        # This is not proof that ZHA translates its actual exceptions into HA errors.
        for integration in ("zha", "mqtt"):
            run = Runner(integration)
            failure = 0xFFF3 if integration == "zha" else "number.target_source_1_temperature"
            run.fail.add(failure)

            def burst(worker, call):
                """Submit a burst while the first temperature value is in flight."""
                # A one-shot hook avoids a fabricated infinite stream of changes.
                key = call["data"].get("attribute", call.get("target", {}).get("entity_id"))
                if key != failure:
                    return
                worker.hook = None
                for index in range(12):
                    worker.set_state("sensor.temperature", str(21 + index), "°C")
                    worker.submit("temperature_changed")
                    worker.set_state("sensor.humidity", str(46 + index), "%")
                    worker.submit("humidity_changed")

            run.hook = burst
            run.submit("temperature_changed")
            self.assertTrue(run.errors)
            self.assertGreater(run.rejected, 0)
            self.assertIn(("humidity", 57), run.values())
            self.assertIn(("temperature", 32), run.values())
            self.assertLess(len(run.calls), 20)
            run.fail.clear()
            run.set_state("sensor.temperature", "33", "°C")
            run.submit("temperature_changed")
            self.assertEqual(run.values()[-1], ("temperature", 33))

    def test_failed_humidity_does_not_starve_temperature(self):
        """Check the symmetric failure direction and later humidity recovery."""
        # A humidity write can fail while both sources change during its wait.
        for integration in ("zha", "mqtt"):
            run = Runner(integration)
            failure = 0xFFF4 if integration == "zha" else "number.target_source_1_humidity"
            run.fail.add(failure)

            def update_during_failure(worker, call):
                """Inject source updates into the failing humidity service call."""
                # The last updates need no further source event to be drained.
                key = call["data"].get("attribute", call.get("target", {}).get("entity_id"))
                if key == failure:
                    worker.hook = None
                    worker.set_state("sensor.temperature", "22", "°C")
                    worker.submit("temperature_changed")
                    worker.set_state("sensor.humidity", "52", "%")
                    worker.submit("humidity_changed")

            run.hook = update_during_failure
            run.submit("humidity_changed")
            self.assertIn(("temperature", 22), run.values())
            self.assertIn(("humidity", 52), run.values())
            self.assertTrue(run.errors)
            run.fail.clear()
            run.set_state("sensor.humidity", "53", "%")
            run.submit("humidity_changed")
            self.assertEqual(run.values()[-1], ("humidity", 53))

    def test_startup_temperature_failure_still_attempts_humidity(self):
        """A failed first MQTT write does not abort full-sync humidity."""
        # Full sync is the one path that intentionally attempts both sources.
        run = Runner("mqtt")
        run.fail.add("number.target_source_1_temperature")
        run.submit("ha_started")
        self.assertEqual(run.values(), [("temperature", 20), ("humidity", 45)])
        self.assertEqual(len(run.errors), 1)

    def test_invalid_or_self_sourced_reading_is_independent(self):
        """Skip invalid readings without writing fallback values or gating peers."""
        # Validate runtime data per measurement, not in a shared global condition.
        for integration in ("zha", "mqtt"):
            for value, unit in (("unknown", "°C"), ("unavailable", "°C"), ("20", "bad")):
                run = Runner(integration)
                run.set_state("sensor.temperature", value, unit)
                run.submit("temperature_changed")
                self.assertEqual(run.calls, [])
                run.submit("humidity_changed")
                self.assertEqual(run.values(), [("humidity", 45)])
            run = Runner(integration)
            run.target_entities.append("sensor.temperature")
            run.submit("humidity_changed")
            self.assertEqual(run.values(), [("humidity", 45)])
            for humidity in ("unknown", "unavailable", "100", "-1"):
                run = Runner(integration)
                run.set_state("sensor.humidity", humidity, "%")
                run.submit("humidity_changed")
                self.assertEqual(run.calls, [])
                run.submit("temperature_changed")
                self.assertEqual(run.values(), [("temperature", 20)])

    def test_source_event_filters_preserve_empty_humidity(self):
        """Check actual trigger filters rather than routing unrelated events as sources."""
        # Empty humidity is a nonmatching event filter, never a state-trigger entity.
        run = Runner(humidity="")
        for trigger in run.doc["triggers"][:2]:
            self.assertEqual(trigger["trigger"], "event")
            self.assertEqual(trigger["event_type"], "state_changed")
            entity = run.render(trigger["event_data"]["entity_id"], {})
            self.assertNotEqual(entity, "sensor.unrelated")
        self.assertEqual(run.render(run.doc["triggers"][1]["event_data"]["entity_id"], {}), "")

    def test_sustained_temperature_activity_does_not_starve_humidity(self):
        """Alternate turns drain humidity even while temperature keeps updating."""
        # Both latest values must be attempted after the finite burst ends.
        run = Runner()
        remaining = [8]

        def updates(worker, call):
            """Keep updating during temperature sends for several worker turns."""
            # A finite injection also detects workers that endlessly retry old snapshots.
            if call["data"].get("attribute") == 0xFFF3 and remaining[0]:
                remaining[0] -= 1
                worker.set_state("sensor.temperature", str(30 + remaining[0]), "°C")
                worker.submit("temperature_changed")
                worker.set_state("sensor.humidity", str(50 + remaining[0]), "%")
                worker.submit("humidity_changed")

        run.hook = updates
        run.submit("temperature_changed")
        self.assertEqual(remaining[0], 0)
        self.assertIn(("temperature", 30), run.values())
        self.assertIn(("humidity", 50), run.values())
        self.assertGreaterEqual(sum(kind == "humidity" for kind, _ in run.values()), 7)

    def test_raw_zha_timeout_remains_an_explicit_limitation(self):
        """Do not pretend continue_on_error handles raw TimeoutError or ZHA errors."""
        # HA ignores only supported HomeAssistantError subclasses, not arbitrary errors.
        for error_type in (TimeoutError, RuntimeError):
            run = Runner()
            run.failure_type = error_type
            run.fail.add(0xFFF1)
            with self.assertRaises(error_type):
                run.submit("temperature_changed")
            self.assertFalse(run.running)
            self.assertEqual(run.values(), [])
            run.fail.clear()
            run.submit("humidity_changed")
            self.assertEqual(run.values(), [("humidity", 45)])

    def test_unsupported_target_does_not_send(self):
        """Reject a target that belongs to neither supported integration."""
        # This exercises the common target guard's negative outcome.
        run = Runner("unsupported")
        run.submit("temperature_changed")
        self.assertEqual(run.calls, [])

    def test_missing_humidity_target_does_not_block_temperature(self):
        """Skip MQTT humidity when its target number entity cannot be found."""
        # The no-match choose path must not accidentally send to a different entity.
        run = Runner("mqtt")
        run.target_entities.remove("number.target_source_1_humidity")
        run.submit("humidity_changed")
        self.assertEqual(run.calls, [])
        run.submit("temperature_changed")
        self.assertEqual(run.values(), [("temperature", 20)])


if __name__ == "__main__":
    unittest.main()
