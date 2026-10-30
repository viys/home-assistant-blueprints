"""Measure YAML control-flow execution, not Python or real Home Assistant coverage."""

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Opportunity:
    """One statically enumerated action or branch outcome in a YAML block."""

    file: str
    path: str
    kind: str
    outcome: str
    line: int
    end_line: int
    hits: int = 0


class Recorder:
    """Map executed YAML objects back to a complete static coverage inventory."""

    def __init__(self, root=ROOT):
        """Inventory every blueprint so untested files remain in the denominator."""
        # Runtime bindings are separate from source identities and never create points.
        self.root = Path(root)
        self.points = {}
        self.bindings = {}
        for file in sorted((self.root / "automation").rglob("*.yaml")):
            relative = file.relative_to(self.root).as_posix()
            node = yaml.compose(file.read_text(encoding="utf-8"))
            self._inventory(relative, node)

    def _add(self, file, path, kind, outcome, node):
        """Add a source-located opportunity without counting it as executed."""
        # Use the whole block span when determining whether a diff changed this point.
        key = (file, path, kind, outcome)
        end = node.end_mark
        line_start = end.buffer.rfind("\n", 0, end.pointer) + 1
        # A block may end at the next sibling's indentation, not its content.
        has_content = bool(end.buffer[line_start:end.pointer].strip())
        self.points[key] = Opportunity(
            file, path, kind, outcome, node.start_mark.line + 1,
            max(node.start_mark.line + 1, end.line + has_content),
        )

    def _inventory(self, file, node):
        """Enumerate native action blocks, conditions, choices, and repeat predicates."""
        # Follow control-flow schema positions; service data keys are not actions.
        def mapping(value):
            """Read composed mappings without resolving HA-specific YAML tags."""
            # Composition preserves source ranges and does not execute constructors.
            return {key.value: child for key, child in value.value}

        def conditions(value, path):
            """Enumerate each condition's true and false outcomes."""
            # Short-circuited conditions stay uncovered until evaluated by a test.
            if isinstance(value, yaml.SequenceNode):
                for index, child in enumerate(value.value):
                    conditions(child, f"{path}/{index}")
            elif isinstance(value, yaml.MappingNode):
                fields = mapping(value)
                if "condition" in fields:
                    for outcome in ("true", "false"):
                        self._add(file, path, "condition", outcome, value)
                    if "conditions" in fields:
                        conditions(fields["conditions"], path + "/conditions")

        def actions(value, path):
            """Enumerate action nodes and recursively visit their nested control flow."""
            # Every action, including unimplemented simulator actions, starts uncovered.
            if not isinstance(value, yaml.SequenceNode):
                return
            for index, action in enumerate(value.value):
                current = f"{path}/{index}"
                self._add(file, current, "action", "reached", action)
                if not isinstance(action, yaml.MappingNode):
                    continue
                fields = mapping(action)
                conditions(action, current)
                for key in ("sequence", "default", "then", "else", "parallel"):
                    if key in fields:
                        actions(fields[key], f"{current}/{key}")
                if "if" in fields:
                    conditions(fields["if"], current + "/if")
                if "choose" in fields:
                    for choice_index, choice in enumerate(fields["choose"].value):
                        branch = mapping(choice)
                        self._add(file, current, "choose", str(choice_index), action)
                        conditions(branch["conditions"], f"{current}/choose/{choice_index}/conditions")
                        actions(branch["sequence"], f"{current}/choose/{choice_index}/sequence")
                    self._add(file, current, "choose", "none", action)
                if "repeat" in fields:
                    repeat = mapping(fields["repeat"])
                    actions(repeat["sequence"], current + "/repeat/sequence")
                    for key in ("until", "while"):
                        if key in repeat:
                            conditions(repeat[key], f"{current}/repeat/{key}")

        document = mapping(node)
        if "conditions" in document:
            conditions(document["conditions"], "conditions")
        actions(document["actions"], "actions")

    def bind(self, file, document):
        """Bind a simulator-loaded document to its file and YAML object paths."""
        # Loading/visiting objects alone never records coverage.
        relative = Path(file).resolve().relative_to(self.root.resolve()).as_posix()

        def visit(value, path):
            """Index live mapping identities for execution hooks."""
            # Retain the object too, preventing Python id reuse from misattributing hits.
            if isinstance(value, dict):
                self.bindings[id(value)] = (value, relative, path)
                for key, child in value.items():
                    visit(child, f"{path}/{key}" if path else key)
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    visit(child, f"{path}/{index}")

        visit(document, "")

    def hit(self, value, kind, outcome):
        """Record a runtime event only if that event exists in the static inventory."""
        # Fail loudly if an execution hook and the inventory disagree.
        _, file, path = self.bindings[id(value)]
        key = (file, path, kind, str(outcome))
        self.points[key].hits += 1

    def rows(self):
        """Return serializable source-level records in deterministic order."""
        # Reports include uncovered points and wholly untested blueprints.
        return [asdict(point) for _, point in sorted(self.points.items())]


RECORDER = Recorder()
