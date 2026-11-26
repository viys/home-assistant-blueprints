"""Check the manual's source mapping and publishing boundary without a web browser."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import yaml

from tools import check_site as site_checker
from tools.check_site import check_site


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


class DocumentationTests(unittest.TestCase):
    """Check published guides and assets without requiring Pages coverage of every blueprint."""

    def test_published_guides_have_matching_svg_and_metadata(self):
        """Validate existing Pages entries independently of blueprint-only changes."""
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
        self.assertEqual({path.stem for path in (DOCS / "public/diagrams").glob("*.svg")}, set(guides))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("https://viys.github.io/home-assistant-blueprints/", readme)
        ns = {"svg": "http://www.w3.org/2000/svg"}
        for stem, (path, metadata, text) in guides.items():
            with self.subTest(guide=stem):
                self.assertTrue(metadata.get("title"))
                self.assertEqual(path.stem, stem)
                svg = ET.parse(DOCS / "public/diagrams" / f"{stem}.svg").getroot()
                self.assertIn("viewBox", svg.attrib)
                self.assertIsNotNone(svg.find("svg:title", ns))
                self.assertIsNotNone(svg.find("svg:desc", ns))
                self.assertFalse(svg.findall(".//svg:script", ns))
                self.assertIn(f"{stem}.svg", text)

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

    def test_import_target_must_exist_but_unpublished_blueprints_are_allowed(self):
        """Reject a guide with a missing YAML while allowing YAML without a guide."""
        # Exercise the CLI against an isolated repository and a matching rendered import button.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            guides = root / "docs/src/content/docs/blueprints"
            guides.mkdir(parents=True)
            (guides / "example.md").write_text(
                "---\nblueprint: example\ntitle: Example\n---\n", encoding="utf-8")
            site = root / "dist"
            (site / "pagefind").mkdir(parents=True)
            (site / "pagefind/pagefind.js").write_text("", encoding="utf-8")
            (site / "index.html").write_text(
                '<a href="https://my.home-assistant.io/redirect/blueprint_import/?'
                'blueprint_url=https%3A%2F%2Fgithub.com%2Fviys%2Fhome-assistant-blueprints'
                '%2Fblob%2Fmaster%2Fautomation%2Fsonoff%2Fexample.yaml">Import</a>', encoding="utf-8")
            with patch.object(site_checker, "__file__", str(root / "tools/check_site.py")), \
                    patch("sys.argv", ["check_site.py", str(site)]):
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(site_checker.main(), 1)
                self.assertIn("automation/sonoff/example.yaml", output.getvalue())
                self.assertIn("missing", output.getvalue())

                blueprints = root / "automation/sonoff"
                blueprints.mkdir(parents=True)
                (blueprints / "example.yaml").write_text("blueprint: {}\n", encoding="utf-8")
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(site_checker.main(), 0)

                (blueprints / "unpublished.yaml").write_text("blueprint: {}\n", encoding="utf-8")
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(site_checker.main(), 0)

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
