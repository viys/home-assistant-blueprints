"""Behavior checks for the TRVZBT remote temperature blueprint."""

import unittest

from common.single_source_checks import SingleSourceChecks, single_source


class RemoteTemperatureTests(SingleSourceChecks, unittest.TestCase):
    """Run the shared single-source scenarios for this blueprint."""

    cases = (("remote_temperature_link_trvzbt.yaml", "TRV-ZBT",
              "Zigbee thermostatic radiator valve", None),)

    def test_trvzbt_accepts_alternative_zha_switch_name(self):
        """Support both selector-switch entity suffixes declared in the ZBT YAML."""
        # The fixture must not hard-code only the older switch naming pattern.
        run = single_source(self.cases[0])
        run.entity_map["target"][0] = "switch.target_temperature_sensor_select"
        run.set_state("switch.target_temperature_sensor_select", "on")
        run.fire("source_temperature")
        self.assertEqual(run.calls[0]["data"]["value"], 20)

    def test_numbered_entities_support_both_zha_switch_names_and_mqtt_input(self):
        """A selected ZBT may have an HA-generated duplicate-name suffix."""
        # Verify discovery and the ZHA mode-enable path without changing MQTT policy.
        for integration in ("zha", "mqtt"):
            for switch_suffix in ("external_temperature_sensor", "temperature_sensor_select"):
                for suffix in ("_2", "_3", "_12"):
                    with self.subTest(integration=integration, switch=switch_suffix, suffix=suffix):
                        run = single_source(self.cases[0], integration)
                        run.entity_map["target"][0] = "switch.target_" + switch_suffix
                        run.set_state(run.entity_map["target"][0], "on")
                        entities = list(run.entity_map["target"])
                        run.entity_map["target"] = [entity + suffix for entity in entities]
                        for entity in entities:
                            snapshot = run.states[entity]
                            if snapshot:
                                run.set_state(entity + suffix, snapshot["state"], **snapshot["attributes"])
                        run.fire("source_temperature")
                        destination = ("number.target_external_temperature_sensor_value" if integration == "zha"
                                       else "number.target_external_temperature_input") + suffix
                        self.assertEqual([call["target"]["entity_id"] for call in run.calls], [destination])
                        self.assertEqual(run.calls[0]["data"]["value"], 20)
                        if integration == "zha":
                            run.calls.clear()
                            mode = run.entity_map["target"][0]
                            old = run.set_state(mode, "off")
                            new = run.set_state(mode, "on")
                            run.dispatch_state(mode, old, new)
                            self.assertEqual([call["target"]["entity_id"] for call in run.calls], [destination])
