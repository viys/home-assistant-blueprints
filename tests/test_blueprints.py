"""Offline structural checks for every published automation blueprint."""

from dataclasses import dataclass
from pathlib import Path
import re
import unittest
from urllib.parse import parse_qs, unquote, urlparse

from jinja2 import Environment
import yaml


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class InputReference:
    """Keep !input references distinct from ordinary YAML strings."""

    name: str


class BlueprintLoader(yaml.SafeLoader):
    """Load HA input tags and reject silently overwritten YAML mapping keys."""

    def construct_mapping(self, node, deep=False):
        """Reject duplicate keys with a useful YAML source location."""
        # SafeLoader would otherwise keep only the last occurrence of a key.
        keys = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                raise yaml.constructor.ConstructorError(
                    "while reading a blueprint", node.start_mark,
                    f"duplicate key: {key}", key_node.start_mark,
                )
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def input_reference(loader, node):
    """Preserve each input name for declaration checks."""
    # Register on this loader only; unrelated YAML readers stay unchanged.
    return InputReference(loader.construct_scalar(node))


BlueprintLoader.add_constructor("!input", input_reference)


def walk(value):
    """Visit nested YAML values for input-reference and template checks."""
    # Include containers so callers can inspect values without reparsing YAML.
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


class BlueprintTests(unittest.TestCase):
    """Catch malformed YAML, broken inputs/templates, and stale catalogue paths."""

    @classmethod
    def setUpClass(cls):
        """Load every automation blueprint, failing if discovery finds none."""
        # Future vendor directories are automatically included.
        paths = sorted((ROOT / "automation").rglob("*.yaml"))
        if not paths:
            raise AssertionError("No automation blueprints discovered")
        cls.documents = {
            path: yaml.load(path.read_text(encoding="utf-8"), Loader=BlueprintLoader)
            for path in paths
        }

    def test_blueprint_structure(self):
        """Require usable automation metadata and nonempty trigger/action lists."""
        # This checks repository contracts, not the complete Home Assistant schema.
        for path, document in self.documents.items():
            with self.subTest(blueprint=path.name):
                self.assertIsInstance(document, dict)
                blueprint = document["blueprint"]
                for field in ("name", "author", "description"):
                    self.assertIsInstance(blueprint[field], str)
                    self.assertTrue(blueprint[field].strip())
                self.assertEqual(blueprint["domain"], "automation")
                self.assertIsInstance(blueprint["input"], dict)
                for field in ("triggers", "actions"):
                    self.assertIsInstance(document[field], list)
                    self.assertTrue(document[field])
                self.assertIn(document.get("mode", "single"),
                              ("single", "restart", "queued", "parallel"))
                minimum = blueprint.get("homeassistant", {}).get("min_version")
                if minimum is not None:
                    self.assertRegex(str(minimum), r"^\d{4}\.\d{1,2}\.\d+$")

    def test_input_references_are_declared(self):
        """Catch misspelled or removed inputs used anywhere in a blueprint."""
        # Input section groups may contain nested input declarations.
        for path, document in self.documents.items():
            declared = set(document["blueprint"]["input"])
            for item in walk(document["blueprint"]["input"]):
                if isinstance(item, dict) and isinstance(item.get("input"), dict):
                    declared.update(item["input"])
            for item in walk(document):
                if isinstance(item, InputReference):
                    with self.subTest(blueprint=path.name, input=item.name):
                        self.assertIn(item.name, declared)

    def test_template_syntax(self):
        """Parse every Jinja template without pretending to provide HA runtime state."""
        # Parsing catches syntax errors while allowing HA-specific functions/filters.
        environment = Environment()
        for path, document in self.documents.items():
            for value in walk(document):
                if isinstance(value, str) and any(tag in value for tag in ("{{", "{%", "{#")):
                    with self.subTest(blueprint=path.name, template=value[:100]):
                        environment.parse(value)

    def test_readme_catalogue_matches_files(self):
        """Verify master import badges and both branches' raw links."""
        # Compare decoded paths, including each URL-encoded blueprint_url parameter.
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        expected = {path.relative_to(ROOT).as_posix() for path in self.documents}
        imports = {branch: set() for branch in ("master", "dev")}
        raw_links = {branch: set() for branch in ("master", "dev")}
        for url in re.findall(r'https://[^\s"<>\)]+', text):
            parsed = urlparse(url)
            if parsed.netloc == "my.home-assistant.io":
                for source in parse_qs(parsed.query).get("blueprint_url", []):
                    source_url = urlparse(source)
                    self.assertEqual(source_url.netloc, "github.com")
                    for branch in imports:
                        prefix = f"/viys/home-assistant-blueprints/blob/{branch}/"
                        if source_url.path.startswith(prefix):
                            imports[branch].add(unquote(source_url.path[len(prefix):]))
                            break
                    else:
                        self.fail(f"Unexpected blueprint import URL: {source}")
            elif parsed.netloc == "raw.githubusercontent.com":
                for branch in raw_links:
                    prefix = f"/viys/home-assistant-blueprints/{branch}/"
                    if parsed.path.startswith(prefix):
                        raw_links[branch].add(unquote(parsed.path[len(prefix):]))
                        break
                else:
                    self.fail(f"Unexpected raw YAML URL: {url}")
        for branch in imports:
            with self.subTest(branch=branch):
                self.assertEqual(imports[branch], expected if branch == "master" else set())
                self.assertEqual(raw_links[branch], expected)

    def test_duplicate_yaml_keys_are_rejected(self):
        """Ensure malformed mappings cannot produce a misleading passing check."""
        # A duplicate top-level key must fail instead of hiding earlier definitions.
        with self.assertRaises(yaml.constructor.ConstructorError):
            yaml.load("mode: queued\nmode: parallel\n", Loader=BlueprintLoader)


if __name__ == "__main__":
    unittest.main()
