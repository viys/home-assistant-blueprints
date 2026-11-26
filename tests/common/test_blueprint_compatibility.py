"""Validate compatibility metadata for published blueprint guides."""
import json
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/src"
STATUSES = {"supported", "limited", "experimental", "not_supported"}


class BlueprintCompatibilityTests(unittest.TestCase):
    def test_published_guides_have_valid_compatibility(self):
        data = json.loads((DOCS / "data/blueprint-compatibility.json").read_text(encoding="utf-8"))
        guides = set()
        for path in (DOCS / "content/docs/blueprints").rglob("*.md"):
            metadata = yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])
            if "blueprint" in metadata:
                guides.add(metadata["blueprint"])
        self.assertEqual(set(data), guides)
        for stem, entry in data.items():
            with self.subTest(blueprint=stem):
                self.assertTrue((ROOT / "automation/sonoff" / f"{stem}.yaml").is_file())
                self.assertIsInstance(entry["columns"], list)
                self.assertTrue(entry["columns"])
                self.assertTrue(all(isinstance(c, str) and c.strip() for c in entry["columns"]))
                self.assertEqual(len(set(entry["columns"])), len(entry["columns"]))
                for platform in ("zha", "zigbee2mqtt"):
                    self.assertIsInstance(entry[platform], list)
                    self.assertEqual(len(entry[platform]), len(entry["columns"]))
                    self.assertTrue(set(entry[platform]) <= STATUSES)
                if "note" in entry:
                    self.assertIsInstance(entry["note"], str)
                    self.assertTrue(entry["note"].strip())
