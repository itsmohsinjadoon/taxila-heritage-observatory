#!/usr/bin/env python3
"""Deterministic structural and checksum validation for Stage 4 outputs."""

from __future__ import annotations

import hashlib
import json
import pathlib

import numpy as np
import rasterio
from affine import Affine


ROOT = pathlib.Path(__file__).resolve().parent


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    config = json.load((ROOT / "batch1_config.json").open(encoding="utf-8"))
    discovery = json.load((ROOT / "outputs" / "discovery_validation.json").open(encoding="utf-8"))
    report = json.load((ROOT / "outputs" / "preprocessing_validation.json").open(encoding="utf-8"))
    transform = Affine.from_gdal(*config["spatial_contract"]["transform_gdal"])
    checks = []

    def add(name: str, passed: bool, observed=None) -> None:
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "observed": observed})

    add("discovery_checks_pass", discovery["fail_count"] == 0, discovery)
    add("preprocessing_global_checks_pass", report["fail_count"] == 0, report["global_checks"])
    add("five_unique_epoch_audits", [row["epoch_id"] for row in report["epoch_audits"]] == ["E2004", "E2009", "E2014", "E2019", "E2024"])
    add("scene_audit_count_matches_inventory", len(report["scene_audits"]) == 77, len(report["scene_audits"]))
    add("no_processing_failures", all(row["processing_failures"] == 0 for row in report["epoch_audits"]))
    add("all_epoch_gates_pass", all(all(value == "PASS" for value in row["checks"].values()) for row in report["epoch_audits"]))

    raster_count = 0
    hash_failures = []
    grid_failures = []
    band_failures = []
    for epoch in report["epoch_audits"]:
        for name, meta in epoch["outputs"].items():
            path = pathlib.Path(meta["path"])
            if not path.is_absolute():
                path = ROOT / path
            raster_count += 1
            if not path.exists() or sha256(path) != meta["sha256"]:
                hash_failures.append(str(path))
                continue
            with rasterio.open(path) as dataset:
                grid_ok = (
                    dataset.width == config["spatial_contract"]["width"]
                    and dataset.height == config["spatial_contract"]["height"]
                    and str(dataset.crs) == config["spatial_contract"]["target_crs"]
                    and dataset.transform.almost_equals(transform, precision=1e-9)
                )
                if not grid_ok:
                    grid_failures.append(str(path))
                expected_bands = 6 if "surface_reflectance" in name else (4 if name == "indices" else 1)
                if dataset.count != expected_bands:
                    band_failures.append(str(path))
                array = dataset.read(masked=True)
                if name in {"native_surface_reflectance", "oli_like_surface_reflectance", "indices"} and not np.isfinite(array.compressed()).all():
                    band_failures.append(f"non-finite:{path}")
    add("twenty_five_output_rasters", raster_count == 25, raster_count)
    add("all_output_hashes_match", not hash_failures, hash_failures)
    add("all_rasters_match_stage3_grid", not grid_failures, grid_failures)
    add("all_raster_band_contracts_pass", not band_failures, band_failures)

    result = {
        "schema_version": "1.0",
        "checks": checks,
        "pass_count": sum(row["status"] == "PASS" for row in checks),
        "fail_count": sum(row["status"] == "FAIL" for row in checks),
    }
    destination = ROOT / "outputs" / "stage4_structural_validation.json"
    with destination.open("w", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))
    return 0 if result["fail_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
