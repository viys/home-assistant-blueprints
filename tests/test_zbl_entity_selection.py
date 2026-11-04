"""Check automatic, language-independent ZBL mode discovery."""

import unittest

from test_remote_temperature_links import CASES, single_source
from test_remote_temperature_sources_link_trv_zbl import sources


class ZblEntitySelectionTests(unittest.TestCase):
    def instances(self, integration="zha"):
        yield single_source(CASES[1], integration), "source_temperature", "sensor.source"
        yield sources(integration), "source_changed", "sensor.source1"

    def status(self, run, entity, value="external_sensor", **attrs):
        return run.set_state(entity, value, device_class="enum",
                             options=["internal_sensor", "external_sensor"], **attrs)

    def test_localized_and_renamed_status_without_selection(self):
        for suffix in ("wen_du_lai_yuan", "temperaturquelle", "renamed_42"):
            for run, trigger, source in self.instances():
                with self.subTest(file=run.file.name, suffix=suffix):
                    entity = f"sensor.{suffix}"
                    run.entity_map["target"] = [entity]
                    run.inputs["external_temperature_control"] = ""
                    self.status(run, entity, friendly_name="任意名称")
                    run.fire(trigger, entity=source)
                    self.assertEqual(run.calls[0]["data"]["value"], 2000)
                    run.calls.clear()
                    old = self.status(run, entity, "internal_sensor")
                    run.fire(trigger, entity=source)
                    self.assertEqual(run.calls, [])
                    run.dispatch_state(entity, old, self.status(run, entity))
                    self.assertEqual(len(run.calls), 5 if "sources" in run.file.name else 1)

    def test_missing_foreign_ambiguous_unavailable_status_skips(self):
        for problem in ("missing", "foreign", "duplicate", "unavailable", "unknown", "wrong_options"):
            for run, trigger, source in self.instances():
                with self.subTest(file=run.file.name, problem=problem):
                    entity = "sensor.target_temperature_source_mode"
                    if problem in ("missing", "foreign"):
                        run.entity_map["target"].remove(entity)
                    elif problem == "duplicate":
                        run.entity_map["target"].append("sensor.duplicate")
                        self.status(run, "sensor.duplicate")
                    elif problem == "wrong_options":
                        run.set_state(entity, "external_sensor", device_class="enum", options=["off", "on"])
                    else:
                        self.status(run, entity, problem)
                    # A legacy switch selection/name must not bypass the status contract.
                    run.inputs["external_temperature_control"] = "switch.target_external_temperature_sensor"
                    run.set_state("switch.target_external_temperature_sensor", "on")
                    run.fire(trigger, entity=source)
                    self.assertEqual(run.calls, [])

    def test_mqtt_localized_input_and_invalid_selection(self):
        for run, trigger, source in self.instances("mqtt"):
            entity = "number.renamed_input"
            run.entity_map["target"] = [entity]
            run.inputs["external_temperature_control"] = entity
            run.fire(trigger, entity=source)
            self.assertEqual(run.calls[0]["target"], {"entity_id": entity})
            for selection in ("", "number.other", "switch.wrong_type"):
                run.calls.clear()
                run.inputs["external_temperature_control"] = selection
                run.fire(trigger, entity=source)
                self.assertEqual(run.calls, [])

    def test_control_input_is_optional_and_mqtt_only(self):
        for run, _, _ in self.instances():
            control = run.doc["blueprint"]["input"]["external_temperature_control"]
            self.assertEqual(control["default"], "")
            self.assertEqual(control["selector"]["entity"]["filter"],
                             [dict(domain="number", integration="mqtt")])


if __name__ == "__main__":
    unittest.main()
