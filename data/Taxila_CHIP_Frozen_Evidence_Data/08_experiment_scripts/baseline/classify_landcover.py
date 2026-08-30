#!/usr/bin/env python3
"""Build provisional land-cover products and a defensible validation design.

WorldCover is used only for weak supervision. Metrics against the held-out
WorldCover consensus are proxy-agreement diagnostics, not independent accuracy.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import os
import pathlib
import pickle
import urllib.parse
import urllib.request
from collections import Counter

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine, xy
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform as transform_coordinates
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_fscore_support,
)
from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold


ROOT = pathlib.Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
CONFIG_PATH = ROOT / "batch2_config.json"
OUTPUTS = ROOT / "outputs"
COMPOSITES = ROOT.parent / "stage4_batch1" / "outputs" / "composites"
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=120) as response:
        return json.load(response)


def signed_asset(href: str) -> str:
    query = urllib.parse.urlencode({"href": href})
    return get_json(f"{SIGN}?{query}")["href"]


def find_worldcover_asset(year: int, bbox: list[float]) -> dict:
    response = post_json(
        f"{STAC}/search",
        {
            "collections": ["esa-worldcover"],
            "bbox": bbox,
            "datetime": f"{year}-01-01/{year}-12-31",
            "limit": 10,
        },
    )
    if len(response.get("features", [])) != 1:
        raise RuntimeError(f"Expected exactly one WorldCover tile for {year}; found {len(response.get('features', []))}")
    item = response["features"][0]
    return {
        "year": year,
        "item_id": item["id"],
        "product_version": item["properties"]["esa_worldcover:product_version"],
        "unsigned_href": item["assets"]["map"]["href"],
    }


def write_raster(path: pathlib.Path, array: np.ndarray, profile: dict, descriptions: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = array if array.ndim == 3 else array[np.newaxis, ...]
    updated = profile.copy()
    updated.update(
        driver="GTiff",
        height=out.shape[1],
        width=out.shape[2],
        count=out.shape[0],
        dtype=str(out.dtype),
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
        BIGTIFF="IF_SAFER",
    )
    with rasterio.open(path, "w", **updated) as dst:
        dst.write(out)
        if descriptions:
            for band, description in enumerate(descriptions, start=1):
                dst.set_band_description(band, description)


def map_worldcover(values: np.ndarray, class_lookup: dict[int, int]) -> np.ndarray:
    result = np.zeros(values.shape, dtype=np.uint8)
    for source, target in class_lookup.items():
        result[values == source] = target
    return result


def majority_and_purity(mapped_high_res: np.ndarray, height: int, width: int, classes: list[int]) -> tuple[np.ndarray, np.ndarray]:
    cube = mapped_high_res.reshape(height, 3, width, 3).transpose(0, 2, 1, 3).reshape(height, width, 9)
    counts = np.stack([(cube == class_id).sum(axis=2) for class_id in classes], axis=0)
    winner = np.argmax(counts, axis=0)
    majority = np.take(np.array(classes, dtype=np.uint8), winner)
    best_count = np.take_along_axis(counts, winner[np.newaxis, ...], axis=0)[0]
    majority[best_count == 0] = 0
    return majority, best_count.astype(np.uint8)


def build_proxy_labels(config: dict, reference_profile: dict, bbox4326: list[float]) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    height = reference_profile["height"]
    width = reference_profile["width"]
    transform = reference_profile["transform"]
    high_transform = Affine(transform.a / 3, transform.b, transform.c, transform.d, transform.e / 3, transform.f)
    high_shape = (height * 3, width * 3)
    classes = [item["id"] for item in config["primary_legend"]]
    class_lookup = {
        source: item["id"]
        for item in config["primary_legend"]
        for source in item["worldcover_codes"]
    }
    yearly = []
    assets = []
    for year in (2020, 2021):
        asset = find_worldcover_asset(year, bbox4326)
        assets.append(asset)
        signed = signed_asset(asset["unsigned_href"])
        with rasterio.Env(GDAL_HTTP_UNSAFESSL="YES"):
            with rasterio.open(signed) as source:
                with WarpedVRT(
                    source,
                    crs=reference_profile["crs"],
                    transform=high_transform,
                    width=high_shape[1],
                    height=high_shape[0],
                    resampling=Resampling.nearest,
                    nodata=0,
                ) as vrt:
                    original = vrt.read(1)
        mapped = map_worldcover(original, class_lookup)
        yearly.append(majority_and_purity(mapped, height, width, classes))
    majority_2020, count_2020 = yearly[0]
    majority_2021, count_2021 = yearly[1]
    required = math.ceil(config["proxy_labels"]["minimum_within_year_purity"] * 9 - 1e-9)
    agreement = (
        (majority_2020 == majority_2021)
        & (majority_2020 > 0)
        & (count_2020 >= required)
        & (count_2021 >= required)
    )
    proxy = np.where(agreement, majority_2020, 0).astype(np.uint8)
    purity = np.where(agreement, np.minimum(count_2020, count_2021) / 9.0, 0).astype(np.float32)
    return proxy, purity, assets


def read_predictors(epoch_id: str) -> tuple[np.ndarray, dict]:
    sr_path = COMPOSITES / f"{epoch_id}_oli_like_surface_reflectance.tif"
    ix_path = COMPOSITES / f"{epoch_id}_oli_like_indices.tif"
    with rasterio.open(sr_path) as sr:
        bands = sr.read().astype(np.float32)
        profile = sr.profile.copy()
        sr_nodata = sr.nodata
    with rasterio.open(ix_path) as ix:
        indices = ix.read().astype(np.float32)
        ix_nodata = ix.nodata
    predictors = np.concatenate([bands, indices], axis=0)
    invalid = (~np.isfinite(predictors)).any(axis=0)
    if sr_nodata is not None:
        invalid |= (bands == sr_nodata).any(axis=0)
    if ix_nodata is not None:
        invalid |= (indices == ix_nodata).any(axis=0)
    predictors[:, invalid] = np.nan
    return predictors, profile


def balanced_proxy_sample(
    predictors: np.ndarray,
    labels: np.ndarray,
    maximum_per_class: int,
    seed: int,
    block_pixels: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    valid = (labels > 0) & np.isfinite(predictors).all(axis=0)
    rows, cols = np.where(valid)
    y_all = labels[rows, cols]
    chosen = []
    for class_id in sorted(np.unique(y_all)):
        candidates = np.flatnonzero(y_all == class_id)
        take = min(len(candidates), maximum_per_class)
        chosen.append(rng.choice(candidates, size=take, replace=False))
    selected = np.concatenate(chosen)
    rng.shuffle(selected)
    rows = rows[selected]
    cols = cols[selected]
    y = labels[rows, cols]
    X = predictors[:, rows, cols].T
    block_cols = math.ceil(labels.shape[1] / block_pixels)
    groups = (rows // block_pixels) * block_cols + (cols // block_pixels)
    return X, y, groups.astype(np.int32), rows.astype(np.int32), cols.astype(np.int32)


def select_outer_split(X: np.ndarray, y: np.ndarray, groups: np.ndarray, seed: int, n_splits: int) -> tuple[np.ndarray, np.ndarray, int]:
    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    all_classes = set(np.unique(y).tolist())
    candidates = []
    for fold, (train, test) in enumerate(splitter.split(X, y, groups)):
        present_train = set(np.unique(y[train]).tolist())
        present_test = set(np.unique(y[test]).tolist())
        completeness = len(all_classes & present_train) + len(all_classes & present_test)
        fraction_penalty = abs(len(test) / len(y) - 1 / n_splits)
        candidates.append((completeness, -fraction_penalty, -fold, train, test, fold))
    _, _, _, train, test, fold = max(candidates, key=lambda item: item[:3])
    return train, test, fold


def train_and_evaluate(config: dict, predictors: np.ndarray, labels: np.ndarray) -> tuple[RandomForestClassifier, dict, pd.DataFrame, np.ndarray, np.ndarray]:
    seed = config["random_seed"]
    resolution = config["analysis_grid"]["resolution_m"]
    block_pixels = round(config["model"]["spatial_block_size_m"] / resolution)
    X, y, groups, rows, cols = balanced_proxy_sample(
        predictors,
        labels,
        config["model"]["maximum_samples_per_class"],
        seed,
        block_pixels,
    )
    development, test, outer_fold = select_outer_split(
        X, y, groups, seed, config["model"]["outer_folds"]
    )
    base = config["model"]["base_parameters"].copy()
    model = RandomForestClassifier(random_state=seed, **base)
    inner = StratifiedGroupKFold(
        n_splits=config["model"]["inner_folds"],
        shuffle=True,
        random_state=seed + 1,
    )
    search = GridSearchCV(
        model,
        param_grid=config["model"]["tuning_grid"],
        scoring="f1_macro",
        cv=inner,
        n_jobs=-1,
        refit=True,
        return_train_score=False,
        error_score="raise",
    )
    search.fit(X[development], y[development], groups=groups[development])
    selected: RandomForestClassifier = search.best_estimator_
    predicted = selected.predict(X[test])
    probabilities = selected.predict_proba(X[test])
    classes = np.array([item["id"] for item in config["primary_legend"]])
    matrix = confusion_matrix(y[test], predicted, labels=classes)
    precision, recall, f1, support = precision_recall_fscore_support(
        y[test], predicted, labels=classes, zero_division=0
    )
    names = {item["id"]: item["name"] for item in config["primary_legend"]}
    class_metrics = pd.DataFrame(
        {
            "class_id": classes,
            "class_name": [names[value] for value in classes],
            "proxy_user_accuracy_precision": precision,
            "proxy_producer_accuracy_recall": recall,
            "proxy_f1": f1,
            "proxy_test_support": support,
        }
    )
    class_counts = {str(k): int(v) for k, v in Counter(y.tolist()).items()}
    class_groups = {str(k): int(len(np.unique(groups[y == k]))) for k in classes}
    diagnostics = {
        "role": "held-out WorldCover-consensus proxy agreement; not independent accuracy",
        "sample_count": int(len(y)),
        "class_sample_counts": class_counts,
        "class_spatial_block_counts": class_groups,
        "spatial_block_size_m": config["model"]["spatial_block_size_m"],
        "outer_fold_selected": int(outer_fold),
        "development_sample_count": int(len(development)),
        "test_sample_count": int(len(test)),
        "development_block_count": int(len(np.unique(groups[development]))),
        "test_block_count": int(len(np.unique(groups[test]))),
        "development_test_block_overlap": int(len(set(groups[development]) & set(groups[test]))),
        "best_parameters": search.best_params_,
        "best_inner_macro_f1": float(search.best_score_),
        "outer_proxy_overall_agreement": float(accuracy_score(y[test], predicted)),
        "outer_proxy_balanced_accuracy": float(balanced_accuracy_score(y[test], predicted)),
        "outer_proxy_macro_f1": float(f1_score(y[test], predicted, average="macro")),
        "outer_proxy_log_loss": float(log_loss(y[test], probabilities, labels=selected.classes_)),
        "confusion_matrix_reference_rows_map_columns": matrix.tolist(),
        "class_order": classes.tolist(),
        "independent_validation_gate": "BLOCKED_PENDING_HUMAN_REFERENCE_LABELS",
    }
    cv = pd.DataFrame(search.cv_results_)
    cv_columns = [
        "rank_test_score",
        "mean_test_score",
        "std_test_score",
        "param_max_depth",
        "param_min_samples_leaf",
        "mean_fit_time",
        "mean_score_time",
    ]
    cv[cv_columns].sort_values("rank_test_score").to_csv(OUTPUTS / "random_forest_tuning_results.csv", index=False)
    membership = pd.DataFrame(
        {
            "row": rows,
            "col": cols,
            "proxy_class": y,
            "spatial_block": groups,
            "partition": np.where(np.isin(np.arange(len(y)), test), "outer_proxy_test", "development"),
        }
    )
    membership.to_csv(OUTPUTS / "proxy_sample_partition.csv", index=False)
    return selected, diagnostics, class_metrics, development, test


def predict_epoch(model: RandomForestClassifier, predictors: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    bands, height, width = predictors.shape
    flat = predictors.reshape(bands, -1).T
    valid = np.isfinite(flat).all(axis=1)
    class_map = np.zeros(height * width, dtype=np.uint8)
    probability_map = np.full((len(model.classes_), height * width), np.nan, dtype=np.float32)
    indices = np.flatnonzero(valid)
    for start in range(0, len(indices), 50000):
        batch = indices[start : start + 50000]
        probs = model.predict_proba(flat[batch]).astype(np.float32)
        probability_map[:, batch] = probs.T
        class_map[batch] = model.classes_[np.argmax(probs, axis=1)].astype(np.uint8)
    max_probability = np.full(height * width, np.nan, dtype=np.float32)
    entropy = np.full(height * width, np.nan, dtype=np.float32)
    valid_probabilities = probability_map[:, valid]
    max_probability[valid] = np.max(valid_probabilities, axis=0)
    clipped = np.clip(valid_probabilities, 1e-7, 1.0)
    entropy[valid] = -np.sum(clipped * np.log(clipped), axis=0) / math.log(len(model.classes_))
    return (
        class_map.reshape(height, width),
        probability_map.reshape(len(model.classes_), height, width),
        max_probability.reshape(height, width).astype(np.float32),
        entropy.reshape(height, width).astype(np.float32),
    )


def spatially_spread_sample(candidates: np.ndarray, n: int, min_spacing_pixels: int, rng: np.random.Generator) -> np.ndarray:
    order = rng.permutation(len(candidates))
    chosen = []
    for idx in order:
        row, col = candidates[idx]
        if all(max(abs(int(row) - int(r)), abs(int(col) - int(c))) >= min_spacing_pixels for r, c in chosen):
            chosen.append((int(row), int(col)))
            if len(chosen) == n:
                break
    if len(chosen) < n:
        used = set(chosen)
        for idx in order:
            point = tuple(map(int, candidates[idx]))
            if point not in used:
                chosen.append(point)
                used.add(point)
                if len(chosen) == n:
                    break
    return np.array(chosen, dtype=np.int32)


def make_reference_sample(
    config: dict,
    class_maps: dict[str, np.ndarray],
    profiles: dict[str, dict],
) -> pd.DataFrame:
    target = config["independent_validation"]["target_per_mapped_class_per_epoch"]
    min_spacing = math.ceil(
        config["independent_validation"]["minimum_point_spacing_m"]
        / config["analysis_grid"]["resolution_m"]
    )
    names = {item["id"]: item["name"] for item in config["primary_legend"]}
    years = {item["epoch_id"]: item["label_year"] for item in config["epochs"]}
    records = []
    for epoch_index, epoch in enumerate(config["epochs"]):
        epoch_id = epoch["epoch_id"]
        class_map = class_maps[epoch_id]
        profile = profiles[epoch_id]
        rng = np.random.default_rng(config["random_seed"] + epoch_index * 100)
        for class_id in sorted(names):
            candidates = np.argwhere(class_map == class_id)
            population = len(candidates)
            requested = (
                config["independent_validation"]["target_for_combined_bare_quarry_stratum_per_epoch"]
                if class_id == 2
                else target
            )
            n = min(requested, population)
            if n == 0:
                continue
            selected = spatially_spread_sample(candidates, n, min_spacing, rng)
            xs, ys = xy(profile["transform"], selected[:, 0], selected[:, 1], offset="center")
            longitudes, latitudes = transform_coordinates(profile["crs"], "EPSG:4326", xs, ys)
            for sequence, (row, col, easting, northing, longitude, latitude) in enumerate(
                zip(selected[:, 0], selected[:, 1], xs, ys, longitudes, latitudes), start=1
            ):
                records.append(
                    {
                        "sample_id": f"{epoch_id}_C{class_id}_{sequence:03d}",
                        "epoch_id": epoch_id,
                        "label_year": years[epoch_id],
                        "mapped_class_id": class_id,
                        "mapped_class_name": names[class_id],
                        "sample_purpose": "primary_accuracy_and_quarry_subclass_verification" if class_id == 2 else "primary_accuracy",
                        "row": int(row),
                        "col": int(col),
                        "easting_m": round(float(easting), 3),
                        "northing_m": round(float(northing), 3),
                        "longitude": round(float(longitude), 8),
                        "latitude": round(float(latitude), 8),
                        "stratum_population_pixels_Nh": population,
                        "stratum_sample_size_nh": n,
                        "inclusion_probability": n / population,
                        "design_weight": population / n,
                        "reference_class_id_1_to_7": "",
                        "reference_class_name": "",
                        "quarry_subclass_yes_no_uncertain": "",
                        "interpretation_confidence_high_medium_low": "",
                        "reference_source_1": "",
                        "source_1_acquisition_date": "",
                        "reference_source_2": "",
                        "source_2_acquisition_date": "",
                        "interpreter_1": "",
                        "interpreter_2": "",
                        "adjudication_status": "",
                        "notes": "",
                    }
                )
    return pd.DataFrame(records)


def raster_summary(epoch_id: str, class_map: np.ndarray, max_probability: np.ndarray, entropy: np.ndarray, config: dict) -> list[dict]:
    valid = class_map > 0
    rows = []
    pixel_ha = config["analysis_grid"]["resolution_m"] ** 2 / 10000
    for item in config["primary_legend"]:
        count = int((class_map == item["id"]).sum())
        rows.append(
            {
                "epoch_id": epoch_id,
                "class_id": item["id"],
                "class_name": item["name"],
                "mapped_pixels": count,
                "unadjusted_mapped_area_ha": count * pixel_ha,
                "status": "PROVISIONAL_DIAGNOSTIC_NOT_AREA_ADJUSTED",
            }
        )
    probabilities = max_probability[valid]
    entropies = entropy[valid]
    rows.append(
        {
            "epoch_id": epoch_id,
            "class_id": 0,
            "class_name": "MODEL_DIAGNOSTIC",
            "mapped_pixels": int(valid.sum()),
            "unadjusted_mapped_area_ha": float("nan"),
            "status": json.dumps(
                {
                    "median_max_probability": float(np.nanmedian(probabilities)),
                    "p10_max_probability": float(np.nanpercentile(probabilities, 10)),
                    "percent_max_probability_at_least_0_70": float(np.mean(probabilities >= 0.70) * 100),
                    "median_normalized_entropy": float(np.nanmedian(entropies)),
                },
                sort_keys=True,
            ),
        }
    )
    return rows


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    config = load_config()
    training_predictors, reference_profile = read_predictors(config["model"]["training_epoch"])
    reference_profile.update(nodata=0)
    from rasterio.warp import transform_bounds

    bounds = rasterio.transform.array_bounds(reference_profile["height"], reference_profile["width"], reference_profile["transform"])
    bbox4326 = list(transform_bounds(reference_profile["crs"], "EPSG:4326", *bounds))
    proxy, purity, assets = build_proxy_labels(config, reference_profile, bbox4326)
    class_profile = reference_profile.copy()
    class_profile.update(dtype="uint8", count=1, nodata=0)
    float_profile = reference_profile.copy()
    float_profile.update(dtype="float32", count=1, nodata=-9999.0)
    write_raster(OUTPUTS / "worldcover_2020_2021_consensus_proxy_labels.tif", proxy, class_profile, ["proxy_landcover_class"])
    purity_out = np.where(proxy > 0, purity, -9999.0).astype(np.float32)
    write_raster(OUTPUTS / "worldcover_consensus_proxy_purity.tif", purity_out, float_profile, ["minimum_within_year_collapsed_class_purity"])
    (OUTPUTS / "worldcover_assets.json").write_text(json.dumps(assets, indent=2), encoding="utf-8")

    model, diagnostics, class_metrics, _, _ = train_and_evaluate(config, training_predictors, proxy)
    (OUTPUTS / "proxy_agreement_diagnostics.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    class_metrics.to_csv(OUTPUTS / "proxy_agreement_class_metrics.csv", index=False)
    matrix = pd.DataFrame(
        diagnostics["confusion_matrix_reference_rows_map_columns"],
        index=[f"reference_{value}" for value in diagnostics["class_order"]],
        columns=[f"mapped_{value}" for value in diagnostics["class_order"]],
    )
    matrix.to_csv(OUTPUTS / "proxy_agreement_confusion_matrix.csv")
    with gzip.open(OUTPUTS / "random_forest_development_model.pkl.gz", "wb", compresslevel=6) as handle:
        pickle.dump(model, handle, protocol=pickle.HIGHEST_PROTOCOL)

    importances = pd.DataFrame(
        {
            "predictor": config["predictors"],
            "mean_decrease_impurity_importance": model.feature_importances_,
            "status": "diagnostic_only_correlated_predictors_not_causal",
        }
    ).sort_values("mean_decrease_impurity_importance", ascending=False)
    importances.to_csv(OUTPUTS / "random_forest_feature_importance.csv", index=False)

    class_maps = {}
    profiles = {}
    summaries = []
    epoch_diagnostics = []
    for epoch in config["epochs"]:
        epoch_id = epoch["epoch_id"]
        predictors, profile = read_predictors(epoch_id)
        class_map, probabilities, max_probability, entropy = predict_epoch(model, predictors)
        class_maps[epoch_id] = class_map
        profiles[epoch_id] = profile
        class_output_profile = profile.copy()
        class_output_profile.update(dtype="uint8", count=1, nodata=0)
        probability_profile = profile.copy()
        probability_profile.update(dtype="float32", count=len(model.classes_), nodata=-9999.0)
        single_float_profile = profile.copy()
        single_float_profile.update(dtype="float32", count=1, nodata=-9999.0)
        probability_out = np.where(np.isfinite(probabilities), probabilities, -9999.0).astype(np.float32)
        max_out = np.where(np.isfinite(max_probability), max_probability, -9999.0).astype(np.float32)
        entropy_out = np.where(np.isfinite(entropy), entropy, -9999.0).astype(np.float32)
        write_raster(OUTPUTS / f"{epoch_id}_provisional_landcover.tif", class_map, class_output_profile, ["provisional_landcover_class"])
        write_raster(
            OUTPUTS / f"{epoch_id}_class_probabilities.tif",
            probability_out,
            probability_profile,
            [f"class_{value}_probability" for value in model.classes_],
        )
        write_raster(OUTPUTS / f"{epoch_id}_maximum_class_probability.tif", max_out, single_float_profile, ["maximum_class_probability"])
        write_raster(OUTPUTS / f"{epoch_id}_normalized_entropy.tif", entropy_out, single_float_profile, ["normalized_entropy"])
        epoch_rows = raster_summary(epoch_id, class_map, max_probability, entropy, config)
        summaries.extend(row for row in epoch_rows if row["class_id"] != 0)
        epoch_diagnostics.append(json.loads(next(row["status"] for row in epoch_rows if row["class_id"] == 0)) | {"epoch_id": epoch_id})

    pd.DataFrame(summaries).to_csv(OUTPUTS / "provisional_unadjusted_mapped_area_diagnostics.csv", index=False)
    pd.DataFrame(epoch_diagnostics).to_csv(OUTPUTS / "epoch_probability_diagnostics.csv", index=False)
    built_up = [
        next(row for row in summaries if row["epoch_id"] == epoch["epoch_id"] and row["class_id"] == 1)
        for epoch in config["epochs"]
    ]
    interval_checks = []
    for earlier, later in zip(built_up, built_up[1:]):
        change = later["unadjusted_mapped_area_ha"] - earlier["unadjusted_mapped_area_ha"]
        interval_checks.append(
            {
                "from_epoch": earlier["epoch_id"],
                "to_epoch": later["epoch_id"],
                "unadjusted_change_ha": change,
                "non_decreasing_check": "PASS" if change >= 0 else "FAIL",
            }
        )
    temporal_plausibility = {
        "role": "screen for model-transfer instability; not an assumption that all built-up pixels are irreversible",
        "built_up_non_decreasing_interval_check": interval_checks,
        "failed_interval_count": sum(row["non_decreasing_check"] == "FAIL" for row in interval_checks),
        "result_acceptance": "FAIL" if any(row["non_decreasing_check"] == "FAIL" for row in interval_checks) else "REVIEW",
        "interpretation": "Any failure blocks manuscript use of the provisional area trajectory and triggers epoch-matched reference labelling and retraining.",
    }
    (OUTPUTS / "temporal_plausibility_audit.json").write_text(json.dumps(temporal_plausibility, indent=2), encoding="utf-8")
    reference = make_reference_sample(config, class_maps, profiles)
    reference.to_csv(OUTPUTS / "independent_reference_sample_template.csv", index=False, quoting=csv.QUOTE_MINIMAL)

    sample_summary = (
        reference.groupby(["epoch_id", "mapped_class_id", "mapped_class_name"], as_index=False)
        .agg(
            population_pixels=("stratum_population_pixels_Nh", "first"),
            requested_or_available_samples=("sample_id", "count"),
        )
    )
    sample_summary.to_csv(OUTPUTS / "independent_reference_sample_allocation.csv", index=False)

    validation = {
        "status": "PASS_PROXY_DEVELOPMENT_FAIL_TEMPORAL_TRANSFER_FOR_MANUSCRIPT_RESULTS",
        "independent_accuracy_status": "BLOCKED_PENDING_HUMAN_REFERENCE_LABELS",
        "temporal_transfer_result_acceptance": temporal_plausibility["result_acceptance"],
        "proxy_labelled_pixels": int((proxy > 0).sum()),
        "proxy_labelled_grid_percent": float((proxy > 0).mean() * 100),
        "proxy_class_pixel_counts": {str(item["id"]): int((proxy == item["id"]).sum()) for item in config["primary_legend"]},
        "outer_development_block_overlap": diagnostics["development_test_block_overlap"],
        "reference_sample_rows": int(len(reference)),
        "reference_strata": int(len(sample_summary)),
        "output_grid": {
            "crs": str(reference_profile["crs"]),
            "width": reference_profile["width"],
            "height": reference_profile["height"],
            "transform": list(reference_profile["transform"]),
        },
    }
    (OUTPUTS / "batch2_validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")

    manifest = []
    for path in sorted(OUTPUTS.iterdir()):
        if path.is_file() and path.name != "sha256_manifest.csv":
            manifest.append({"filename": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    pd.DataFrame(manifest).to_csv(OUTPUTS / "sha256_manifest.csv", index=False)
    print(json.dumps({"diagnostics": diagnostics, "validation": validation}, indent=2))


if __name__ == "__main__":
    main()
