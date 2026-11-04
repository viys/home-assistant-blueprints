"""Check language-independent entity selection in both ZBL blueprints."""

import unittest

from test_remote_temperature_links import CASES, single_source
from test_remote_temperature_sources_link_trv_zbl import sources


class ZblEntitySelectionTests(unittest.TestCase):
    """Use selected entities instead of translated names or English suffixes."""

    def instances(self, integration):
        """Yield both actual blueprints and their source event identifiers."""
        yield single_source(CASES[1], integration), "source_temperature", "sensor.source"
        yield sources(integration), "source_changed", "sensor.source1"

    def test_localized_and_renamed_controls(self):
        """Chinese, German and arbitrary names all route to the selected control."""
        for suffix in ("wai_bu_wen_du", "externer_temperatursensor", "renamed_control_42"):
            for integration in ("zha", "mqtt"):
                for run, trigger, source in self.instances(integration):
                    with self.subTest(file=run.file.name, integration=integration, suffix=suffix):
                        domain = "switch" if integration == "zha" else "number"
                        entity = f"{domain}.{suffix}"
                        input_name = "external_temperature_switch" if integration == "zha" else "external_temperature_input"
                        # Remove every conventional target name: only the selected entity exists.
                        run.entity_map["target"] = [entity]
                        run.inputs[input_name] = entity
                        run.set_state(entity, "on" if integration == "zha" else "0")
                        run.fire(trigger, entity=source)
                        self.assertEqual(len(run.calls), 1)
                        if integration == "mqtt":
                            self.assertEqual(run.calls[0]["target"], {"entity_id": entity})
                            self.assertEqual(run.calls[0]["data"]["value"], 20)
                        else:
                            self.assertEqual(run.calls[0]["data"]["value"], 2000)
                            run.calls.clear()
                            run.set_state(entity, "off")
                            run.fire(trigger, entity=source)
                            self.assertEqual(run.calls, [])
                            run.dispatch_state(entity, {"state": "off"}, run.set_state(entity, "on"))
                            self.assertTrue(run.calls)

    def test_missing_or_foreign_selection_does_not_fall_back_to_names(self):
        """Existing English-named controls must not silently override configuration."""
        for integration in ("zha", "mqtt"):
            for selection in ("", "switch.other" if integration == "zha" else "number.other"):
                for run, trigger, source in self.instances(integration):
                    input_name = "external_temperature_switch" if integration == "zha" else "external_temperature_input"
                    run.inputs[input_name] = selection
                    if selection:
                        run.set_state(selection, "on" if integration == "zha" else "0")
                    run.fire(trigger, entity=source)
                    self.assertEqual(run.calls, [], (run.file.name, integration, selection))


if __name__ == "__main__":
    unittest.main()
