"""Check the manual's source mapping and publishing boundary without a web browser."""

from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import yaml

from tests.common.test_common import BlueprintLoader
from tools.check_site import check_site


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


class DocumentationTests(unittest.TestCase):
    """Keep guide names, inputs, illustrations, and catalogue links aligned."""

    def test_every_blueprint_has_one_matching_markdown_guide_and_svg(self):
        """Catch missing guides and stale blueprint names or input labels."""
        # Front matter is the mapping used by the site's shared import-button component.
        guides = {}
        for path in (DOCS / "src/content/docs/blueprints").rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            metadata = yaml.safe_load(text.split("---", 2)[1])
            if "blueprint" not in metadata:
                continue
            stem = metadata["blueprint"]
            self.assertNotIn(stem, guides)
            guides[stem] = (path, metadata, text)
        blueprints = list((ROOT / "automation/sonoff").glob("*.yaml"))
        self.assertEqual(set(guides), {path.stem for path in blueprints})
        self.assertEqual({path.stem for path in (DOCS / "public/diagrams").glob("*.svg")}, set(guides))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("https://viys.github.io/home-assistant-blueprints/", readme)
        ns = {"svg": "http://www.w3.org/2000/svg"}
        for blueprint in blueprints:
            with self.subTest(blueprint=blueprint.name):
                path, metadata, text = guides[blueprint.stem]
                data = yaml.load(blueprint.read_text(encoding="utf-8"), Loader=BlueprintLoader)["blueprint"]
                self.assertEqual(metadata["title"], data["name"])
                self.assertEqual(path.stem, blueprint.stem)
                minimum = data.get("homeassistant", {}).get("min_version")
                self.assertIsNotNone(minimum)
                self.assertIn(f"**{minimum} or later**", text)
                for value in data["input"].values():
                    self.assertIn(value["name"], text)
                self.assertIn(data["name"], readme)
                svg = ET.parse(DOCS / "public/diagrams" / f"{blueprint.stem}.svg").getroot()
                self.assertIn("viewBox", svg.attrib)
                self.assertIsNotNone(svg.find("svg:title", ns))
                self.assertIsNotNone(svg.find("svg:desc", ns))
                self.assertFalse(svg.findall(".//svg:script", ns))
                self.assertIn(f"{blueprint.stem}.svg", text)

    def test_both_branches_publish_but_prs_remain_read_only(self):
        """Build once through the reusable job and publish one shared branch site."""
        # BaseLoader preserves the workflow's on key instead of interpreting YAML 1.1 booleans.
        workflow = yaml.load((ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertIn("pull_request", workflow["on"])
        self.assertEqual(workflow["on"]["push"]["branches"], ["master", "dev"])
        deploy = workflow["jobs"]["deploy"]
        self.assertEqual(deploy["if"], "github.event_name != 'pull_request' && "
                         "(github.ref == 'refs/heads/master' || github.ref == 'refs/heads/dev')")
        self.assertEqual(workflow["jobs"]["build"]["uses"], "./.github/workflows/manual-build.yml")
        self.assertEqual(deploy["needs"], "build")
        self.assertEqual(deploy["permissions"], {"pages": "write", "id-token": "write"})

    def test_rendered_checker_handles_base_paths_fragments_and_missing_assets(self):
        """Exercise real URL resolution and failure reporting using a tiny artifact."""
        # External links are intentionally ignored; these checks must work offline.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "guide").mkdir()
            (root / "guide/index.html").write_text('<h1 id="setup">Setup</h1>', encoding="utf-8")
            (root / "diagram.svg").write_text('<svg/>', encoding="utf-8")
            index = root / "index.html"
            index.write_text('<a href="/manual/guide/#setup">Guide</a><img src="diagram.svg">', encoding="utf-8")
            self.assertEqual(check_site(root, "/manual"), [])
            index.write_text('<a href="/guide/">Wrong base</a><a href="../escape">Escape</a>'
                             '<a href="/manual/guide/#absent">Bad anchor</a><img src="missing.svg">'
                             '<a href="https://example.com/">External</a>', encoding="utf-8")
            errors = check_site(root, "/manual")
            self.assertEqual(len(errors), 4)
            for kind in ("outside base path", "escapes site", "missing anchor", "missing:"):
                self.assertTrue(any(kind in error for error in errors))


if __name__ == "__main__":
    unittest.main()
