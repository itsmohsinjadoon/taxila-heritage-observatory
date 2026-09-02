#!/usr/bin/env python3
"""Execute the Taxila Heritage Observatory notebook and write an audit receipt."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import nbformat
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "Taxila_CHIP_Q1_Executable_Analysis.ipynb"
DATA_ROOT = ROOT / "data" / "Taxila_CHIP_Frozen_Evidence_Data"
PACKAGES = [
    "numpy", "pandas", "scipy", "scikit-learn", "matplotlib", "seaborn",
    "joblib", "rasterio", "geopandas", "pyogrio", "shapely", "pyproj",
    "nbformat", "nbclient",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def lock_summary(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"status": "MISSING", "passed": 0, "total": 0, "failed_claims": []}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    failed = [row.get("claim", "unnamed") for row in rows if row.get("pass", "").lower() != "true"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "passed": len(rows) - len(failed),
        "total": len(rows),
        "failed_claims": failed,
    }


def default_output(profile: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / "output" / "runs" / f"{stamp}-{profile}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["validation", "publication"], default="validation")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=3600, help="Per-cell timeout in seconds")
    args = parser.parse_args()

    run_dir = (args.output_dir or default_output(args.profile)).resolve()
    artifacts = run_dir / "artifacts"
    run_dir.mkdir(parents=True, exist_ok=False)
    artifacts.mkdir()
    executed_notebook = run_dir / f"Taxila_CHIP_Q1_{args.profile}_executed.ipynb"
    receipt_path = run_dir / "execution_receipt.json"

    os.environ["TAXILA_PROFILE"] = args.profile
    os.environ["TAXILA_OUTPUT_ROOT"] = str(artifacts)
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))

    started = datetime.now(timezone.utc)
    start_clock = time.perf_counter()
    receipt: dict[str, object] = {
        "schema_version": 1,
        "status": "RUNNING",
        "profile": args.profile,
        "started_utc": started.isoformat(),
        "git_commit": git_commit(),
        "source_notebook": NOTEBOOK.relative_to(ROOT).as_posix(),
        "source_notebook_sha256": sha256(NOTEBOOK),
        "data_root": DATA_ROOT.relative_to(ROOT).as_posix(),
        "random_seed": 311,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": package_versions(),
        "scientific_boundary": (
            "Relative landscape-pressure and field-inspection prioritisation only; "
            "not confirmed deterioration, causal climate impact, legal boundaries or external accuracy."
        ),
    }

    try:
        notebook = nbformat.read(NOTEBOOK, as_version=4)
        client = NotebookClient(
            notebook,
            timeout=args.timeout,
            kernel_name=notebook.metadata.get("kernelspec", {}).get("name", "python3"),
            resources={"metadata": {"path": str(NOTEBOOK.parent)}},
            allow_errors=False,
        )
        client.execute()
        nbformat.write(notebook, executed_notebook)

        quality_report = run_dir / "data_quality_report.json"
        quality = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "audit_scientific_data.py"),
                "--data-root", str(DATA_ROOT),
                "--output", str(quality_report),
                "--quiet",
            ],
            cwd=ROOT,
            check=False,
        )
        lock = lock_summary(artifacts / "validation" / "headline_evidence_lock.csv")
        receipt.update(
            {
                "status": "PASS" if quality.returncode == 0 and lock["status"] == "PASS" else "REVIEW",
                "executed_notebook": executed_notebook.name,
                "executed_notebook_sha256": sha256(executed_notebook),
                "artifact_manifest": "artifacts/output_manifest.csv",
                "headline_evidence_lock": lock,
                "data_quality_status": "PASS" if quality.returncode == 0 else "FAIL",
            }
        )
    except Exception as error:
        receipt.update({"status": "ERROR", "error_type": type(error).__name__, "error": str(error)})
        raise
    finally:
        finished = datetime.now(timezone.utc)
        receipt["finished_utc"] = finished.isoformat()
        receipt["duration_seconds"] = round(time.perf_counter() - start_clock, 3)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2))

    return 0 if receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
