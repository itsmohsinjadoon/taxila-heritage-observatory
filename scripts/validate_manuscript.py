#!/usr/bin/env python3
"""Pre-submission structural validation of the manuscript sources.

Checks the classes of error that otherwise surface only at compile time, plus
the Journal of Cultural Heritage submission constraints:

  * unresolved \\input targets
  * missing graphics files
  * undefined \\ref / \\eqref targets and duplicate \\label definitions
  * \\cite keys absent from references.bib, and unbalanced environments
  * unbalanced braces per source file
  * display-item count against the 10-item cap
  * body word count against the 5,000-word cap (abstract, declarations,
    float contents and references excluded)
  * Research aim section against the 200-word cap
  * highlights count and per-highlight character limit
  * unresolved [[...]] author placeholders

Exit status is non-zero if any hard check fails. Placeholders are reported as
warnings, since they are expected until the authors resolve them.

Usage
-----
    python scripts/validate_manuscript.py --manuscript manuscript
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

WORD_CAP = 5000
DISPLAY_CAP = 10
AIM_CAP = 200
HIGHLIGHT_CHARS = 85
HIGHLIGHT_RANGE = (3, 5)

INPUT_RE = re.compile(r"\\input\{([^}]+)\}")
GRAPHIC_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
REF_RE = re.compile(r"\\(?:ref|eqref|autoref)\{([^}]+)\}")
CITE_RE = re.compile(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]+)\}")
BIBKEY_RE = re.compile(r"@\w+\{([^,]+),")
ENV_RE = re.compile(r"\\(begin|end)\{([a-zA-Z*]+)\}")

# Sections counted towards the body word limit.
BODY_SECTIONS = ["02_introduction", "04_methods", "05_results",
                 "06_discussion", "07_conclusions"]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def resolve(path: Path, root: Path, seen: set[Path] | None = None,
            missing: list[str] | None = None) -> str:
    seen = set() if seen is None else seen
    missing = [] if missing is None else missing
    real = path.resolve()
    if real in seen:
        return ""
    seen.add(real)
    if not path.exists():
        missing.append(str(path))
        return ""
    text = read(path)
    out, pos = [], 0
    for m in INPUT_RE.finditer(text):
        out.append(text[pos:m.start()])
        name = m.group(1)
        out.append(resolve(root / (name if name.endswith(".tex") else name + ".tex"),
                           root, seen, missing))
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


# A comment starts at an unescaped '%'. Matching bare '%' would swallow the
# rest of any line containing an escaped percent sign (e.g. "95\%"), which
# silently truncates captions and produces spurious brace-imbalance reports.
COMMENT_RE = re.compile(r"(?m)(?<!\\)%.*$")


def word_count(tex: str) -> int:
    t = COMMENT_RE.sub("", tex)
    t = re.sub(r"\\begin\{(figure|table|longtable|equation|align|aligned)\*?\}"
               r".*?\\end\{\1\*?\}", " ", t, flags=re.S)
    t = re.sub(r"\\(?:cite[a-zA-Z]*|ref|eqref|label|includegraphics|input)\*?"
               r"(?:\[[^\]]*\])*\{[^}]*\}", " X ", t)
    t = re.sub(r"\\[a-zA-Z]+\*?", " ", t)
    t = re.sub(r"[{}$&\\~^_]", " ", t)
    return len([w for w in t.split() if any(c.isalnum() for c in w)])


def brace_balance(tex: str) -> int:
    t = COMMENT_RE.sub("", tex)
    t = re.sub(r"\\[{}]", "", t)
    return t.count("{") - t.count("}")


def env_balance(tex: str) -> list[str]:
    t = COMMENT_RE.sub("", tex)
    stack, errs = [], []
    for kind, env in ENV_RE.findall(t):
        if kind == "begin":
            stack.append(env)
        elif not stack:
            errs.append(f"\\end{{{env}}} with no matching begin")
        elif stack[-1] != env:
            errs.append(f"\\end{{{env}}} closes \\begin{{{stack[-1]}}}")
            stack.pop()
        else:
            stack.pop()
    errs += [f"unclosed \\begin{{{e}}}" for e in stack]
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manuscript", type=Path, default=Path("manuscript"))
    args = ap.parse_args()
    root = args.manuscript
    fails: list[str] = []
    warns: list[str] = []

    # --- main document -----------------------------------------------------
    missing_inputs: list[str] = []
    doc = resolve(root / "main.tex", root, missing=missing_inputs)
    supp_dir = root / "supplementary"
    missing_supp: list[str] = []
    supp = resolve(supp_dir / "supplementary_information.tex", supp_dir,
                   missing=missing_supp)
    if missing_inputs:
        fails.append(f"main: unresolved \\input targets: {missing_inputs}")
    if missing_supp:
        fails.append(f"supplement: unresolved \\input targets: {missing_supp}")

    fig_dirs = [root / "figures" / "main", root / "figures" / "supplementary"]
    for name, text in (("main", doc), ("supplement", supp)):
        for g in GRAPHIC_RE.findall(text):
            if not any((d / g).exists() for d in fig_dirs):
                fails.append(f"{name}: graphics file not found: {g}")

    for name, text in (("main", doc), ("supplement", supp)):
        labels = LABEL_RE.findall(text)
        dupes = {x for x in labels if labels.count(x) > 1}
        if dupes:
            fails.append(f"{name}: duplicate labels: {sorted(dupes)}")
        undefined = sorted(set(REF_RE.findall(text)) - set(labels))
        if undefined:
            fails.append(f"{name}: undefined references: {undefined}")
        unused = sorted(set(labels) - set(REF_RE.findall(text)))
        if unused:
            warns.append(f"{name}: labels defined but never referenced: {unused}")
        for err in env_balance(text):
            fails.append(f"{name}: {err}")

    bib = read(root / "references.bib")
    keys = {k.strip() for k in BIBKEY_RE.findall(bib)}
    cited: set[str] = set()
    for text in (doc, supp):
        for group in CITE_RE.findall(text):
            cited.update(k.strip() for k in group.split(","))
    absent = sorted(cited - keys)
    if absent:
        fails.append(f"cited keys absent from references.bib: {absent}")

    for tex_file in sorted((root / "sections").glob("*.tex")):
        if (bal := brace_balance(read(tex_file))) != 0:
            fails.append(f"{tex_file.name}: brace imbalance {bal:+d}")

    # --- submission constraints -------------------------------------------
    n_fig = len(re.findall(r"\\begin\{figure\}", doc))
    n_tab = len(re.findall(r"\\begin\{table\}", doc))
    if n_fig + n_tab > DISPLAY_CAP:
        fails.append(f"display items {n_fig + n_tab} exceed cap {DISPLAY_CAP}")

    body = sum(word_count(read(root / "sections" / f"{s}.tex")) for s in BODY_SECTIONS)
    if body > WORD_CAP:
        fails.append(f"body word count {body} exceeds cap {WORD_CAP}")

    intro = read(root / "sections" / "02_introduction.tex")
    if "\\section{Research aim}" not in intro:
        fails.append("Research aim section missing")
    else:
        aim = word_count(intro.split("\\section{Research aim}")[1])
        if aim > AIM_CAP:
            fails.append(f"Research aim {aim} words exceeds cap {AIM_CAP}")

    hl_path = root / "highlights.txt"
    highlights = [ln.strip().lstrip("-").strip()
                  for ln in read(hl_path).splitlines() if ln.strip()]
    if not HIGHLIGHT_RANGE[0] <= len(highlights) <= HIGHLIGHT_RANGE[1]:
        fails.append(f"{len(highlights)} highlights outside {HIGHLIGHT_RANGE}")
    for h in highlights:
        if len(h) > HIGHLIGHT_CHARS:
            fails.append(f"highlight exceeds {HIGHLIGHT_CHARS} chars ({len(h)}): {h[:60]}")

    for tex_file in sorted(root.rglob("*.tex")):
        if "unused" in tex_file.parts:
            continue
        for m in re.finditer(r"\[\[(.+?)\]\]", read(tex_file)):
            warns.append(f"{tex_file.name}: unresolved placeholder: {m.group(1)[:70]}")

    # --- report ------------------------------------------------------------
    print(f"main display items : {n_fig} figures + {n_tab} tables = {n_fig + n_tab} (cap {DISPLAY_CAP})")
    print(f"body word count    : {body} (cap {WORD_CAP})")
    print(f"citations          : {len(cited)} cited, {len(keys)} in bib")
    print(f"highlights         : {len(highlights)}, max {max((len(h) for h in highlights), default=0)} chars")
    for w in warns:
        print(f"WARN  {w}")
    for f in fails:
        print(f"FAIL  {f}")
    print("\nRESULT:", "PASS" if not fails else f"{len(fails)} FAILURE(S)")
    if not fails:
        print("\nTo produce PDFs (requires a local TeX distribution):")
        print("  cd manuscript && latexmk -pdf main.tex")
        print("  cd manuscript && latexmk -pdf title_page.tex")
        print("  cd manuscript/supplementary && latexmk -pdf supplementary_information.tex")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
