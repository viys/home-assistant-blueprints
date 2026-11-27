"""Exercise the shared SONOFF average pipeline and model-specific transports offline."""

from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import unittest

from tests.common.entity_discovery import NUMBERED_ENTITY_IDS, assert_entity_id_compatibility
from tools.blueprint_runner import BlueprintRunner


BLUEPRINT = Path(__file__).resolve().parents[1] / "automation/sonoff/remote_temperature_average_link_sonoff_thermostatic.yaml"
MODELS = ("TRVZB", "TRV-ZBT", "TP-WGZBA", "TRV-ZBL")
ATTRIBUTE_TARGETS = {("TP-WGZBA", "zha"): 0x7009, ("TRV-ZBL", "zha"): 0xFF02}
TARGETS = tuple((model, integration) for model in MODELS for integration in ("zha", "mqtt"))


def average_runner(model="TRVZB", integration="zha", targets=None):
    """Bind one or more model/integration pairs to explicit controls and external sources."""
    # All controls belong to their target device; unrelated devices cannot supply a match.
    targets = targets if targets is not None else [(model, integration)]
    run = BlueprintRunner(BLUEPRINT, dict(target_devices=[f"t{index}" for index in range(len(targets))],
                                         source_entities=["sensor.source", "sensor.second"]))
    run.doc["variables"]["this"] = {"entity_id": "automation.sonoff_average"}
    run.set_state("sensor.source", "20", "°C")
    run.set_state("sensor.second", "24", "°C")
    for index, (model, integration) in enumerate(targets):
        device = f"t{index}"
        run.devices[device] = dict(manufacturer="SONOFF", model_id=model,
                                  model=model if integration == "zha" else (
                                      "Zigbee thermostat panel" if model == "TP-WGZBA"
                                      else "Zigbee thermostatic radiator valve"),
                                  identifiers=[(integration, f"00:{index:02}")])
        if integration == "mqtt":
            mode, value = f"select.{device}_temperature_sensor_select", f"number.{device}_external_temperature_input"
            run.entity_map[device] = [mode, value]
            run.set_state(mode, "remote_temperature")
            run.set_state(value, "20", "°C", min=0, max=99.9, step=0.1)
        elif model in ("TP-WGZBA", "TRV-ZBL"):
            mode = f"sensor.{device}_temperature_source_mode"
            run.entity_map[device] = [mode]
            run.set_state(mode, "external_sensor", device_class="enum")
        else:
            mode, value = f"switch.{device}_external_temperature_sensor", f"number.{device}_external_temperature_sensor_value"
            run.entity_map[device] = [mode, value]
            run.set_state(mode, "on")
            run.set_state(value, "20", "°C")
    return run


class SharedAverageTests(unittest.TestCase):
    """Validate a shared source group across all supported destination combinations."""

    def test_mixed_models_and_integrations_receive_the_converted_average(self):
        """Use a single automation for all eight destination paths and round at dispatch."""
        # The mean is 21.666..., encoded as 2167 for raw ZHA attributes and 21.7 for number entities.
        run = average_runner(targets=TARGETS)
        run.inputs["source_entities"].append("sensor.third")
        run.set_state("sensor.source", "68", "°F")
        run.set_state("sensor.second", "297.15", "K")
        run.set_state("sensor.third", "21", "°C")
        run.fire("periodic_sync")
        self.assertEqual(len(run.calls), len(TARGETS))
        self.assertEqual([call["data"]["value"] for call in run.calls], [21.7] * 4 + [2167, 21.7, 2167, 21.7])
        self.assertEqual(run.calls[4]["data"], dict(ieee="00:04", endpoint_id=1, cluster_id=0xFC11,
                                                   cluster_type="in", attribute=0x7009, value=2167))
        self.assertEqual([call["target"]["entity_id"] for call in run.calls if "target" in call],
                         ["number.t0_external_temperature_sensor_value", "number.t1_external_temperature_input",
                          "number.t2_external_temperature_sensor_value", "number.t3_external_temperature_input",
                          "number.t5_external_temperature_input", "number.t7_external_temperature_input"])

    def test_each_full_sync_trigger_reaches_all_distinct_targets(self):
        """Startup, reload, periodic and source triggers preserve mixed-model fan-out."""
        # Duplicate device selections must never create duplicate writes.
        run = average_runner(targets=TARGETS)
        run.inputs["target_devices"].append("t0")
        for trigger in ("ha_started", "automation_reloaded", "periodic_sync", "source_changed"):
            run.calls.clear()
            run.fire(trigger)
            writes = [call for call in run.calls if call["action"] != "persistent_notification.dismiss"]
            self.assertEqual(len(writes), len(TARGETS))
        self.assertEqual(run.doc["mode"], "queued")

    def test_duplicate_sources_and_all_targets_own_sensors_are_excluded(self):
        """Selected targets cannot feed their measured temperatures back into the group."""
        # Even a sensor on the last target must be excluded from the first target's average.
        run = average_runner(targets=TARGETS)
        run.inputs["source_entities"] += ["sensor.source", "sensor.self"]
        run.entity_map[f"t{len(TARGETS) - 1}"].append("sensor.self")
        run.set_state("sensor.self", "90", "°C")
        run.fire("periodic_sync")
        self.assertEqual([call["data"]["value"] for call in run.calls], [22] * 4 + [2200, 22, 2200, 22])

    def test_invalid_sources_are_excluded_without_blocking_valid_peers(self):
        """Reject missing, unavailable, nonfinite and unsupported-unit source values."""
        # The remaining valid sensor must still drive each destination.
        for value, unit in ((None, "°C"), ("unknown", "°C"), ("unavailable", "°C"),
                            ("bad", "°C"), ("nan", "°C"), ("inf", "°C"), ("20", "bad")):
            with self.subTest(value=value, unit=unit):
                run = average_runner(targets=TARGETS)
                if value is None:
                    del run.states["sensor.source"]
                else:
                    run.set_state("sensor.source", value, unit)
                run.fire("periodic_sync")
                self.assertEqual([call["data"]["value"] for call in run.calls], [24] * 4 + [2400, 24, 2400, 24])

    def test_expiration_boundary_and_same_value_recovery(self):
        """Expired sources stop writes and recover after an unavailable transition."""
        # Attribute-only updates and repeated values preserve the source's last_changed clock.
        run = average_runner(targets=TARGETS)
        run.inputs.update(source_entities=["sensor.source"], source_timeout=1)
        run.clock += timedelta(seconds=60)
        run.set_state("sensor.source", "20", "°C", battery=90)
        run.fire("periodic_sync")
        self.assertEqual(run.calls, [])
        run.set_state("sensor.source", "unavailable", "°C")
        old = run.states["sensor.source"]
        new = run.set_state("sensor.source", "20", "°C")
        run.dispatch_state("sensor.source", old, new)
        self.assertEqual(len(run.calls), len(TARGETS))

    def test_empty_source_or_target_selection_never_broadcasts(self):
        """Defensive empty inputs cannot send a temperature or broadcast a service call."""
        # A target-less service action is never constructed.
        for name in ("target_devices", "source_entities"):
            run = average_runner()
            run.inputs[name] = []
            run.fire("periodic_sync")
            self.assertEqual(run.calls, [])

    def test_live_modes_and_freshness_are_rechecked_for_later_targets(self):
        """A slow or changing first destination cannot send stale data to later targets."""
        # Simulate elapsed time during the first service call rather than changing queue inputs.
        run = average_runner(targets=TARGETS)

        def expire_sources(runner, call):
            """Advance the clock after the first target receives its temperature."""
            # Remaining targets must not refresh an expired source group.
            runner.clock += timedelta(minutes=61)

        run.hook = expire_sources
        run.fire("periodic_sync")
        self.assertEqual(len(run.calls), 1)


class DeviceDispatchTests(unittest.TestCase):
    """Keep device differences in profiles and reject unsupported or ambiguous controls."""

    def test_selector_models_and_unknown_runtime_models(self):
        """Offer all four models on both integrations and reject unknown runtime models."""
        # MQTT uses stable model IDs without requiring descriptive model text.
        run = average_runner()
        filters = run.doc["blueprint"]["input"]["target_devices"]["selector"]["device"]["filter"]
        self.assertEqual({(item.get("model_id") or item.get("model")) for item in filters}, set(MODELS))
        self.assertEqual([item["integration"] for item in filters if (item.get("model_id") or item.get("model")) == "TRV-ZBL"], ["zha", "mqtt"])
        self.assertTrue(all("model" not in item for item in filters if item["integration"] == "mqtt"))
        for model, integration in (("OTHER", "zha"), ("OTHER", "mqtt")):
            run = average_runner(model, integration)
            run.fire("periodic_sync")
            self.assertEqual(run.calls, [])

    def test_mqtt_model_description_does_not_control_selection_or_dispatch(self):
        """Stable MQTT model IDs identify devices even when their descriptive text changes."""
        # Manufacturer and integration still gate dispatch; descriptive model text is optional.
        for model in MODELS:
            for description in ("任意显示名称", "Renamed model description", None):
                run = average_runner(model, "mqtt")
                run.devices["t0"]["model"] = description
                run.fire("periodic_sync")
                self.assertEqual(len(run.calls), 1)
                self.assertEqual(run.calls[0]["data"], {"value": 22})

    def test_profile_extension_reuses_the_existing_pipeline(self):
        """A future number-writing valve can use the shared dispatcher with a new profile."""
        # Deliberately inject only a profile and matching device metadata, not new actions.
        run = average_runner("FUTURE-TRV", "mqtt")
        run.doc["variables"]["device_profiles"]["FUTURE-TRV"] = deepcopy(
            run.doc["variables"]["device_profiles"]["TRV-ZBT"])
        run.fire("periodic_sync")
        self.assertEqual(run.calls[0]["data"], {"value": 22})

    def test_number_writes_use_the_destination_temperature_unit(self):
        """HA number services consume displayed units, even though the shared mean is Celsius."""
        # A Fahrenheit destination must receive 71.6 for a 22 Celsius average.
        for model, integration in TARGETS:
            if (model, integration) in ATTRIBUTE_TARGETS:
                continue
            for unit, expected in (("°F", 71.6), ("K", 295.1), ("°C", 22)):
                with self.subTest(model=model, integration=integration, unit=unit):
                    run = average_runner(model, integration)
                    destination = run.entity_map["t0"][1]
                    run.set_state(destination, "20", unit)
                    run.fire("periodic_sync")
                    self.assertEqual(run.calls[0]["data"], {"value": expected})

    def test_disabled_modes_and_wrong_identity_skip_only_that_target(self):
        """A disabled or incorrectly identified device cannot block healthy peers."""
        # All supported models have distinct, explicitly accepted external-mode states.
        for model, integration in TARGETS:
            run = average_runner(targets=[(model, integration), ("TRVZB", "zha")])
            mode = run.entity_map["t0"][0]
            run.set_state(mode, "internal_sensor" if (model, integration) in ATTRIBUTE_TARGETS
                          else "off" if integration == "zha" else "local_temperature", device_class="enum")
            run.fire("periodic_sync")
            self.assertEqual(len(run.calls), 1)
            self.assertEqual(run.calls[0]["target"]["entity_id"], "number.t1_external_temperature_sensor_value")
        for field, value in (("manufacturer", "OTHER"), ("model_id", "OTHER"), ("model_id", None),
                             ("identifiers", [("mqtt", "00:00"), ("zha", "00:00")])):
            run = average_runner("TRVZB", "mqtt")
            run.devices["t0"][field] = value
            run.fire("periodic_sync")
            self.assertEqual(run.calls, [])

    def test_failed_writes_do_not_block_other_models(self):
        """Both direct ZHA attribute failures and number failures are isolated per target."""
        # A failed TP MQTT write must not enable its stale cached value.
        for model, integration in TARGETS:
            run = average_runner(targets=[(model, integration), ("TRVZB", "zha")])
            key = ATTRIBUTE_TARGETS[(model, integration)] if (model, integration) in ATTRIBUTE_TARGETS else run.entity_map["t0"][1]
            run.fail.add(key)
            run.fire("periodic_sync")
            self.assertEqual(len(run.errors), 1)
            self.assertEqual(run.calls[-1]["target"]["entity_id"], "number.t1_external_temperature_sensor_value")
            self.assertNotIn("select.select_option", [call["action"] for call in run.calls])

    def test_missing_and_ambiguous_controls_fail_closed(self):
        """Refuse duplicate matches rather than choosing an arbitrary target control."""
        # Missing controls on this device cannot be replaced by a similarly named foreign control.
        for model, integration in TARGETS:
            for ambiguous in (False, True):
                run = average_runner(model, integration)
                entity = run.entity_map["t0"][0]
                if ambiguous:
                    duplicate = entity + "_2"
                    snapshot = run.states[entity]
                    run.entity_map["t0"].append(duplicate)
                    run.set_state(duplicate, snapshot["state"], **snapshot["attributes"])
                else:
                    run.entity_map["t0"].remove(entity)
                run.fire("periodic_sync")
                self.assertEqual(run.calls, [])

    def test_renamed_or_ambiguous_number_contracts_do_not_write_arbitrary_controls(self):
        """Name-based number contracts fail closed when absent or ambiguous on the target."""
        # TP's raw ZHA path is independent of number entities; its enum naming is tested separately.
        for model, integration in TARGETS:
            if (model, integration) in ATTRIBUTE_TARGETS:
                continue
            for ambiguous in (False, True):
                run = average_runner(model, integration)
                original = run.entity_map["t0"][1]
                renamed = original + "_2" if ambiguous else "number.wai_bu_wen_du"
                snapshot = run.states[original]
                if not ambiguous:
                    run.entity_map["t0"].remove(original)
                run.entity_map["t0"].append(renamed)
                run.set_state(renamed, snapshot["state"], **snapshot["attributes"])
                run.fire("periodic_sync")
                self.assertEqual(run.calls, [])

    def test_numbered_controls_and_event_filters(self):
        """HA conflict suffixes must not hide any supported model or integration."""
        # Numbered cases check suffix handling, not localization of name-based contracts.
        for model, integration in TARGETS:
            def make_runner():
                """Build a fresh single-device fixture for the selected profile."""
                # Bind loop values before running the naming matrix synchronously.
                return average_runner(model, integration)

            def exercise(run, entity_ids):
                """Send an average, then exercise a real target mode transition."""
                # Write echoes and unrelated state changes must not fan out again.
                run.fire("periodic_sync")
                original = run.entity_map["t0"][0]
                mode = entity_ids.get(original, original)
                enabled = run.states[mode]
                old = run.set_state(mode, "internal_sensor" if mode.startswith("sensor.") else "off",
                                    **enabled["attributes"])
                new = run.set_state(mode, enabled["state"], **enabled["attributes"])
                run.dispatch_state(mode, old, new)
                run.dispatch_state("sensor.unrelated", None, {"state": "on"})

            action = "zha.set_zigbee_cluster_attribute" if (model, integration) in ATTRIBUTE_TARGETS else "number.set_value"
            variants = NUMBERED_ENTITY_IDS if (model, integration) not in ATTRIBUTE_TARGETS else (
                *NUMBERED_ENTITY_IDS, "zh_pinyin", "de", "fr", "renamed")
            assert_entity_id_compatibility(self, make_runner, exercise, "t0",
                                           expected_actions=[action, action], variants=variants)

    def test_mode_and_destination_recovery_only_refresh_the_affected_device(self):
        """A target event cannot resend an unchanged average to all other models."""
        # Subsequent temperature write echoes are not fresh destination-recovery events.
        run = average_runner(targets=TARGETS)
        value = "number.t3_external_temperature_input"
        old = run.set_state(value, "unavailable", "°C")
        new = run.set_state(value, "20", "°C")
        run.dispatch_state(value, old, new)
        self.assertEqual(len(run.calls), 1)
        self.assertEqual(run.calls[0]["target"]["entity_id"], value)
        run.calls.clear()
        echo = run.set_state(value, "22", "°C")
        run.dispatch_state(value, new, echo)
        self.assertEqual(run.calls, [])


class TrvZblZhaTests(unittest.TestCase):
    """Follow PR #5740's single-input virtual-attribute contract for ZHA TRV-ZBL."""

    def test_ha_average_writes_only_the_single_remote_temperature_input(self):
        """Send one Celsius x100 mean through FF02, leaving T01 encoding to the quirk."""
        # PR head 58f2b921 maps FF02 to 601E:T01; FF11-FF15 instead represent separate T03 sources.
        run = average_runner("TRV-ZBL", "zha")
        run.fire("periodic_sync")
        self.assertEqual(run.calls, [{"action": "zha.set_zigbee_cluster_attribute", "data": {
            "ieee": "00:00", "endpoint_id": 1, "cluster_id": 0xFC11,
            "cluster_type": "in", "attribute": 0xFF02, "value": 2200}}])
        self.assertEqual(run.doc["blueprint"]["homeassistant"]["min_version"], "2025.10.0")

    def test_signed_temperatures_and_quirk_boundaries(self):
        """Keep signed hundredths and accept the quirk's inclusive -30 to 100 Celsius range."""
        # No unsigned frame construction or multi-source sentinel belongs in this blueprint.
        for value, expected in (("-30", -3000), ("-1.25", -125), ("0", 0), ("100", 10000)):
            with self.subTest(value=value):
                run = average_runner("TRV-ZBL", "zha")
                run.inputs["source_entities"] = ["sensor.source"]
                run.set_state("sensor.source", value, "°C")
                run.fire("periodic_sync")
                self.assertEqual(run.calls[0]["data"]["value"], expected)

    def test_out_of_range_zbl_mean_is_skipped_without_blocking_other_targets(self):
        """Reject samples the virtual quirk encoder would raise on before invoking its service."""
        # Other profiles can have different valid ranges and must still be dispatched.
        for value in ("-30.01", "100.01"):
            run = average_runner(targets=[("TRV-ZBL", "zha"), ("TRVZB", "zha")])
            run.inputs["source_entities"] = ["sensor.source"]
            run.set_state("sensor.source", value, "°C")
            run.fire("periodic_sync")
            self.assertEqual(len(run.calls), 1)
            self.assertEqual(run.calls[0]["target"]["entity_id"], "number.t1_external_temperature_sensor_value")

    def test_internal_mode_and_expired_sources_never_enable_or_unbind_zbl(self):
        """Leave external-source selection under user control and stop sending stale means."""
        # An inactive input is cached locally by the quirk, so the blueprint must gate it first.
        run = average_runner("TRV-ZBL", "zha")
        run.set_state("sensor.t0_temperature_source_mode", "internal_sensor", device_class="enum")
        run.fire("periodic_sync")
        self.assertEqual(run.calls, [])
        old = run.states["sensor.t0_temperature_source_mode"]
        new = run.set_state("sensor.t0_temperature_source_mode", "external_sensor", device_class="enum")
        run.dispatch_state("sensor.t0_temperature_source_mode", old, new)
        self.assertEqual(run.calls[0]["data"]["attribute"], 0xFF02)
        run.calls.clear()
        run.clock += timedelta(minutes=61)
        run.fire("periodic_sync")
        self.assertEqual(run.calls, [])


class BoundSourceDispatchTests(unittest.TestCase):
    """Push bound MQTT sources directly and leave remote-mode recovery to the firmware."""

    def test_all_bound_modes_send_once_without_writing_the_mode(self):
        """Both online and offline bindings receive fresh averages without selector changes."""
        # Preserve each converter's accepted binding states, including legacy TRVZB modes.
        for model in MODELS:
            run = average_runner(model, "mqtt")
            for mode in run.doc["variables"]["device_profiles"][model]["mqtt_modes"]:
                with self.subTest(model=model, mode=mode):
                    run.calls.clear()
                    run.set_state("select.t0_temperature_sensor_select", mode)
                    run.fire("periodic_sync")
                    self.assertEqual([call["action"] for call in run.calls], ["number.set_value"])
                    self.assertEqual(run.calls[0]["data"], {"value": 22})
                    self.assertEqual(run.states("select.t0_temperature_sensor_select"), mode)

    def test_unbound_or_unknown_modes_are_never_enabled(self):
        """An unbound device remains under user control and receives no source writes."""
        # Unknown mode is not proof of an existing binding, so it must also fail closed.
        for model in MODELS:
            for mode in ("local_temperature", "internal", "unknown", "unavailable"):
                with self.subTest(model=model, mode=mode):
                    run = average_runner(model, "mqtt")
                    run.set_state("select.t0_temperature_sensor_select", mode)
                    run.fire("periodic_sync")
                    self.assertEqual(run.calls, [])

    def test_offline_unknown_cached_value_does_not_block_mixed_target_dispatch(self):
        """Send without waiting for an old converter value, then immediately process the next target."""
        # The firmware can restore the remote source after receiving the new temperature.
        for model in MODELS:
            for cached in ("unknown", "unavailable", "20"):
                with self.subTest(model=model, cached=cached):
                    run = average_runner(targets=[(model, "mqtt"), ("TRVZB", "zha")])
                    run.set_state("select.t0_temperature_sensor_select", "remote_source_offline")
                    run.set_state("number.t0_external_temperature_input", cached, "°C")
                    run.fire("periodic_sync")
                    self.assertEqual([call["action"] for call in run.calls], ["number.set_value"] * 2)
                    self.assertEqual([call["data"]["value"] for call in run.calls], [22, 22])
                    self.assertEqual(run.states("number.t0_external_temperature_input"), cached)


class SourceNotificationTests(unittest.TestCase):
    """Verify one optional summary per automation, independent of target count or mode."""

    def test_offline_invalid_and_expired_summary_recovers_and_clears(self):
        """Report distinct source issues even when every target has no usable reading."""
        # Sources recover independently; repeated checks update the same notification ID.
        run = average_runner(targets=TARGETS)
        run.inputs.update(notify_source_offline=True, source_entities=["sensor.source", "sensor.bad", "sensor.second"])
        run.set_state("sensor.bad", "bad", "°C")
        run.clock += timedelta(minutes=61)
        run.set_state("sensor.source", "unavailable", "°C", friendly_name="Bedroom")
        run.fire("periodic_sync")
        self.assertEqual(len(run.calls), 1)
        alert = run.calls[0]
        self.assertEqual(alert["action"], "persistent_notification.create")
        self.assertIn("Bedroom — Unavailable.", alert["data"]["message"])
        self.assertIn("sensor.bad — Invalid temperature.", alert["data"]["message"])
        self.assertIn("sensor.second — No temperature change for 60 minutes.", alert["data"]["message"])
        run.calls.clear()
        run.set_state("sensor.source", "21", "°C")
        run.fire("source_changed")
        self.assertNotIn("Bedroom", run.calls[0]["data"]["message"])
        self.assertEqual(run.calls[0]["data"]["notification_id"], alert["data"]["notification_id"])
        run.calls.clear()
        run.inputs["source_entities"] = ["sensor.source"]
        run.fire("automation_reloaded")
        self.assertEqual(run.calls[0]["action"], "persistent_notification.dismiss")
        self.assertEqual(len(run.calls), len(TARGETS) + 1)

    def test_disabled_notifications_clear_on_reload_even_in_local_mode(self):
        """Saving the disabled option clears the existing summary without temperature writes."""
        # Notification cleanup is independent of device-specific mode gating.
        run = average_runner("TP-WGZBA", "zha")
        run.inputs["notify_source_offline"] = True
        run.set_state("sensor.t0_temperature_source_mode", "internal_sensor", device_class="enum")
        run.set_state("sensor.source", "unavailable", "°C")
        run.fire("periodic_sync")
        self.assertEqual(len(run.calls), 1)
        run.calls.clear()
        run.inputs["notify_source_offline"] = False
        run.fire("automation_reloaded")
        self.assertEqual([call["action"] for call in run.calls], ["persistent_notification.dismiss"])

    def test_notification_failure_does_not_block_any_temperature_target(self):
        """Failing the optional summary cannot prevent normal mixed-model synchronization."""
        # Notification services have no device entity target in this runner.
        run = average_runner(targets=TARGETS)
        run.inputs["notify_source_offline"] = True
        run.fail.add(None)
        run.fire("periodic_sync")
        self.assertEqual(len(run.errors), 1)
        self.assertEqual(len(run.calls), len(TARGETS) + 1)
