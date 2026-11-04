"""Check automatic, language-independent ZBL mode discovery."""

import unittest

from test_remote_temperature_links import CASES, single_source
from test_remote_temperature_sources_link_trv_zbl import sources


class ZblEntitySelectionTests(unittest.TestCase):
    def instances(self, integration="zha"):
        yield single_source(CASES[1], integration), "source_temperature", "sensor.source"
        yield sources(integration), "source_changed", "sensor.source1"

    def status(self, run, entity, value="external_sensor", **attrs):
        return run.set_state(entity, value, device_class="enum", **attrs)

    def test_real_ha_enum_state_without_options_enables_sync(self):
        """HA enum sensors publish device_class and state, but not options."""
        for run, trigger, source in self.instances():
            entity = "sensor.target_temperature_source_mode"
            run.set_state(entity, "external_sensor", device_class="enum")
            run.fire(trigger, entity=source)
            self.assertEqual(len(run.calls), 1, run.file.name)

    def test_localized_and_renamed_status_without_selection(self):
        for suffix in ("wen_du_lai_yuan", "temperaturquelle", "renamed_42"):
            for run, trigger, source in self.instances():
                with self.subTest(file=run.file.name, suffix=suffix):
                    entity = f"sensor.{suffix}"
                    run.entity_map["target"] = [entity]
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
        for problem in ("missing", "foreign", "duplicate", "unavailable", "unknown", "wrong_state"):
            for run, trigger, source in self.instances():
                with self.subTest(file=run.file.name, problem=problem):
                    entity = "sensor.target_temperature_source_mode"
                    if problem in ("missing", "foreign"):
                        run.entity_map["target"].remove(entity)
                    elif problem == "duplicate":
                        run.entity_map["target"].append("sensor.duplicate")
                        self.status(run, "sensor.duplicate")
                    elif problem == "wrong_state":
                        run.set_state(entity, "other_mode", device_class="enum")
                    else:
                        self.status(run, entity, problem)
                    # A legacy switch selection/name must not bypass the status contract.
                    run.inputs["external_temperature_control"] = "switch.target_external_temperature_sensor"
                    run.set_state("switch.target_external_temperature_sensor", "on")
                    run.fire(trigger, entity=source)
                    self.assertEqual(run.calls, [])

    def test_mqtt_localized_input_is_discovered_without_selection(self):
        for suffix in ("wai_bu_wen_du", "externe_temperatur", "renamed_42"):
            for run, trigger, source in self.instances("mqtt"):
                entity = f"number.{suffix}"
                run.entity_map["target"] = [entity, "number.frost_temperature"]
                run.set_state(entity, "20", "°C", min=0, max=99.9, step=0.1)
                run.set_state("number.frost_temperature", "5", "°C", min=4, max=10, step=0.5)
                run.fire(trigger, entity=source)
                self.assertEqual(run.calls[0]["target"], {"entity_id": entity})
                self.assertEqual(run.calls[0]["data"]["value"], 20)

    def test_mqtt_missing_foreign_ambiguous_and_wrong_attributes_skip(self):
        for problem in ("missing", "foreign", "duplicate", "unit", "min", "max", "step", "domain"):
            for run, trigger, source in self.instances("mqtt"):
                with self.subTest(file=run.file.name, problem=problem):
                    entity = "number.target_external_temperature_input"
                    attrs = dict(min=0, max=99.9, step=0.1)
                    if problem in ("missing", "foreign"):
                        run.entity_map["target"] = []
                    elif problem == "duplicate":
                        run.entity_map["target"].append("number.duplicate")
                        run.set_state("number.duplicate", "20", "°C", **attrs)
                    elif problem == "domain":
                        run.entity_map["target"] = ["sensor.wrong_domain"]
                        run.set_state("sensor.wrong_domain", "20", "°C", **attrs)
                    else:
                        if problem in attrs:
                            attrs[problem] = 1
                        run.set_state(entity, "20", "°F" if problem == "unit" else "°C", **attrs)
                    # Old automation inputs cannot override automatic discovery.
                    run.inputs["external_temperature_control"] = entity
                    run.fire(trigger, entity=source)
                    self.assertEqual(run.calls, [])

    def test_control_selector_is_removed(self):
        for run, _, _ in self.instances():
            self.assertNotIn("external_temperature_control", run.doc["blueprint"]["input"])


if __name__ == "__main__":
    unittest.main()
