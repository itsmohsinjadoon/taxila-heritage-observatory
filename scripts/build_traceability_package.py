#!/usr/bin/env python3
"""Regenerate the manuscript traceability package from the manuscript itself.

Earlier generations of this repository maintained the display-item map and the
equation-code map by hand. They desynchronised from the manuscript: the maps
described a 14-figure, 18-equation article that no longer existed, and every
figure path in the display-item map pointed at a filename absent from the
repository. This script removes the possibility by deriving both maps from the
compiled source, so they cannot drift from the document again.

It parses ``main.tex`` and ``supplementary/supplementary_information.tex``,
resolves ``\\input`` recursively, and walks float and equation environments in
document order to assign the numbers LaTeX itself would assign.

Usage
-----
    python scripts/build_traceability_package.py --manuscript manuscript
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

INPUT_RE = re.compile(r"\\input\{([^}]+)\}")
FLOAT_RE = re.compile(
    r"\\begin\{(?P<env>figure|table)\*?\}(?P<body>.*?)\\end\{(?P=env)\*?\}", re.S)
EQ_RE = re.compile(r"\\begin\{equation\*?\}(?P<body>.*?)\\end\{equation\*?\}", re.S)
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
GRAPHIC_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
CAPTION_RE = re.compile(r"\\caption\{")
SECTION_RE = re.compile(r"\\(?P<level>sub)?section\*?\{(?P<title>[^}]*)\}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def resolve(path: Path, root: Path, seen: set[Path] | None = None) -> str:
    """Inline \\input files recursively, once each, preserving document order."""
    seen = set() if seen is None else seen
    real = path.resolve()
    if real in seen or not path.exists():
        return ""
    seen.add(real)
    text = read(path)
    out, pos = [], 0
    for m in INPUT_RE.finditer(text):
        out.append(text[pos:m.start()])
        name = m.group(1)
        target = root / (name if name.endswith(".tex") else name + ".tex")
        out.append(resolve(target, root, seen))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


def balanced_caption(body: str) -> str:
    """Extract the caption text, honouring nested braces."""
    m = CAPTION_RE.search(body)
    if not m:
        return ""
    i = m.end() - 1
    depth = 0
    for j in range(i, len(body)):
        if body[j] == "{":
            depth += 1
        elif body[j] == "}":
            depth -= 1
            if depth == 0:
                return " ".join(body[i + 1:j].split())
    return ""


def section_at(doc: str, index: int) -> str:
    """Nearest preceding section/subsection heading."""
    sec = sub = ""
    for m in SECTION_RE.finditer(doc, 0, index):
        if m.group("level"):
            sub = m.group("title")
        else:
            sec, sub = m.group("title"), ""
    return f"{sec} / {sub}".strip(" /") if sec else ""


def display_items(doc: str, prefix: str) -> list[dict]:
    counters = {"figure": 0, "table": 0}
    rows = []
    for m in FLOAT_RE.finditer(doc):
        env, body = m.group("env"), m.group("body")
        counters[env] += 1
        label = LABEL_RE.search(body)
        rows.append({
            "item_id": f"{prefix}{'F' if env == 'figure' else 'T'}{counters[env]}",
            "type": env,
            "number_as_compiled": f"{prefix}{counters[env]}",
            "label": label.group(1) if label else "",
            "graphics_file": "; ".join(GRAPHIC_RE.findall(body)),
            "manuscript_section": section_at(doc, m.start()),
            "caption_first_sentence": balanced_caption(body).split(". ")[0][:300],
        })
    return rows


def equations(doc: str) -> list[dict]:
    rows = []
    for n, m in enumerate(EQ_RE.finditer(doc), start=1):
        body = m.group("body")
        label = LABEL_RE.search(body)
        rows.append({
            "equation_number_as_compiled": n,
            "label": label.group(1) if label else "",
            "manuscript_section": section_at(doc, m.start()),
            "latex_first_line": " ".join(body.strip().splitlines()[0].split())[:220],
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manuscript", type=Path, default=Path("manuscript"))
    args = ap.parse_args()
    root = args.manuscript
    outdir = root / "source_traceability"
    outdir.mkdir(parents=True, exist_ok=True)

    main_doc = resolve(root / "main.tex", root)
    supp_path = root / "supplementary" / "supplementary_information.tex"
    supp_doc = resolve(supp_path, supp_path.parent)

    items = display_items(main_doc, "") + display_items(supp_doc, "S")
    eqs = equations(main_doc)
    write_csv(outdir / "display_item_source_map.csv", items)
    write_csv(outdir / "equation_code_map.csv", eqs)

    n_fig = sum(1 for r in items if r["type"] == "figure" and not r["item_id"].startswith("S"))
    n_tab = sum(1 for r in items if r["type"] == "table" and not r["item_id"].startswith("S"))
    missing = [r["graphics_file"] for r in items if r["graphics_file"] and not any(
        (root / "figures" / sub / g).exists()
        for g in r["graphics_file"].split("; ") for sub in ("main", "supplementary"))]

    receipt = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": Path(__file__).name,
        "main_display_items": {"figures": n_fig, "tables": n_tab, "total": n_fig + n_tab},
        "supplementary_display_items": sum(1 for r in items if r["item_id"].startswith("S")),
        "main_numbered_equations": len(eqs),
        "graphics_files_not_found": missing,
        "note": ("Derived from the compiled source rather than maintained by hand, so the "
                 "maps cannot desynchronise from the manuscript."),
    }
    (outdir / "traceability_build_receipt.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
