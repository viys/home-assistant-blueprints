"""Small offline YAML executor shared by behavior tests, not a Home Assistant runtime."""

import ast
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import re

from jinja2 import Environment
import yaml

from tools.blueprint_coverage import RECORDER


class InputLoader(yaml.SafeLoader):
    """Resolve blueprint input tags without changing the global YAML loader."""


def input_value(loader, node):
    """Keep input names available for substitution in each automation instance."""
    # Inputs resolve before Home Assistant validates the automation.
    return ("input", loader.construct_scalar(node))


class States(dict):
    """Expose the subset of HA's state interface used by these blueprints."""

    def __getitem__(self, entity):
        """Return None for missing entities, as the HA template interface does."""
        # Optional humidity must also work without a matching entity.
        return self.get(entity)

    def __call__(self, entity):
        """Read an entity's state string."""
        # Missing sources have no numeric reading.
        return self[entity]["state"] if self[entity] else "unknown"


class HandledServiceError(Exception):
    """Stand in for a runtime HomeAssistantError allowed by continue_on_error."""


InputLoader.add_constructor("!input", input_value)


def is_number(value):
    """Match numeric source validation, including rejection of NaN and infinity."""
    # Failed conversions represent unavailable or invalid readings.
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def ha_bool(value, default=False):
    """Interpret common HA Boolean values without treating the string false as true."""
    # Version/full-sync templates can produce lowercase Boolean strings.
    if isinstance(value, str):
        if value.lower() in ('true', 'yes', 'on', '1'):
            return True
        if value.lower() in ('false', 'no', 'off', '0'):
            return False
        return default
    return bool(value)


class BlueprintRunner:
    """Execute actual blueprint documents with explicit state/device fixtures."""

    scope_factory = dict

    def __init__(self, file, inputs):
        """Load and bind a blueprint without counting loading as execution."""
        # The executor records source locations only at actual execution hooks.
        self.file = Path(file)
        self.doc = yaml.load(self.file.read_text(encoding='utf-8'), Loader=InputLoader)
        RECORDER.bind(self.file, self.doc)
        self.inputs = inputs
        self.env = Environment()
        self.env.filters['bool'] = ha_bool
        self.env.tests['match'] = lambda value, pattern: re.match(pattern, value)
        self.states = States()
        self.devices = {}
        self.entity_map = {}
        self.clock = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.calls = []
        self.errors = []
        self.hook = None
        self.fail = set()
        self.failure_type = HandledServiceError
        self.last_scope = None

    def set_state(self, entity, value, unit=None, **attributes):
        """Create a fresh state snapshot with deterministic update versions."""
        # Keep snapshots immutable from the perspective of an earlier trigger.
        self.clock += timedelta(microseconds=1)
        if unit is not None:
            attributes['unit_of_measurement'] = unit
        self.states[entity] = dict(state=str(value), attributes=attributes, last_updated=self.clock)
        return self.states[entity]

    def fire(self, trigger_id, entity=None, old_state=None, new_state=None):
        """Run a declared trigger through the real global conditions and actions."""
        # This models an admitted event, not HA scheduling or integration transport.
        declaration = next(item for item in self.doc['triggers'] if item['id'] == trigger_id)
        trigger = {'id': trigger_id}
        if declaration['trigger'] == 'event':
            trigger['event'] = {'data': dict(entity_id=entity, old_state=old_state, new_state=new_state)}
        scope = dict(states=self.states, trigger=trigger, is_number=is_number,
                     is_state=lambda entity, value: self.states(entity) == value,
                     state_attr=lambda entity, key: self.states[entity]['attributes'].get(key) if self.states[entity] else None,
                     device_entities=lambda device: self.entity_map.get(device, []),
                     device_attr=lambda device, key: self.devices.get(device, {}).get(key))
        self.variables(self.doc['variables'], scope)
        self.last_scope = scope
        if self.condition(self.doc.get('conditions', []), scope):
            self.execute(self.doc['actions'], self.scope_factory(scope))

    def dispatch_state(self, entity, old_state, new_state):
        """Match the state/event trigger forms used by the tested blueprints."""
        # The structural coverage metric excludes dispatch; assertions still verify it.
        for declaration in self.doc['triggers']:
            if declaration['trigger'] == 'event' and declaration.get('event_type') == 'state_changed':
                filters = self.render(declaration.get('event_data', {}), {})
                event = dict(entity_id=entity, old_state=old_state, new_state=new_state)
                if all(event.get(key) == value for key, value in filters.items()):
                    self.fire(declaration['id'], entity, old_state, new_state)
            elif declaration['trigger'] == 'state':
                selected = self.render(declaration['entity_id'], {})
                selected = selected if isinstance(selected, list) else [selected]
                # HA suppresses attribute-only events when state-value filters exist.
                filtered = any(key in declaration for key in ('from', 'to', 'not_from', 'not_to'))
                if (filtered and old_state is not None and new_state is not None
                        and old_state['state'] == new_state['state']):
                    continue
                if (entity in selected and new_state is not None
                        and new_state['state'] not in declaration.get('not_to', [])):
                    self.fire(declaration['id'], entity, old_state, new_state)

    def render(self, value, scope):
        """Resolve inputs and templates recursively, preserving native values."""
        # HA renders action data only when that action executes.
        if isinstance(value, tuple) and value[0] == "input":
            return self.inputs[value[1]]
        if isinstance(value, str) and ("{{" in value or "{%" in value):
            rendered = self.env.from_string(value).render(**scope)
            if isinstance(rendered, str):
                rendered = rendered.strip()
                try:
                    parsed = ast.literal_eval(rendered)
                    # Follow HA 2025.3's simple-number result parsing; preserve strings,
                    # complex/scientific/hex values instead of native-Jinja coercion.
                    # See homeassistant/helpers/template.py:_cached_parse_result in HA.
                    if (isinstance(parsed, (str, complex))
                            or (type(parsed) in (int, float)
                                and not re.fullmatch(r"[+-]?(?!0\d)\d*(?:\.\d*)?", rendered))):
                        return rendered
                    return parsed
                except (ValueError, SyntaxError):
                    return rendered
            return rendered
        if isinstance(value, dict):
            return {key: self.render(item, scope) for key, item in value.items()}
        if isinstance(value, list):
            return [self.render(item, scope) for item in value]
        return value

    def variables(self, values, scope):
        """Render variable mappings in order, including dependencies on prior keys."""
        # Automation-level mappings render at trigger time, before admission to a queue.
        for key, value in values.items():
            scope[key] = self.render(value, scope)

    def condition(self, conditions, scope):
        """Evaluate the template conditions used in the blueprint."""
        # Lists of conditions use HA's default AND behavior.
        for item in conditions:
            rendered = self.render(item["value_template"], scope)
            outcome = rendered is True or (isinstance(rendered, str) and rendered.lower() == "true")
            RECORDER.hit(item, "condition", "true" if outcome else "false")
            if not outcome:
                return False
        return True

    def child_scope(self, scope):
        """Allow optional checks using HA's actual ScriptRunVariables implementation."""
        # Normal focused tests use a dict; source-level checks can inject HA scopes.
        return scope.enter_scope() if hasattr(scope, "enter_scope") else scope

    def execute(self, actions, scope):
        """Run actual YAML actions and model service exceptions at their call sites."""
        # Error handling belongs to the action carrying continue_on_error.
        for action in actions:
            RECORDER.hit(action, "action", "reached")
            try:
                if "variables" in action:
                    self.variables(action["variables"], scope)
                elif "condition" in action:
                    if not self.condition([action], scope):
                        return
                elif "choose" in action:
                    for choice_index, choice in enumerate(action["choose"]):
                        if self.condition(choice["conditions"], scope):
                            RECORDER.hit(action, "choose", choice_index)
                            self.execute(choice["sequence"], self.child_scope(scope))
                            break
                    else:
                        RECORDER.hit(action, "choose", "none")
                        self.execute(action.get("default", []), self.child_scope(scope))
                elif "sequence" in action:
                    self.execute(action["sequence"], self.child_scope(scope))
                elif "repeat" in action:
                    repeat = action["repeat"]
                    if "for_each" in repeat:
                        previous = scope.get("repeat")
                        items = self.render(repeat["for_each"], scope)
                        for index, item in enumerate(items, 1):
                            scope["repeat"] = {"index": index, "first": index == 1, "item": item}
                            self.execute(repeat["sequence"], self.child_scope(scope))
                        scope["repeat"] = previous
                    else:
                        for index in range(1, 101):
                            scope["repeat"] = {"index": index, "first": index == 1}
                            self.execute(repeat["sequence"], self.child_scope(scope))
                            if self.condition(repeat["until"], scope):
                                break
                        else:
                            raise AssertionError("Worker did not settle after source updates stopped")
                elif "action" in action:
                    call = self.render(action, scope)
                    self.calls.append(call)
                    if self.hook:
                        self.hook(self, call)
                    key = call.get("data", {}).get("attribute", call.get("target", {}).get("entity_id"))
                    if key in self.fail:
                        raise self.failure_type(f"Injected service error: {key}")
                else:
                    raise AssertionError(f"Unsupported test action: {action}")
            except HandledServiceError as error:
                if not action.get("continue_on_error", False):
                    raise
                self.errors.append(str(error))
