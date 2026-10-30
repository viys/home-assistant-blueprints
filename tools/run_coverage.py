"""Run tests, export simulated YAML coverage, and gate changed control-flow blocks."""

import argparse
from collections import defaultdict
import html
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

from tools.blueprint_coverage import RECORDER, ROOT


NOTICE = ("Simulated YAML coverage only. Action hits mean reached/attempted, not successful delivery. "
          "Branches count whole condition true/false outcomes and choose selection/no-match. "
          "Jinja internals, trigger dispatch, top-level variables, HA semantics, and devices are not measured.")


def changed_lines(base):
    """Get changed new-side YAML lines from Git, failing on an invalid baseline."""
    # Argument arrays avoid shell interpretation of user-provided revision names.
    subprocess.run(["git", "rev-parse", "--verify", f"{base}^{{commit}}"],
                   cwd=ROOT, check=True, capture_output=True, text=True)
    diff = subprocess.run(["git", "diff", "--no-ext-diff", "--unified=0", base,
                           "--", "automation"], cwd=ROOT, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout
    changed = defaultdict(set)
    file = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            file = line[6:] if line.startswith("+++ b/") else None
        elif file and (match := re.match(r"@@ .* \+(\d+)(?:,(\d+))? @@", line)):
            first, count = int(match[1]), int(match[2] or 1)
            # A deletion-only hunk still changes the surrounding surviving block.
            changed[file].update(range(max(1, first), first + max(1, count)))
    return changed


def metric(rows):
    """Format covered opportunities without calling an empty denominator 100 percent."""
    # Whole-template outcomes count once each, regardless of repeated execution.
    covered = sum(row["hits"] > 0 for row in rows)
    return f"{covered}/{len(rows)} ({covered / len(rows):.1%})" if rows else "N/A"


def evaluate_gates(rows, thresholds, has_base):
    """Evaluate independent action/branch gates without rounding before comparison."""
    # Global gates always apply; diff gates need a baseline and nonempty opportunities.
    gates = []
    for name, minimum in thresholds.items():
        changed = name.startswith("changed_")
        actions = name.endswith("_actions")
        selected = [row for row in rows
                    if (row["kind"] == "action") == actions
                    and (not changed or (has_base and row.get("changed", False)))]
        covered = sum(row["hits"] > 0 for row in selected)
        total = len(selected)
        gates.append(dict(name=name, minimum=minimum, covered=covered, total=total,
                          percentage=covered * 100 / total if total else None,
                          passed=not total or covered * 100 >= total * minimum))
    return gates


def load_thresholds(path):
    """Require all four finite percentage thresholds in the shared configuration."""
    # Invalid/missing configuration must fail rather than silently disabling a gate.
    values = json.loads(path.read_text(encoding="utf-8"))
    expected = {"changed_actions", "changed_branches", "overall_actions", "overall_branches"}
    if not isinstance(values, dict) or set(values) != expected:
        raise ValueError("Thresholds must specify changed/overall actions and branches")
    for name, value in values.items():
        if (type(value) not in (int, float) or not math.isfinite(value)
                or not 0 <= value <= 100):
            raise ValueError(f"Invalid percentage threshold for {name}: {value!r}")
    return values


def write_reports(rows, output, changed, result, base, thresholds=None):
    """Export JSON, Markdown, and an escaped standalone HTML source report."""
    # A failed test run still produces a clearly marked diagnostic report.
    output.mkdir(parents=True, exist_ok=True)
    for row in rows:
        row["changed"] = bool(changed.get(row["file"], set()).intersection(
            range(row["line"], row["end_line"] + 1)))
    gates = evaluate_gates(rows, thresholds or {}, bool(base))
    payload = dict(measurement="simulated-yaml-control-flow", notice=NOTICE,
                   tests_passed=result.wasSuccessful(), tests_run=result.testsRun,
                   coverage_passed=all(gate["passed"] for gate in gates), gates=gates,
                   base=base, changed_files=sorted(changed), opportunities=rows)
    (output / "coverage.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    summary = ["# Simulated blueprint coverage", "", NOTICE, "",
               f"Tests: **{'PASS' if result.wasSuccessful() else 'FAIL'}** ({result.testsRun} tests)", "",
               f"Overall actions: **{metric([r for r in rows if r['kind'] == 'action'])}**; "
               f"branch outcomes: **{metric([r for r in rows if r['kind'] != 'action'])}**.", "",
               "| Blueprint | Actions reached | Branch outcomes | Changed actions | Changed branches |",
               "| --- | --- | --- | --- | --- |"]
    details = []
    for file in sorted({row["file"] for row in rows}):
        group = [row for row in rows if row["file"] == file]
        actions = [row for row in group if row["kind"] == "action"]
        branches = [row for row in group if row["kind"] != "action"]
        summary.append(f"| {file} | {metric(actions)} | {metric(branches)} | "
                       f"{metric([r for r in actions if r['changed']]) if base else 'N/A (no base)'} | "
                       f"{metric([r for r in branches if r['changed']]) if base else 'N/A (no base)'} |")
        entries = "".join(
            f"<tr class={'hit' if row['hits'] else 'miss'}><td><a href='#" +
            html.escape(file, quote=True) + f"-L{row['line']}'>L{row['line']}</a></td>"
            f"<td>{html.escape(row['path'])}</td><td>{row['kind']}: {row['outcome']}</td>"
            f"<td>{row['hits']}</td><td>{'changed' if row['changed'] else ''}</td></tr>"
            for row in group)
        source = "\n".join(f"<span id='{html.escape(file, quote=True)}-L{index}'>"
                           f"{index:4} {html.escape(line)}</span>"
                           for index, line in enumerate((ROOT / file).read_text(encoding="utf-8").splitlines(), 1))
        details.append(f"<h2>{html.escape(file)}</h2><table><tr><th>Line</th><th>Path</th>"
                       f"<th>Opportunity</th><th>Hits</th><th>Diff</th></tr>{entries}</table>"
                       f"<details><summary>YAML source</summary><pre>{source}</pre></details>")
    if gates:
        summary += ["", "## Coverage gates", "",
                    "| Gate | Coverage | Minimum | Result |", "| --- | --- | --- | --- |"]
        for gate in gates:
            actual = f"{gate['covered']}/{gate['total']} ({gate['percentage']:.1f}%)" if gate["total"] else "N/A"
            status = ("PASS" if gate["passed"] else "FAIL") if gate["total"] else "N/A (no opportunities/baseline)"
            summary.append(f"| {gate['name']} | {actual} | {gate['minimum']}% | {status} |")
    outside = [file for file, lines in changed.items() if not any(
        row["file"] == file and row["changed"] for row in rows)]
    if outside:
        summary += ["", "Changed files without measured control-flow blocks: " + ", ".join(outside),
                    "These changes have no coverage gate; review triggers, variables, templates, and metadata separately."]
    missing = [row for row in rows if row["changed"] and not row["hits"]]
    summary += ["", f"Uncovered changed opportunities: **{len(missing)}**", ""]
    summary += [f"- {row['file']}:{row['line']} — {row['kind']} {row['path']} [{row['outcome']}]"
                for row in missing]
    markdown = "\n".join(summary) + "\n"
    (output / "summary.md").write_text(markdown, encoding="utf-8")
    page = ("<!doctype html><html lang='en'><meta charset='utf-8'><title>Blueprint coverage</title>"
            "<style>body{font:15px system-ui;margin:32px;max-width:1400px}table{border-collapse:collapse}"
            "td,th{border:1px solid #bbb;padding:6px;text-align:left}.hit{background:#e5f5e8}"
            ".miss{background:#ffe9e7}pre{background:#f4f4f4;padding:16px;overflow:auto}"
            "pre span{display:block}h2{margin-top:40px}</style><h1>Simulated blueprint coverage</h1>"
            f"<pre>{html.escape(markdown)}</pre>" + "".join(details) + "</html>")
    (output / "index.html").write_text(page, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
            stream.write(markdown)
    return missing


def main():
    """Execute the complete suite and fail on any test failure or unmet coverage gate."""
    # Local runs work without Git history; PR CI passes an explicit baseline SHA.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "coverage-report")
    parser.add_argument("--base", help="Git commit/ref for changed-block coverage")
    parser.add_argument("--thresholds", type=Path, default=ROOT / "config/testing/coverage_thresholds.json",
                        help="JSON configuration for all four coverage gates")
    args = parser.parse_args()
    try:
        thresholds = load_thresholds(args.thresholds)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    changed = changed_lines(args.base) if args.base else {}
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.discover(str(ROOT / "tests")))
    rows = RECORDER.rows()
    write_reports(rows, args.output, changed, result, args.base, thresholds)
    gates = evaluate_gates(rows, thresholds, bool(args.base))
    print((args.output / "summary.md").read_text(encoding="utf-8"))
    return int(not result.wasSuccessful() or any(not gate["passed"] for gate in gates))


if __name__ == "__main__":
    sys.exit(main())
