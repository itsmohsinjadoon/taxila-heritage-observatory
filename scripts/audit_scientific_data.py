#!/usr/bin/env python3
"""Validate the frozen ProjectTaxila evidence at its declared analytical grain."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import rasterio


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = ROOT / "data" / "Taxila_CHIP_Frozen_Evidence_Data"
EPOCHS = {"E2004", "E2009", "E2014", "E2019", "E2024"}
RADII = {250, 500, 1000}


@dataclass
class Check:
    check_id: str
    passed: bool
    severity: str
    observed: Any
    expected: Any
    implication: str


def add(
    checks: list[Check],
    check_id: str,
    passed: bool,
    observed: Any,
    expected: Any,
    implication: str,
    severity: str = "high",
) -> None:
    checks.append(Check(check_id, bool(passed), severity, observed, expected, implication))


def verify_checksums(data_root: Path) -> tuple[int, list[str]]:
    failures: list[str] = []
    total = 0
    for line in (data_root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split(maxsplit=1)
        path = data_root / relative.strip()
        total += 1
        if not path.is_file():
            failures.append(f"missing:{relative.strip()}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest.lower() != expected.lower():
            failures.append(f"hash:{relative.strip()}")
    return total, failures


def key_duplicates(frame: pd.DataFrame, columns: list[str]) -> int:
    return int(frame.duplicated(columns).sum())


def table_profile(frame: pd.DataFrame) -> dict[str, int]:
    return {
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "duplicate_rows": int(frame.duplicated().sum()),
        "null_cells": int(frame.isna().sum().sum()),
    }


def audit(data_root: Path) -> dict[str, Any]:
    checks: list[Check] = []
    profiles: dict[str, Any] = {}

    checksum_total, checksum_failures = verify_checksums(data_root)
    add(
        checks,
        "frozen_sha256_manifest",
        not checksum_failures,
        {"verified": checksum_total - len(checksum_failures), "failures": checksum_failures},
        {"verified": checksum_total, "failures": []},
        "A failure means the frozen evidence no longer matches its recorded study snapshot.",
        "critical",
    )

    vectors = data_root / "06_processed_vectors"
    components = gpd.read_file(vectors / "taxila_components_epsg32643.geojson")
    profiles["components"] = {
        **table_profile(pd.DataFrame(components.drop(columns="geometry"))),
        "null_geometries": int(components.geometry.isna().sum()),
        "crs": str(components.crs),
    }
    add(checks, "component_inventory", len(components) == 18, len(components), 18,
        "The UNESCO inventory contains 18 component records.")
    add(checks, "component_id_unique", components["component_id"].is_unique,
        int(components["component_id"].nunique()), 18,
        "Duplicate identifiers would mix component-level observations.", "critical")
    missing_geometry = components.loc[components.geometry.isna(), "component_id"].astype(str).tolist()
    add(checks, "saraikala_geometry_boundary", missing_geometry == ["139-002"],
        missing_geometry, ["139-002"],
        "Exactly one known unresolved component geometry must remain explicit, not silently imputed.")
    add(checks, "component_crs", str(components.crs) == "EPSG:32643", str(components.crs),
        "EPSG:32643", "Metric analytical neighbourhoods require the declared projected CRS.")

    tables = data_root / "13_tables" / "baseline_reproduction"
    landsat = pd.read_csv(tables / "component_epoch_multiscale_landsat.csv")
    terrain = pd.read_csv(tables / "component_multiscale_terrain_hydrology.csv")
    scores = pd.read_csv(tables / "component_epoch_integrated_scores.csv")
    features = pd.read_csv(tables / "proxy_model_feature_table.csv")
    profiles.update({
        "landsat_component_epoch_radius": table_profile(landsat),
        "terrain_component_radius": table_profile(terrain),
        "integrated_scores": table_profile(scores),
        "proxy_features": table_profile(features),
    })

    expected_component_ids = set(components.loc[components.geometry.notna(), "component_id"].astype(str))
    for name, frame, key, expected_rows in [
        ("landsat", landsat, ["component_id", "radius_m", "epoch_id"], 17 * 3 * 5),
        ("terrain", terrain, ["component_id", "radius_m"], 17 * 3),
        ("scores", scores, ["component_id", "radius_m", "epoch_id"], 17 * 3 * 5),
    ]:
        add(checks, f"{name}_row_grain", len(frame) == expected_rows,
            len(frame), expected_rows, f"{name} must contain one row at its declared analytical grain.", "critical")
        add(checks, f"{name}_key_unique", key_duplicates(frame, key) == 0,
            key_duplicates(frame, key), 0, f"Duplicate {name} keys would double-count components.", "critical")
        add(checks, f"{name}_complete_components",
            set(frame["component_id"].astype(str)) == expected_component_ids,
            len(set(frame["component_id"].astype(str))), 17,
            f"{name} must cover every mapped component and exclude unresolved Saraikala.")
        add(checks, f"{name}_no_null_cells", int(frame.isna().sum().sum()) == 0,
            int(frame.isna().sum().sum()), 0, f"Unexpected missing values would alter {name} results.")
        add(checks, f"{name}_radii", set(frame["radius_m"].astype(int)) == RADII,
            sorted(set(frame["radius_m"].astype(int))), sorted(RADII),
            f"{name} must retain the 250, 500 and 1000 m sensitivity design.")
        if "epoch_id" in frame:
            add(checks, f"{name}_epochs", set(frame["epoch_id"].astype(str)) == EPOCHS,
                sorted(set(frame["epoch_id"].astype(str))), sorted(EPOCHS),
                f"{name} must retain all five declared Landsat epochs.")

    add(checks, "proxy_pixel_key_unique", key_duplicates(features, ["row", "col"]) == 0,
        key_duplicates(features, ["row", "col"]), 0,
        "Duplicated pixels would inflate the proxy benchmark.", "critical")
    add(checks, "proxy_no_null_cells", int(features.isna().sum().sum()) == 0,
        int(features.isna().sum().sum()), 0, "Missing model features would change the fitted sample.")
    add(checks, "proxy_classes", set(features["proxy_class"].astype(int)) == set(range(1, 7)),
        sorted(set(features["proxy_class"].astype(int))), list(range(1, 7)),
        "The fixed target contains six WorldCover-derived proxy classes.")
    block_columns = features["spatial_block"].astype(int) % 10
    canonical_test = block_columns.isin([3, 4])
    canonical_buffer = block_columns.isin([2, 5])
    canonical_development = ~(canonical_test | canonical_buffer)
    canonical_counts = {
        "development": int(canonical_development.sum()),
        "buffer_excluded": int(canonical_buffer.sum()),
        "outer_proxy_test": int(canonical_test.sum()),
    }
    add(checks, "proxy_canonical_partition_counts",
        canonical_counts == {"development": 12094, "buffer_excluded": 4467, "outer_proxy_test": 4188},
        canonical_counts, {"development": 12094, "buffer_excluded": 4467, "outer_proxy_test": 4188},
        "A changed block-column split invalidates the locked spatial benchmark.", "critical")
    canonical_block_counts = {
        "development": int(features.loc[canonical_development, "spatial_block"].nunique()),
        "buffer_excluded": int(features.loc[canonical_buffer, "spatial_block"].nunique()),
        "outer_proxy_test": int(features.loc[canonical_test, "spatial_block"].nunique()),
    }
    add(checks, "proxy_canonical_partition_blocks",
        canonical_block_counts == {"development": 60, "buffer_excluded": 20, "outer_proxy_test": 20},
        canonical_block_counts, {"development": 60, "buffer_excluded": 20, "outer_proxy_test": 20},
        "The development, buffer and test geographies must preserve the declared block design.", "critical")
    legacy_test = features["partition"].eq("outer_proxy_test")
    profiles["proxy_partition_contract"] = {
        "canonical_rule": "block columns 3–4 test; 2 and 5 buffer; remaining columns development",
        "legacy_partition_field_mismatches": int((legacy_test != canonical_test).sum()),
        "legacy_field_status": "retained frozen metadata; not consumed by the canonical model",
    }

    climate = pd.read_csv(data_root / "04_cleaned_data" / "open_meteo_era5_seamless_site_daily.csv")
    profiles["climate_site_daily"] = table_profile(climate)
    dates = pd.to_datetime(climate["date"], errors="coerce")
    expected_dates = pd.date_range("1991-01-01", "2025-12-31", freq="D")
    add(checks, "climate_daily_coverage",
        len(climate) == len(expected_dates) and dates.nunique() == len(expected_dates),
        {"rows": len(climate), "unique_dates": int(dates.nunique()),
         "start": str(dates.min().date()), "end": str(dates.max().date())},
        {"rows": len(expected_dates), "unique_dates": len(expected_dates),
         "start": "1991-01-01", "end": "2025-12-31"},
        "Missing or duplicated days would bias climate aggregation.", "critical")
    add(checks, "climate_no_null_cells", int(climate.isna().sum().sum()) == 0,
        int(climate.isna().sum().sum()), 0, "Unexpected gaps would alter annual and seasonal context.")

    raster_root = data_root / "05_processed_rasters"
    raster_rows: list[dict[str, Any]] = []
    for path in sorted(raster_root.glob("*.tif")):
        with rasterio.open(path) as dataset:
            raster_rows.append({
                "file": path.name,
                "width": dataset.width,
                "height": dataset.height,
                "bands": dataset.count,
                "crs": str(dataset.crs),
                "pixel_x": dataset.transform.a,
                "pixel_y": dataset.transform.e,
                "origin_x": dataset.transform.c,
                "origin_y": dataset.transform.f,
            })
    profiles["rasters"] = {"files": len(raster_rows), "specifications": raster_rows}
    raster_alignment = all(
        row["width"] == 616 and row["height"] == 655 and row["crs"] == "EPSG:32643"
        and row["pixel_x"] == 30.0 and row["pixel_y"] == -30.0
        and row["origin_x"] == 292980.0 and row["origin_y"] == 3748620.0
        for row in raster_rows
    )
    add(checks, "raster_grid_alignment", len(raster_rows) == 21 and raster_alignment,
        {"files": len(raster_rows), "all_aligned": raster_alignment},
        {"files": 21, "all_aligned": True},
        "Misaligned rasters would invalidate pixelwise endpoint and component extraction.", "critical")

    failed = [check for check in checks if not check.passed]
    return {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "data_root": "data/Taxila_CHIP_Frozen_Evidence_Data",
        "intended_grain": {
            "components": "18 inventory records; 17 mapped analytical points",
            "landsat_and_scores": "component × radius × epoch",
            "terrain": "component × radius",
            "climate": "one site-mean row per day",
            "proxy_features": "one row per sampled raster pixel",
        },
        "status": "PASS" if not failed else "FAIL",
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "checks": [asdict(check) for check in checks],
        "profiles": profiles,
        "scientific_boundary": (
            "These checks establish internal completeness, declared grain and file integrity. "
            "They do not create field-condition labels, official UNESCO polygons, station validation, "
            "causal identification or external-site accuracy."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    report = audit(args.data_root.resolve())
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if not args.quiet:
        print(rendered)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
