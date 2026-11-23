"""Check the built manual's local links, anchors, images, and stable import targets."""

import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


class Page(HTMLParser):
    """Collect references and fragment destinations from rendered HTML."""

    def __init__(self, text):
        """Parse a page once for both incoming and outgoing link validation."""
        # HTMLParser decodes escaped ampersands in HTML attribute values.
        super().__init__(convert_charrefs=True)
        self.references = []
        self.anchors = set()
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        """Record navigation, scripts, styles, images, and fragment targets."""
        # Include legacy named anchors as well as ordinary element IDs.
        attrs = dict(attrs)
        if attrs.get("id"):
            self.anchors.add(attrs["id"])
        if tag == "a" and attrs.get("name"):
            self.anchors.add(attrs["name"])
        for key in ("href", "src"):
            if attrs.get(key):
                self.references.append(attrs[key])


def check_site(root, baseurl="/home-assistant-blueprints"):
    """Return broken references, including repository-subpath and anchor errors."""
    # Resolve every path against the artifact; never fetch external URLs.
    root = Path(root).resolve()
    baseurl = "/" + baseurl.strip("/") if baseurl.strip("/") else ""
    pages = {path: Page(path.read_text(encoding="utf-8")) for path in root.rglob("*.html")}
    if root / "index.html" not in pages:
        return ["Missing site index.html"]
    errors = []
    for source, page in pages.items():
        for reference in page.references:
            url = urlsplit(reference)
            if url.scheme or url.netloc:
                continue
            path = unquote(url.path)
            if path.startswith("/"):
                if baseurl and path != baseurl and not path.startswith(baseurl + "/"):
                    errors.append(f"{source.relative_to(root)}: outside base path: {reference}")
                    continue
                target = root / path[len(baseurl):].lstrip("/")
            else:
                target = source.parent / path if path else source
            target = target.resolve()
            if not target.is_relative_to(root):
                errors.append(f"{source.relative_to(root)}: escapes site: {reference}")
                continue
            if target.is_dir():
                target /= "index.html"
            if not target.is_file():
                errors.append(f"{source.relative_to(root)}: missing: {reference}")
            elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].anchors:
                errors.append(f"{source.relative_to(root)}: missing anchor: {reference}")
    return sorted(set(errors))


def main():
    """Validate the artifact and compare its import buttons with the actual YAML files."""
    # Check generated buttons as a set so stale, missing, or duplicate guides fail CI.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    parser.add_argument("--baseurl", default="/home-assistant-blueprints")
    args = parser.parse_args()
    errors = check_site(args.site, args.baseurl)
    imports = []
    for path in args.site.rglob("*.html"):
        page = Page(path.read_text(encoding="utf-8"))
        for reference in page.references:
            url = urlsplit(reference)
            if url.netloc == "my.home-assistant.io":
                imports.extend(parse_qs(url.query).get("blueprint_url", []))
    repository = Path(__file__).resolve().parents[1]
    expected = {f"https://github.com/viys/home-assistant-blueprints/blob/master/automation/sonoff/{p.name}"
                for p in (repository / "automation/sonoff").glob("*.yaml")}
    if set(imports) != expected or len(imports) != len(expected):
        errors.append("Built import buttons must match every current blueprint exactly once (master only).")
    if not (args.site / "pagefind/pagefind.js").is_file():
        errors.append("Missing built search index runtime: pagefind/pagefind.js")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"Links, anchors, assets, search runtime, and {len(imports)} stable import buttons passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
