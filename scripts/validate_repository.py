#!/usr/bin/env python3
"""Lightweight, dependency-free structural validation for ProjectTaxila."""

from __future__ import annotations

import ast
import csv
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_GITHUB_BYTES = 95 * 1024 * 1024

REQUIRED = [
    "README.md",
    "CITATION.cff",
    "requirements.txt",
    "notebooks/Taxila_CHIP_Q1_Executable_Analysis.ipynb",
    "data/Taxila_CHIP_Frozen_Evidence_Data/README.md",
    "data/Taxila_CHIP_Frozen_Evidence_Data/SHA256SUMS.txt",
    "data/Taxila_CHIP_Frozen_Evidence_Data/17_reproducibility/software_environment.json",
    "data/Taxila_CHIP_Frozen_Evidence_Data/16_validation/final_experiment_run_validation.json",
    "manuscript/main.tex",
    "manuscript/references.bib",
    "manuscript/supplementary/supplementary_information.tex",
    "manuscript/CLAIM_EVIDENCE_AUDIT.csv",
    "experiments/integrated/analysis/run_integrated_experiments.py",
    "experiments/integrated/analysis/validation/integrated_experiment_validation.json",
]

SECRET_PATTERNS = {
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    files = sorted(path for path in ROOT.rglob("*") if path.is_file() and ".git" not in path.parts)

    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            fail(f"missing required file: {relative}", errors)

    for path in files:
        relative = path.relative_to(ROOT)
        if path.stat().st_size > MAX_GITHUB_BYTES:
            fail(f"file exceeds 95 MiB safety limit: {relative}", errors)

        if path.suffix == ".json" or path.suffix == ".ipynb":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 - validation should report all parse failures
                fail(f"invalid JSON: {relative}: {exc}", errors)

        if path.suffix == ".py":
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
            except Exception as exc:  # noqa: BLE001
                fail(f"invalid Python syntax: {relative}: {exc}", errors)

        if path.suffix == ".csv":
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    list(csv.reader(handle))
            except Exception as exc:  # noqa: BLE001
                fail(f"unreadable CSV: {relative}: {exc}", errors)

        if path.suffix.lower() in {".md", ".txt", ".py", ".json", ".yml", ".yaml", ".tex", ".bib"}:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    fail(f"possible {label} in {relative}", errors)

    notebook = ROOT / "notebooks/Taxila_CHIP_Q1_Executable_Analysis.ipynb"
    if notebook.is_file():
        payload = json.loads(notebook.read_text(encoding="utf-8"))
        outputs = sum(len(cell.get("outputs", [])) for cell in payload.get("cells", []))
        if outputs:
            fail(f"clean source notebook contains {outputs} committed outputs", errors)

    if errors:
        print("ProjectTaxila validation FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"ProjectTaxila validation PASSED: {len(files)} files checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())

