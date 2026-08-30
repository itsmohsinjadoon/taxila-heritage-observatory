#!/usr/bin/env python3
"""Structural and protocol validation for Stage 4 Batch 2 outputs."""

from __future__ import annotations

import json
import pathlib
import platform

import numpy as np
import pandas as pd
import rasterio
import sklearn


ROOT = pathlib.Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
CONFIG = json.loads((ROOT / "batch2_config.json").read_text(encoding="utf-8"))
EPOCHS = [item["epoch_id"] for item in CONFIG["epochs"]]


def exact_grid(path: pathlib.Path, reference: dict) -> list[dict]:
    checks = []
    with rasterio.open(path) as ds:
        checks.extend(
            [
                {"file": path.name, "check": "crs", "pass": str(ds.crs) == reference["crs"]},
                {"file": path.name, "check": "width", "pass": ds.width == reference["width"]},
                {"file": path.name, "check": "height", "pass": ds.height == reference["height"]},
                {"file": path.name, "check": "transform", "pass": np.allclose(tuple(ds.transform), reference["transform"])},
            ]
        )
    return checks


def main() -> None:
    reference = {
        "crs": CONFIG["analysis_grid"]["crs"],
        "width": CONFIG["analysis_grid"]["width"],
        "height": CONFIG["analysis_grid"]["height"],
        "transform": tuple(CONFIG["analysis_grid"]["transform"] + [0.0, 0.0, 1.0]),
    }
    checks = []
    raster_paths = [
        OUTPUTS / "worldcover_2020_2021_consensus_proxy_labels.tif",
        OUTPUTS / "worldcover_consensus_proxy_purity.tif",
    ]
    for epoch in EPOCHS:
        raster_paths.extend(
            [
                OUTPUTS / f"{epoch}_provisional_landcover.tif",
                OUTPUTS / f"{epoch}_class_probabilities.tif",
                OUTPUTS / f"{epoch}_maximum_class_probability.tif",
                OUTPUTS / f"{epoch}_normalized_entropy.tif",
            ]
        )
    for path in raster_paths:
        checks.extend(exact_grid(path, reference))

    for epoch in EPOCHS:
        with rasterio.open(OUTPUTS / f"{epoch}_provisional_landcover.tif") as ds:
            values = ds.read(1)
            checks.append({"file": ds.name, "check": "class_domain_0_to_6", "pass": bool(np.isin(np.unique(values), np.arange(7)).all())})
        with rasterio.open(OUTPUTS / f"{epoch}_class_probabilities.tif") as ds:
            probabilities = ds.read()
            valid = probabilities[0] != ds.nodata
            sums = probabilities[:, valid].sum(axis=0)
            checks.extend(
                [
                    {"file": ds.name, "check": "six_probability_bands", "pass": ds.count == 6},
                    {"file": ds.name, "check": "probability_domain", "pass": bool(((probabilities[:, valid] >= 0) & (probabilities[:, valid] <= 1)).all())},
                    {"file": ds.name, "check": "probability_sum", "pass": bool(np.allclose(sums, 1.0, atol=1e-5))},
                ]
            )
        for suffix in ("maximum_class_probability", "normalized_entropy"):
            with rasterio.open(OUTPUTS / f"{epoch}_{suffix}.tif") as ds:
                values = ds.read(1)
                valid = values != ds.nodata
                checks.append({"file": ds.name, "check": "unit_interval", "pass": bool(((values[valid] >= 0) & (values[valid] <= 1 + 1e-6)).all())})

    reference_sample = pd.read_csv(OUTPUTS / "independent_reference_sample_template.csv", keep_default_na=False)
    allocations = reference_sample.groupby(["epoch_id", "mapped_class_id"]).size()
    checks.extend(
        [
            {"file": "independent_reference_sample_template.csv", "check": "row_count_2625", "pass": len(reference_sample) == 2625},
            {"file": "independent_reference_sample_template.csv", "check": "thirty_strata", "pass": len(allocations) == 30},
            {"file": "independent_reference_sample_template.csv", "check": "bare_quarry_150_per_epoch", "pass": bool(all(allocations[(epoch, 2)] == 150 for epoch in EPOCHS))},
            {"file": "independent_reference_sample_template.csv", "check": "other_classes_75_per_epoch", "pass": bool(all(allocations[(epoch, class_id)] == 75 for epoch in EPOCHS for class_id in [1, 3, 4, 5, 6]))},
            {"file": "independent_reference_sample_template.csv", "check": "reference_labels_blank", "pass": bool((reference_sample["reference_class_id_1_to_7"] == "").all())},
        ]
    )
    diagnostics = json.loads((OUTPUTS / "proxy_agreement_diagnostics.json").read_text(encoding="utf-8"))
    checks.append({"file": "proxy_agreement_diagnostics.json", "check": "zero_block_overlap", "pass": diagnostics["development_test_block_overlap"] == 0})
    temporal = json.loads((OUTPUTS / "temporal_plausibility_audit.json").read_text(encoding="utf-8"))
    checks.append({"file": "temporal_plausibility_audit.json", "check": "manuscript_result_gate_explicitly_failed", "pass": temporal["result_acceptance"] == "FAIL"})

    failures = [item for item in checks if not item["pass"]]
    report = {
        "status": "PASS" if not failures else "FAIL",
        "check_count": len(checks),
        "pass_count": len(checks) - len(failures),
        "fail_count": len(failures),
        "checks": checks,
        "scientific_gate_note": "Structural pass does not convert proxy agreement into independent accuracy; manuscript land-cover and change results remain blocked.",
    }
    (OUTPUTS / "structural_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    environment = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "rasterio": rasterio.__version__,
        "scikit_learn": sklearn.__version__,
        "gdal_transport_exception": "GDAL_HTTP_UNSAFESSL=YES was required only to access the controlled public COG proxy in this runtime; it is not part of the scientific method.",
    }
    (OUTPUTS / "software_environment.json").write_text(json.dumps(environment, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
