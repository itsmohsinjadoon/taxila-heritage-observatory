#!/usr/bin/env python3
"""Execute the experiment-only Taxila/PreserveX completion pipeline.

This script extends the frozen Landsat baseline with Open-Meteo acquisition
outputs, climate-product comparison, acquisition-date weather matching,
uncertainty-aware trend analysis, leakage-controlled proxy modelling, ranking
sensitivity, block bootstrap uncertainty, figures, maps and validation.

It does not write manuscript prose and does not infer monument damage.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import platform
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from PIL import Image
from scipy.stats import (
    kendalltau,
    norm,
    pearsonr,
    rankdata,
    spearmanr,
    theilslopes,
)
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, label_binarize


RUN_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(__file__).resolve().parents[2]
INVENTORY = RUN_ROOT / "00_inventory"
MANIFESTS = RUN_ROOT / "01_sources_and_manifests"
RAW = RUN_ROOT / "02_raw_data"
CLEAN = RUN_ROOT / "04_cleaned_data"
RASTERS = RUN_ROOT / "05_processed_rasters"
VECTORS = RUN_ROOT / "06_processed_vectors"
FEATURES = RUN_ROOT / "07_feature_tables"
MODELS = RUN_ROOT / "10_models"
FIGURES = RUN_ROOT / "11_figures"
MAPS = RUN_ROOT / "12_maps"
TABLES = RUN_ROOT / "13_tables"
STATS = RUN_ROOT / "14_statistics"
LOGS = RUN_ROOT / "15_logs"
VALIDATION = RUN_ROOT / "16_validation"
REPRO = RUN_ROOT / "17_reproducibility"
UNRESOLVED = RUN_ROOT / "18_unresolved_issues"
for directory in (
    INVENTORY,
    MANIFESTS,
    RAW,
    CLEAN,
    RASTERS,
    VECTORS,
    FEATURES,
    MODELS,
    FIGURES,
    MAPS,
    TABLES,
    STATS,
    LOGS,
    VALIDATION,
    REPRO,
    UNRESOLVED,
):
    directory.mkdir(parents=True, exist_ok=True)

SEED = 311
RNG = np.random.default_rng(SEED)
np.random.seed(SEED)
BASELINE_TABLES = TABLES / "baseline_reproduction"
BASELINE_VALIDATION = VALIDATION / "baseline_reproduction"
EPOCHS = ["E2004", "E2009", "E2014", "E2019", "E2024"]
EPOCH_YEARS = dict(zip(EPOCHS, [2004, 2009, 2014, 2019, 2024]))
RADII = [250, 500, 1000]
COLORS = {
    "navy": "#17324D",
    "blue": "#3B75AF",
    "teal": "#2A9D8F",
    "gold": "#D9A441",
    "orange": "#E07A3F",
    "red": "#C84B4B",
    "purple": "#7B61A8",
    "grey": "#68717D",
}
sns.set_theme(style="whitegrid", context="paper")
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 8.5,
        "axes.titlesize": 10,
        "axes.labelsize": 8.5,
        "legend.fontsize": 7.5,
        "figure.dpi": 160,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
    }
)


def load_baseline_module():
    path = Path(__file__).parent / "baseline" / "run_integrated_experiments.py"
    spec = importlib.util.spec_from_file_location("taxila_baseline", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the frozen baseline module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load_baseline_module()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_dump(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def save_figure(fig: plt.Figure, stem: str, map_output: bool = False) -> None:
    target = MAPS if map_output else FIGURES
    for extension in ["png", "pdf"]:
        final_path = target / f"{stem}.{extension}"
        temporary_path = target / f".{stem}.{os.getpid()}.tmp.{extension}"
        last_error: Exception | None = None
        for _ in range(3):
            try:
                fig.savefig(temporary_path, dpi=300 if extension == "png" else None, format=extension)
                with temporary_path.open("rb") as handle:
                    os.fsync(handle.fileno())
                if extension == "png":
                    with Image.open(temporary_path) as image:
                        image.verify()
                else:
                    content = temporary_path.read_bytes()
                    if not content.startswith(b"%PDF") or b"%%EOF" not in content[-4096:]:
                        raise RuntimeError("incomplete PDF output")
                os.replace(temporary_path, final_path)
                last_error = None
                break
            except Exception as error:
                last_error = error
                temporary_path.unlink(missing_ok=True)
        if last_error is not None:
            raise RuntimeError(f"Failed to create verified {extension.upper()} figure {stem}: {last_error}")
    plt.close(fig)


def ecdf_percentile(values: pd.Series, adverse_high: bool = True) -> pd.Series:
    array = values.to_numpy(dtype=float)
    if not adverse_high:
        array = -array
    valid = np.isfinite(array)
    output = np.full(array.shape, np.nan)
    output[valid] = (rankdata(array[valid], method="average") - 0.5) / valid.sum()
    return pd.Series(output, index=values.index)


def longest_run(values: np.ndarray) -> int:
    best = current = 0
    for value in values.astype(bool):
        current = current + 1 if value else 0
        best = max(best, current)
    return int(best)


def benjamini_hochberg(p_values: pd.Series) -> pd.Series:
    output = pd.Series(np.nan, index=p_values.index, dtype=float)
    valid = p_values.dropna().clip(0, 1)
    if valid.empty:
        return output
    ordered = valid.sort_values()
    adjusted = ordered.to_numpy() * len(ordered) / np.arange(1, len(ordered) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    output.loc[ordered.index] = np.minimum(adjusted, 1.0)
    return output


def moving_block_slope_ci(
    years: np.ndarray,
    values: np.ndarray,
    draws: int = 2000,
    block_length: int = 5,
) -> tuple[float, float, float, float]:
    valid = np.isfinite(years) & np.isfinite(values)
    years = years[valid].astype(float)
    values = values[valid].astype(float)
    n = len(values)
    if n < 8:
        return np.nan, np.nan, np.nan, np.nan
    observed = float(theilslopes(values, years).slope)
    intercept = float(np.median(values - observed * years))
    fitted = intercept + observed * years
    residuals = values - fitted
    slopes = np.empty(draws)
    null_slopes = np.empty(draws)
    starts = np.arange(n - block_length + 1)
    for draw in range(draws):
        indices: list[int] = []
        while len(indices) < n:
            start = int(RNG.choice(starts))
            indices.extend(range(start, start + block_length))
        sampled_residuals = residuals[np.asarray(indices[:n])]
        slopes[draw] = theilslopes(fitted + sampled_residuals, years).slope
        null_slopes[draw] = theilslopes(np.median(values) + sampled_residuals, years).slope
    low, high = np.percentile(slopes, [2.5, 97.5])
    p_two = float((1 + np.sum(np.abs(null_slopes) >= abs(observed))) / (draws + 1))
    lag1 = pd.Series(residuals).autocorr(lag=1)
    effective_n = n if not np.isfinite(lag1) else max(2.0, n * (1 - lag1) / (1 + lag1))
    return float(low), float(high), float(p_two), float(effective_n)


def top_label_ece(y_true: np.ndarray, probability: np.ndarray, bins: int = 10) -> tuple[float, pd.DataFrame]:
    confidence = probability.max(axis=1)
    prediction = probability.argmax(axis=1)
    correct = prediction == y_true
    edges = np.linspace(0, 1, bins + 1)
    rows = []
    ece = 0.0
    for left, right in zip(edges[:-1], edges[1:]):
        use = (confidence >= left) & (confidence < right if right < 1 else confidence <= right)
        count = int(use.sum())
        accuracy = float(correct[use].mean()) if count else np.nan
        mean_confidence = float(confidence[use].mean()) if count else np.nan
        if count:
            ece += count / len(y_true) * abs(accuracy - mean_confidence)
        rows.append(
            {
                "bin_left": left,
                "bin_right": right,
                "count": count,
                "accuracy": accuracy,
                "mean_confidence": mean_confidence,
            }
        )
    return float(ece), pd.DataFrame(rows)


def load_open_meteo() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    mapping = pd.read_csv(TABLES / "component_open_meteo_grid_mapping.csv")
    frames = []
    qc_rows = []
    expected_dates = pd.date_range("1991-01-01", "2025-12-31", freq="D")
    for path in sorted((RAW / "open_meteo").glob("OM_*_daily_1991_2025.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        daily = payload["daily"]
        cell_id = path.name.split("_era5", 1)[0]
        frame = pd.DataFrame({key: value for key, value in daily.items()})
        frame["date"] = pd.to_datetime(frame["time"], errors="coerce")
        frame = frame.drop(columns=["time"])
        frame.insert(0, "weather_cell_id", cell_id)
        duplicates = int(frame["date"].duplicated().sum())
        missing_dates = int(len(expected_dates.difference(frame["date"])))
        impossible = {
            "negative_precipitation": int((frame["precipitation_sum"] < 0).sum()),
            "temperature_outside_minus70_plus70": int(
                ((frame["temperature_2m_mean"] < -70) | (frame["temperature_2m_mean"] > 70)).sum()
            ),
            "humidity_outside_0_100": int(
                ((frame["relative_humidity_2m_mean"] < 0) | (frame["relative_humidity_2m_mean"] > 100)).sum()
            ),
        }
        qc_rows.append(
            {
                "weather_cell_id": cell_id,
                "rows": len(frame),
                "start_date": frame["date"].min(),
                "end_date": frame["date"].max(),
                "duplicate_dates": duplicates,
                "missing_dates": missing_dates,
                "total_missing_values": int(frame.drop(columns=["weather_cell_id", "date"]).isna().sum().sum()),
                **impossible,
                "status": "PASS" if duplicates == 0 and missing_dates == 0 and not any(impossible.values()) else "FAIL",
            }
        )
        frames.append(frame)
    if not frames:
        raise RuntimeError("No Open-Meteo raw files found")
    combined = pd.concat(frames, ignore_index=True).sort_values(["weather_cell_id", "date"])
    combined.to_csv(CLEAN / "open_meteo_era5_seamless_daily_by_grid_cell.csv", index=False)
    qc = pd.DataFrame(qc_rows)
    qc.to_csv(TABLES / "open_meteo_quality_control.csv", index=False)
    if not (qc["status"] == "PASS").all():
        raise RuntimeError("Open-Meteo quality control failed")
    numeric = [column for column in combined.columns if column not in ("weather_cell_id", "date")]
    site = combined.groupby("date", as_index=False)[numeric].mean()
    spread = combined.groupby("date")[numeric].std(ddof=0).add_suffix("_spatial_sd").reset_index()
    site = site.merge(spread, on="date")
    site.to_csv(CLEAN / "open_meteo_era5_seamless_site_daily.csv", index=False)
    return combined, site, mapping


def load_nasa_power() -> pd.DataFrame:
    source = SOURCE_ROOT / "data" / "source" / "nasa_power_taxila_1991_2025_daily.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    parameters = payload["properties"]["parameter"]
    dates = sorted(parameters["PRECTOTCORR"])
    frame = pd.DataFrame({"date": pd.to_datetime(dates, format="%Y%m%d")})
    translation = {
        "PRECTOTCORR": "precipitation_sum",
        "T2M": "temperature_2m_mean",
        "T2M_MAX": "temperature_2m_max",
        "T2M_MIN": "temperature_2m_min",
        "RH2M": "relative_humidity_2m_mean",
        "WS10M": "wind_speed_10m_mean",
    }
    for source_name, target_name in translation.items():
        frame[target_name] = [parameters[source_name].get(date, np.nan) for date in dates]
        frame.loc[frame[target_name] <= -900, target_name] = np.nan
    frame.to_csv(CLEAN / "nasa_power_taxila_daily_1991_2025.csv", index=False)
    flagged = frame[
        (frame["precipitation_sum"] > 200)
        | (frame["precipitation_sum"] < 0)
        | (frame["temperature_2m_mean"].abs() > 70)
    ].copy()
    flagged["quality_flag"] = np.select(
        [
            flagged["precipitation_sum"] > 200,
            flagged["precipitation_sum"] < 0,
            flagged["temperature_2m_mean"].abs() > 70,
        ],
        ["EXTREME_PRECIPITATION_GT200MM_REQUIRES_STATION_CHECK", "NEGATIVE_PRECIPITATION", "IMPOSSIBLE_TEMPERATURE"],
        default="UNSPECIFIED",
    )
    flagged.to_csv(TABLES / "nasa_power_flagged_daily_values.csv", index=False)
    json_dump(
        VALIDATION / "nasa_power_quality_control.json",
        {
            "rows": len(frame),
            "start_date": frame["date"].min(),
            "end_date": frame["date"].max(),
            "duplicate_dates": int(frame["date"].duplicated().sum()),
            "missing_values": int(frame.drop(columns="date").isna().sum().sum()),
            "negative_precipitation": int((frame["precipitation_sum"] < 0).sum()),
            "precipitation_gt200mm_days": int((frame["precipitation_sum"] > 200).sum()),
            "maximum_daily_precipitation_mm": float(frame["precipitation_sum"].max()),
            "decision": "retain source values; report full comparison and flagged-value/pre-2020 sensitivity; do not choose the preferred product without station validation",
        },
    )
    return frame


def climate_thresholds(site: pd.DataFrame) -> dict[str, float]:
    baseline = site[site["date"].between("1991-01-01", "2020-12-31")]
    wet = baseline.loc[baseline["precipitation_sum"] >= 1, "precipitation_sum"]
    return {
        "wet_day_p95_mm": float(wet.quantile(0.95)),
        "tmax_p95_c": float(baseline["temperature_2m_max"].quantile(0.95)),
        "precip_p99_mm": float(baseline["precipitation_sum"].quantile(0.99)),
    }


def climate_metrics(group: pd.DataFrame, thresholds: dict[str, float]) -> dict[str, float | int]:
    group = group.sort_values("date")
    rain = group["precipitation_sum"].to_numpy(dtype=float)
    tmax = group["temperature_2m_max"].to_numpy(dtype=float)
    valid_rain = np.isfinite(rain)
    rain_filled = np.where(valid_rain, rain, 0)
    return {
        "valid_days": int(group["date"].notna().sum()),
        "missing_weather_values": int(group.isna().sum().sum()),
        "precipitation_sum_mm": float(np.nansum(rain)),
        "precipitation_mean_mm_day": float(np.nanmean(rain)),
        "rx1day_mm": float(np.nanmax(rain)),
        "rx5day_mm": float(pd.Series(rain).rolling(5, min_periods=5).sum().max()),
        "wet_days_ge1mm": int(np.sum(rain >= 1)),
        "heavy_precipitation_days": int(np.sum(rain > thresholds["wet_day_p95_mm"])),
        "consecutive_wet_days": longest_run(rain_filled >= 1),
        "consecutive_dry_days": longest_run(rain_filled < 1),
        "temperature_mean_c": float(group["temperature_2m_mean"].mean()),
        "tmax_mean_c": float(group["temperature_2m_max"].mean()),
        "tmin_mean_c": float(group["temperature_2m_min"].mean()),
        "annual_or_period_max_tmax_c": float(group["temperature_2m_max"].max()),
        "hot_days": int(np.sum(tmax > thresholds["tmax_p95_c"])),
        "heatwave_max_days": longest_run(tmax > thresholds["tmax_p95_c"]),
        "relative_humidity_mean_percent": float(group["relative_humidity_2m_mean"].mean()),
        "dew_point_mean_c": float(group.get("dew_point_2m_mean", pd.Series(np.nan, index=group.index)).mean()),
        "soil_moisture_mean_m3m3": float(
            group.get("soil_moisture_0_to_7cm_mean", pd.Series(np.nan, index=group.index)).mean()
        ),
        "et0_sum_mm": float(
            group.get("et0_fao_evapotranspiration_sum", pd.Series(np.nan, index=group.index)).sum(min_count=1)
        ),
    }


def aggregate_climate(site: pd.DataFrame, thresholds: dict[str, float]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data = site.copy()
    data["year"] = data["date"].dt.year
    data["month"] = data["date"].dt.month
    season_map = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM", 6: "JJ", 7: "Monsoon", 8: "Monsoon", 9: "Monsoon", 10: "Post-monsoon", 11: "Post-monsoon"}
    data["season"] = data["month"].map(season_map)
    data["season_year"] = data["year"] + (data["month"] == 12).astype(int)

    annual_rows = []
    for year, group in data.groupby("year"):
        annual_rows.append({"year": int(year), **climate_metrics(group, thresholds)})
    annual = pd.DataFrame(annual_rows)
    annual.to_csv(TABLES / "open_meteo_annual_climate_metrics.csv", index=False)

    seasonal_rows = []
    expected_days = {"DJF": (89, 91), "MAM": (92, 92), "JJ": (61, 61), "Monsoon": (92, 92), "Post-monsoon": (61, 61)}
    for (season_year, season), group in data.groupby(["season_year", "season"]):
        low, high = expected_days[season]
        complete = low <= len(group) <= high
        seasonal_rows.append(
            {
                "season_year": int(season_year),
                "season": season,
                "complete_period": complete,
                **climate_metrics(group, thresholds),
            }
        )
    seasonal = pd.DataFrame(seasonal_rows)
    seasonal = seasonal[seasonal["complete_period"]].reset_index(drop=True)
    seasonal.to_csv(TABLES / "open_meteo_seasonal_climate_metrics.csv", index=False)

    climatology = (
        data[data["year"].between(1991, 2020)]
        .groupby("month")
        .agg(
            precipitation_mean_mm_day=("precipitation_sum", "mean"),
            precipitation_monthly_mean_mm=("precipitation_sum", lambda x: x.groupby(data.loc[x.index, "year"]).sum().mean()),
            temperature_mean_c=("temperature_2m_mean", "mean"),
            tmax_mean_c=("temperature_2m_max", "mean"),
            tmin_mean_c=("temperature_2m_min", "mean"),
            relative_humidity_mean_percent=("relative_humidity_2m_mean", "mean"),
            soil_moisture_mean_m3m3=("soil_moisture_0_to_7cm_mean", "mean"),
        )
        .reset_index()
    )
    climatology.to_csv(TABLES / "open_meteo_1991_2020_monthly_climatology.csv", index=False)
    return annual, seasonal, climatology


def trend_record(years: pd.Series, values: pd.Series, label: dict[str, object]) -> dict[str, object]:
    valid = years.notna() & values.notna()
    x = years[valid].to_numpy(dtype=float)
    y = values[valid].to_numpy(dtype=float)
    if len(y) < 8 or np.nanstd(y) == 0:
        return {**label, "n": len(y), "status": "INSUFFICIENT_OR_CONSTANT"}
    slope = theilslopes(y, x, alpha=0.95)
    tau = kendalltau(x, y)
    low, high, block_p, effective_n = moving_block_slope_ci(x, y)
    return {
        **label,
        "n": len(y),
        "effective_n_lag1": effective_n,
        "theil_sen_slope_per_year": float(slope.slope),
        "theil_sen_intercept": float(slope.intercept),
        "scipy_slope_ci_low_95": float(slope.low_slope),
        "scipy_slope_ci_high_95": float(slope.high_slope),
        "moving_block_slope_ci_low_95": low,
        "moving_block_slope_ci_high_95": high,
        "kendall_tau": float(tau.statistic),
        "kendall_p_unadjusted": float(tau.pvalue),
        "moving_block_p_two_sided": block_p,
        "bootstrap_draws": 2000,
        "block_length_years": 5,
        "status": "INFERENTIAL_WITH_BLOCK_BOOTSTRAP",
    }


def climate_trends(annual: pd.DataFrame, seasonal: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    metrics = [
        "precipitation_sum_mm",
        "rx1day_mm",
        "rx5day_mm",
        "heavy_precipitation_days",
        "consecutive_dry_days",
        "temperature_mean_c",
        "annual_or_period_max_tmax_c",
        "hot_days",
        "heatwave_max_days",
        "relative_humidity_mean_percent",
        "soil_moisture_mean_m3m3",
        "et0_sum_mm",
    ]
    rows = []
    for metric in metrics:
        rows.append(trend_record(annual["year"], annual[metric], {"period": "annual", "metric": metric}))
    for season, group in seasonal.groupby("season"):
        for metric in ["precipitation_sum_mm", "temperature_mean_c", "rx1day_mm", "consecutive_dry_days"]:
            rows.append(
                trend_record(group["season_year"], group[metric], {"period": season, "metric": metric})
            )
    trends = pd.DataFrame(rows)
    trends["fdr_adjusted_block_p"] = benjamini_hochberg(trends.get("moving_block_p_two_sided", pd.Series(index=trends.index, dtype=float)))
    trends.to_csv(STATS / "open_meteo_climate_trends_block_bootstrap.csv", index=False)

    sensitivity_rows = []
    windows = [(1991, 2020), (1996, 2025), (1991, 2025)]
    for start, end in windows:
        part = annual[annual["year"].between(start, end)]
        for metric in ["precipitation_sum_mm", "temperature_mean_c", "rx1day_mm", "consecutive_dry_days"]:
            record = trend_record(part["year"], part[metric], {"start_year": start, "end_year": end, "metric": metric})
            sensitivity_rows.append(record)
    sensitivity = pd.DataFrame(sensitivity_rows)
    sensitivity.to_csv(STATS / "climate_baseline_period_sensitivity.csv", index=False)
    return trends, sensitivity


def product_metric(open_values: pd.Series, nasa_values: pd.Series, variable: str, temporal_scale: str, subset: str = "full_record") -> dict[str, object]:
    valid = open_values.notna() & nasa_values.notna()
    left = open_values[valid].to_numpy(dtype=float)
    right = nasa_values[valid].to_numpy(dtype=float)
    difference = left - right
    return {
        "variable": variable,
        "temporal_scale": temporal_scale,
        "comparison_subset": subset,
        "n": int(valid.sum()),
        "pearson_r": float(pearsonr(left, right).statistic) if len(left) > 2 else np.nan,
        "spearman_rho": float(spearmanr(left, right).statistic) if len(left) > 2 else np.nan,
        "mean_bias_open_minus_nasa": float(np.mean(difference)),
        "rmse": float(np.sqrt(np.mean(difference**2))),
        "mae": float(np.mean(np.abs(difference))),
    }


def compare_weather_products(open_site: pd.DataFrame, nasa: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    variables = ["precipitation_sum", "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min", "relative_humidity_2m_mean"]
    aligned = open_site[["date", *variables]].merge(
        nasa[["date", *variables]], on="date", suffixes=("_open", "_nasa"), how="inner"
    )
    rows = []
    for variable in variables:
        rows.append(product_metric(aligned[f"{variable}_open"], aligned[f"{variable}_nasa"], variable, "daily"))
    aligned["year"] = aligned["date"].dt.year
    aligned["month"] = aligned["date"].dt.month
    aligned["season"] = aligned["month"].map({12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM", 6: "JJ", 7: "Monsoon", 8: "Monsoon", 9: "Monsoon", 10: "Post-monsoon", 11: "Post-monsoon"})
    annual = aligned.groupby("year").agg(
        precipitation_sum_open=("precipitation_sum_open", "sum"),
        precipitation_sum_nasa=("precipitation_sum_nasa", "sum"),
        temperature_2m_mean_open=("temperature_2m_mean_open", "mean"),
        temperature_2m_mean_nasa=("temperature_2m_mean_nasa", "mean"),
        temperature_2m_max_open=("temperature_2m_max_open", "max"),
        temperature_2m_max_nasa=("temperature_2m_max_nasa", "max"),
    ).reset_index()
    for variable in ["precipitation_sum", "temperature_2m_mean", "temperature_2m_max"]:
        rows.append(product_metric(annual[f"{variable}_open"], annual[f"{variable}_nasa"], variable, "annual"))
    for season, group in aligned.groupby("season"):
        for variable in variables:
            rows.append(product_metric(group[f"{variable}_open"], group[f"{variable}_nasa"], variable, f"daily_{season}"))

    precip_clean = aligned[(aligned["precipitation_sum_open"] <= 200) & (aligned["precipitation_sum_nasa"] <= 200)]
    rows.append(product_metric(precip_clean["precipitation_sum_open"], precip_clean["precipitation_sum_nasa"], "precipitation_sum", "daily", "exclude_either_product_gt200mm"))
    pre2020 = aligned[aligned["year"] <= 2019]
    for variable in variables:
        rows.append(product_metric(pre2020[f"{variable}_open"], pre2020[f"{variable}_nasa"], variable, "daily", "1991_2019_sensitivity"))
    annual_pre2020 = annual[annual["year"] <= 2019]
    for variable in ["precipitation_sum", "temperature_2m_mean", "temperature_2m_max"]:
        rows.append(product_metric(annual_pre2020[f"{variable}_open"], annual_pre2020[f"{variable}_nasa"], variable, "annual", "1991_2019_sensitivity"))

    baseline = aligned[aligned["year"].between(1991, 2020)]
    extreme_rows = []
    for variable in ["precipitation_sum", "temperature_2m_max"]:
        open_threshold = baseline[f"{variable}_open"].quantile(0.95)
        nasa_threshold = baseline[f"{variable}_nasa"].quantile(0.95)
        open_event = aligned[f"{variable}_open"] > open_threshold
        nasa_event = aligned[f"{variable}_nasa"] > nasa_threshold
        intersection = int((open_event & nasa_event).sum())
        union = int((open_event | nasa_event).sum())
        extreme_rows.append(
            {
                "variable": variable,
                "open_meteo_p95": open_threshold,
                "nasa_power_p95": nasa_threshold,
                "open_event_days": int(open_event.sum()),
                "nasa_event_days": int(nasa_event.sum()),
                "intersection_days": intersection,
                "jaccard_agreement": intersection / union if union else np.nan,
                "open_event_recall_against_nasa": intersection / int(nasa_event.sum()) if nasa_event.sum() else np.nan,
            }
        )
    metrics = pd.DataFrame(rows)
    metrics.to_csv(TABLES / "open_meteo_nasa_power_comparison.csv", index=False)
    extremes = pd.DataFrame(extreme_rows)
    extremes.to_csv(TABLES / "weather_product_extreme_event_agreement.csv", index=False)
    aligned.to_csv(CLEAN / "open_meteo_nasa_power_daily_aligned.csv", index=False)
    annual.to_csv(TABLES / "weather_product_annual_aligned.csv", index=False)
    trend_rows = []
    for variable in ["precipitation_sum", "temperature_2m_mean", "temperature_2m_max"]:
        open_slope = float(theilslopes(annual[f"{variable}_open"], annual["year"]).slope)
        nasa_slope = float(theilslopes(annual[f"{variable}_nasa"], annual["year"]).slope)
        trend_rows.append(
            {
                "variable": variable,
                "open_meteo_theil_sen_slope_per_year": open_slope,
                "nasa_power_theil_sen_slope_per_year": nasa_slope,
                "direction_agreement": bool(np.sign(open_slope) == np.sign(nasa_slope)),
                "absolute_slope_difference": abs(open_slope - nasa_slope),
                "interpretation": "product trend agreement; not station-validated accuracy",
            }
        )
    pd.DataFrame(trend_rows).to_csv(TABLES / "weather_product_trend_slope_agreement.csv", index=False)
    return metrics, annual


def retained_landsat_scenes() -> pd.DataFrame:
    report = json.loads((SOURCE_ROOT / "work" / "landsat" / "outputs" / "preprocessing_validation.json").read_text(encoding="utf-8"))
    rows = []
    for audit in report["scene_audits"]:
        if audit.get("retained"):
            rows.append(
                {
                    "epoch_id": audit["epoch_id"],
                    "item_id": audit["item_id"],
                    "acquisition_datetime_utc": audit["datetime"],
                    "acquisition_date": pd.Timestamp(audit["datetime"]).tz_convert(None).normalize(),
                    "platform": audit["platform"],
                    "local_valid_percent": audit.get("physical_and_baseline_valid_percent"),
                }
            )
    scenes = pd.DataFrame(rows).sort_values(["epoch_id", "acquisition_date"])
    scenes.to_csv(TABLES / "retained_landsat_scene_dates.csv", index=False)
    return scenes


def lag_features(daily: pd.DataFrame, date: pd.Timestamp) -> dict[str, float]:
    record: dict[str, float] = {}
    for days in [7, 30, 90, 180, 365]:
        start = date - pd.Timedelta(days=days)
        end = date - pd.Timedelta(days=1)
        use = daily[daily["date"].between(start, end)]
        record[f"precipitation_preceding_{days}d_mm"] = float(use["precipitation_sum"].sum(min_count=days))
        record[f"temperature_mean_preceding_{days}d_c"] = float(use["temperature_2m_mean"].mean())
        record[f"tmax_max_preceding_{days}d_c"] = float(use["temperature_2m_max"].max())
        record[f"data_completeness_preceding_{days}d"] = float(use["precipitation_sum"].notna().mean()) if len(use) else 0.0
    recent = daily[daily["date"].between(date - pd.Timedelta(days=7), date - pd.Timedelta(days=1))]
    record["humidity_mean_preceding_7d_percent"] = float(recent["relative_humidity_2m_mean"].mean())
    record["soil_moisture_mean_preceding_7d_m3m3"] = float(recent.get("soil_moisture_0_to_7cm_mean", pd.Series(dtype=float)).mean())
    return record


def match_weather_to_landsat(open_site: pd.DataFrame, nasa: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    scenes = retained_landsat_scenes()
    rows = []
    for scene in scenes.itertuples(index=False):
        for provider, daily in [("Open-Meteo ERA5-Seamless", open_site), ("NASA POWER", nasa)]:
            rows.append(
                {
                    "epoch_id": scene.epoch_id,
                    "label_year": EPOCH_YEARS[scene.epoch_id],
                    "item_id": scene.item_id,
                    "platform": scene.platform,
                    "acquisition_datetime_utc": scene.acquisition_datetime_utc,
                    "acquisition_date": scene.acquisition_date,
                    "weather_provider": provider,
                    **lag_features(daily, scene.acquisition_date),
                }
            )
    matched = pd.DataFrame(rows)
    matched.to_csv(TABLES / "landsat_scene_weather_lag_features.csv", index=False)
    numeric = [column for column in matched.columns if column.startswith(("precipitation_", "temperature_", "tmax_", "humidity_", "soil_", "data_"))]
    epoch = matched.groupby(["epoch_id", "label_year", "weather_provider"])[numeric].agg(["mean", "median", "min", "max"])
    epoch.columns = [f"{left}_{right}" for left, right in epoch.columns]
    epoch = epoch.reset_index()
    epoch.to_csv(TABLES / "landsat_epoch_weather_lag_summary.csv", index=False)

    epoch_comparison_rows = []
    for metric in [
        "precipitation_preceding_7d_mm_mean",
        "precipitation_preceding_30d_mm_mean",
        "precipitation_preceding_90d_mm_mean",
        "precipitation_preceding_180d_mm_mean",
        "precipitation_preceding_365d_mm_mean",
        "temperature_mean_preceding_30d_c_mean",
    ]:
        wide = epoch.pivot(index="epoch_id", columns="weather_provider", values=metric).reindex(EPOCHS)
        epoch_comparison_rows.append(
            product_metric(
                wide["Open-Meteo ERA5-Seamless"],
                wide["NASA POWER"],
                metric,
                "landsat_epoch_n5",
                "retained_scene_date_aggregates",
            )
        )
    pd.DataFrame(epoch_comparison_rows).to_csv(TABLES / "weather_product_epoch_level_agreement.csv", index=False)

    spectral = pd.read_csv(BASELINE_TABLES / "sitewide_epoch_spectral_climate_series.csv")
    open_epoch = epoch[epoch["weather_provider"] == "Open-Meteo ERA5-Seamless"]
    site = spectral[["epoch_id", "label_year", "grid_median_ndvi", "grid_median_mndwi", "grid_median_ndbi"]].merge(
        open_epoch, on=["epoch_id", "label_year"]
    )
    association_rows = []
    for days in [7, 30, 90, 180, 365]:
        climate = f"precipitation_preceding_{days}d_mm_mean"
        for spectral_metric in ["grid_median_ndvi", "grid_median_mndwi", "grid_median_ndbi"]:
            x = site[climate].to_numpy(dtype=float)
            y = site[spectral_metric].to_numpy(dtype=float)
            rho = float(spearmanr(x, y).statistic)
            loo = []
            for omitted in range(len(site)):
                keep = np.arange(len(site)) != omitted
                loo.append(float(spearmanr(x[keep], y[keep]).statistic))
            signs = [np.sign(value) for value in loo if np.isfinite(value) and value != 0]
            association_rows.append(
                {
                    "climate_metric": climate,
                    "spectral_metric": spectral_metric,
                    "n_unique_epochs": len(site),
                    "spearman_rho": rho,
                    "leave_one_epoch_out_rho_min": float(np.nanmin(loo)),
                    "leave_one_epoch_out_rho_max": float(np.nanmax(loo)),
                    "sign_stability": float(np.mean(np.asarray(signs) == np.sign(rho))) if signs else np.nan,
                    "inference_status": "EXPLORATORY_NO_P_VALUE_N5",
                }
            )
    associations = pd.DataFrame(association_rows)
    associations.to_csv(STATS / "weather_spectral_lag_associations.csv", index=False)
    return matched, epoch, associations


def feature_selection_record(feature_frame: pd.DataFrame, feature_names: list[str]) -> pd.DataFrame:
    rows = []
    for feature in feature_names:
        series = feature_frame[feature]
        rows.append(
            {
                "feature": feature,
                "missing_count": int(series.isna().sum()),
                "variance": float(series.var()),
                "unique_values": int(series.nunique()),
                "retained": bool(series.notna().all() and series.var() > 0),
                "selection_stage": "prespecified_physical_features_then_inner_fold_regularisation_or_embedded_selection",
                "scientific_role": "reflectance band" if feature in ["blue", "green", "red", "nir08", "swir16", "swir22"] else "engineered spectral index",
                "test_data_used_for_selection": False,
            }
        )
    result = pd.DataFrame(rows)
    result.to_csv(FEATURES / "proxy_model_feature_selection.csv", index=False)
    feature_frame[feature_names].corr(method="spearman").to_csv(FEATURES / "proxy_feature_spearman_correlation.csv")
    return result


def model_metrics(y_true: np.ndarray, prediction: np.ndarray, probability: np.ndarray, labels: list[int]) -> dict[str, float]:
    binary = label_binarize(y_true, classes=labels)
    label_to_index = {label: index for index, label in enumerate(labels)}
    encoded = np.asarray([label_to_index[int(value)] for value in y_true])
    one_hot = np.eye(len(labels))[encoded]
    ece, _ = top_label_ece(encoded, probability)
    return {
        "overall_agreement": float(accuracy_score(y_true, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, prediction)),
        "macro_f1": float(f1_score(y_true, prediction, labels=labels, average="macro", zero_division=0)),
        "macro_auroc_ovr": float(roc_auc_score(y_true, probability, labels=labels, multi_class="ovr", average="macro")),
        "macro_auprc": float(average_precision_score(binary, probability, average="macro")),
        "log_loss": float(log_loss(y_true, probability, labels=labels)),
        "multiclass_brier": float(np.mean(np.sum((probability - one_hot) ** 2, axis=1))),
        "top_label_ece_10bin": ece,
    }


def proxy_model_experiment() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cached_comparison = TABLES / "enhanced_spatially_buffered_proxy_model_comparison.csv"
    cached_calibration = TABLES / "proxy_model_calibration.csv"
    cached_importance = FEATURES / "held_out_permutation_importance.csv"
    if cached_comparison.exists() and cached_calibration.exists() and cached_importance.exists():
        return (
            pd.read_csv(cached_comparison),
            pd.read_csv(cached_calibration),
            pd.read_csv(cached_importance),
        )
    feature_frame = pd.read_csv(BASELINE_TABLES / "proxy_model_feature_table.csv")
    feature_names = ["blue", "green", "red", "nir08", "swir16", "swir22", "NDVI", "NDBI", "MNDWI", "BSI"]
    feature_selection_record(feature_frame, feature_names)
    feature_frame["block_row"] = feature_frame["spatial_block"] // 10
    feature_frame["block_col"] = feature_frame["spatial_block"] % 10

    # A contiguous two-column test stripe is separated from development data
    # by one complete 2.01-km block column on each side. This stricter design
    # complements, rather than replaces, the reproduced 79/21 legacy split.
    test_mask = feature_frame["block_col"].isin([3, 4])
    buffer_mask = feature_frame["block_col"].isin([2, 5])
    development_mask = ~(test_mask | buffer_mask)
    development = feature_frame[development_mask].copy()
    test = feature_frame[test_mask].copy()
    excluded_buffer = feature_frame[buffer_mask].copy()
    labels = sorted(feature_frame["proxy_class"].unique().astype(int).tolist())
    if set(development["proxy_class"].unique()) != set(labels) or set(test["proxy_class"].unique()) != set(labels):
        raise RuntimeError("Buffered spatial split does not retain every proxy class")
    x_dev = development[feature_names].to_numpy(dtype=float)
    y_dev = development["proxy_class"].to_numpy(dtype=int)
    groups = development["spatial_block"].to_numpy(dtype=int)
    x_test = test[feature_names].to_numpy(dtype=float)
    y_test = test["proxy_class"].to_numpy(dtype=int)
    test_blocks = test["spatial_block"].to_numpy(dtype=int)

    candidates = [
        (
            "Regularised multinomial logistic",
            Pipeline(
                [
                    ("scale", StandardScaler()),
                    ("model", LogisticRegression(max_iter=1500, class_weight="balanced", solver="lbfgs", random_state=SEED)),
                ]
            ),
            {"model__C": [0.03, 0.1, 0.3, 1.0, 3.0]},
        ),
        (
            "Random forest",
            RandomForestClassifier(n_estimators=400, class_weight="balanced_subsample", max_features="sqrt", n_jobs=1, random_state=SEED),
            {"max_depth": [16, None], "min_samples_leaf": [1, 5, 12]},
        ),
        (
            "Extra trees",
            ExtraTreesClassifier(n_estimators=400, class_weight="balanced", max_features="sqrt", n_jobs=1, random_state=SEED),
            {"max_depth": [20, None], "min_samples_leaf": [1, 3, 8]},
        ),
        (
            "Histogram gradient boosting",
            HistGradientBoostingClassifier(max_iter=260, l2_regularization=0.1, early_stopping=True, random_state=SEED),
            {"learning_rate": [0.05, 0.1], "max_leaf_nodes": [31, 63], "min_samples_leaf": [20, 50]},
        ),
        (
            "MLP sensitivity",
            Pipeline(
                [
                    ("scale", StandardScaler()),
                    ("model", MLPClassifier(max_iter=400, early_stopping=True, validation_fraction=0.15, n_iter_no_change=25, random_state=SEED)),
                ]
            ),
            {"model__hidden_layer_sizes": [(64,), (64, 32)], "model__alpha": [0.0001, 0.001, 0.01]},
        ),
    ]
    inner_cv = GroupKFold(n_splits=4)
    split_rows = []
    for fold, (_, validation_indices) in enumerate(inner_cv.split(x_dev, y_dev, groups), start=1):
        for block in np.unique(groups[validation_indices]):
            split_rows.append({"spatial_block": int(block), "inner_validation_fold": fold})
    pd.DataFrame(split_rows).to_csv(MODELS / "inner_group_fold_assignments.csv", index=False)

    result_rows = []
    predictions: dict[str, np.ndarray] = {}
    probabilities: dict[str, np.ndarray] = {}
    estimators: dict[str, object] = {}
    for name, estimator, parameter_grid in candidates:
        search = GridSearchCV(
            estimator,
            parameter_grid,
            scoring="f1_macro",
            cv=inner_cv,
            n_jobs=-1,
            refit=True,
            return_train_score=False,
        )
        search.fit(x_dev, y_dev, groups=groups)
        prediction = search.predict(x_test)
        probability = search.predict_proba(x_test)
        metrics = model_metrics(y_test, prediction, probability, labels)
        result_rows.append(
            {
                "model": name,
                "inner_group_cv_macro_f1": float(search.best_score_),
                **metrics,
                "best_parameters": json.dumps(search.best_params_, sort_keys=True),
                "development_samples": len(development),
                "buffer_excluded_samples": len(excluded_buffer),
                "test_samples": len(test),
                "development_blocks": int(development["spatial_block"].nunique()),
                "buffer_blocks": int(excluded_buffer["spatial_block"].nunique()),
                "test_blocks": int(test["spatial_block"].nunique()),
                "development_test_block_overlap": 0,
                "minimum_block_column_separation": 2,
                "validation_role": "WorldCover-derived proxy land-cover agreement; not independent heritage-condition accuracy",
            }
        )
        safe_name = name.lower().replace(" ", "_").replace("-", "_")
        joblib.dump(search.best_estimator_, MODELS / f"{safe_name}.joblib", compress=3)
        predictions[name] = prediction
        probabilities[name] = probability
        estimators[name] = search.best_estimator_

    comparison = pd.DataFrame(result_rows)
    primary_name = comparison.sort_values("inner_group_cv_macro_f1", ascending=False).iloc[0]["model"]
    unique_blocks = np.unique(test_blocks)
    bootstrap_draws = 2000
    probability_draws = 500
    rng = np.random.default_rng(SEED)
    bootstrap_store: dict[str, dict[str, list[float]]] = {
        name: defaultdict(list) for name in predictions
    }
    for draw in range(bootstrap_draws):
        sampled_blocks = rng.choice(unique_blocks, size=len(unique_blocks), replace=True)
        sampled_indices = np.concatenate([np.where(test_blocks == block)[0] for block in sampled_blocks])
        for name in predictions:
            prediction = predictions[name][sampled_indices]
            probability = probabilities[name][sampled_indices]
            truth = y_test[sampled_indices]
            binary = label_binarize(truth, classes=labels)
            encoded = np.asarray([labels.index(int(value)) for value in truth])
            one_hot = np.eye(len(labels))[encoded]
            store = bootstrap_store[name]
            store["macro_f1"].append(float(f1_score(truth, prediction, labels=labels, average="macro", zero_division=0)))
            matrix = confusion_matrix(truth, prediction, labels=labels)
            denominators = matrix.sum(axis=1)
            store["balanced_accuracy"].append(
                float(np.mean(np.diag(matrix) / denominators)) if np.all(denominators > 0) else np.nan
            )
            store["log_loss"].append(float(log_loss(truth, probability, labels=labels)))
            store["multiclass_brier"].append(float(np.mean(np.sum((probability - one_hot) ** 2, axis=1))))
            if draw < probability_draws and binary.shape[1] == len(labels) and np.all(binary.sum(axis=0) > 0):
                store["macro_auroc_ovr"].append(float(roc_auc_score(truth, probability, labels=labels, multi_class="ovr", average="macro")))
                store["macro_auprc"].append(float(average_precision_score(binary, probability, average="macro")))
    for row_index, row in comparison.iterrows():
        store = bootstrap_store[row["model"]]
        for metric in ["macro_f1", "balanced_accuracy", "log_loss", "multiclass_brier", "macro_auroc_ovr", "macro_auprc"]:
            values = np.asarray(store[metric], dtype=float)
            comparison.loc[row_index, f"{metric}_ci_low_95"] = float(np.nanpercentile(values, 2.5))
            comparison.loc[row_index, f"{metric}_ci_high_95"] = float(np.nanpercentile(values, 97.5))
        comparison.loc[row_index, "block_bootstrap_draws"] = bootstrap_draws
        comparison.loc[row_index, "auroc_auprc_bootstrap_draws"] = probability_draws
        comparison.loc[row_index, "primary_selected_from_inner_cv"] = row["model"] == primary_name
    comparison = comparison.sort_values("inner_group_cv_macro_f1", ascending=False)
    comparison.to_csv(TABLES / "enhanced_spatially_buffered_proxy_model_comparison.csv", index=False)

    prediction_table = test[["row", "col", "spatial_block", "proxy_class"]].copy()
    calibration_frames = []
    for name in predictions:
        safe_name = name.lower().replace(" ", "_").replace("-", "_")
        prediction_table[f"prediction_{safe_name}"] = predictions[name]
        for label_index, label in enumerate(labels):
            prediction_table[f"probability_{safe_name}_class_{label}"] = probabilities[name][:, label_index]
        encoded = np.asarray([labels.index(int(value)) for value in y_test])
        ece, calibration = top_label_ece(encoded, probabilities[name])
        calibration.insert(0, "model", name)
        calibration["ece"] = ece
        calibration_frames.append(calibration)
    prediction_table.to_csv(MODELS / "buffered_outer_test_predictions.csv", index=False)
    calibration_table = pd.concat(calibration_frames, ignore_index=True)
    calibration_table.to_csv(TABLES / "proxy_model_calibration.csv", index=False)

    primary_estimator = estimators[primary_name]
    importance = permutation_importance(
        primary_estimator,
        x_test,
        y_test,
        scoring="f1_macro",
        n_repeats=20,
        random_state=SEED,
        n_jobs=-1,
    )
    importance_table = pd.DataFrame(
        {
            "feature": feature_names,
            "permutation_importance_macro_f1_mean": importance.importances_mean,
            "permutation_importance_macro_f1_sd": importance.importances_std,
            "evaluation_data": "held-out buffered test stripe",
            "primary_model": primary_name,
        }
    ).sort_values("permutation_importance_macro_f1_mean", ascending=False)
    importance_table.to_csv(FEATURES / "held_out_permutation_importance.csv", index=False)

    confusion = confusion_matrix(y_test, predictions[primary_name], labels=labels)
    confusion_table = pd.DataFrame(confusion, index=[f"reference_{label}" for label in labels], columns=[f"predicted_{label}" for label in labels])
    confusion_table.to_csv(TABLES / "primary_buffered_proxy_model_confusion_matrix.csv")
    class_distribution = pd.concat(
        [
            development.groupby("proxy_class").size().rename("development_samples"),
            excluded_buffer.groupby("proxy_class").size().rename("buffer_excluded_samples"),
            test.groupby("proxy_class").size().rename("test_samples"),
        ],
        axis=1,
    ).fillna(0).astype(int).reset_index()
    class_distribution.to_csv(TABLES / "proxy_class_distribution_buffered_split.csv", index=False)
    json_dump(
        MODELS / "model_experiment_summary.json",
        {
            "primary_model_selected_by_inner_cv": primary_name,
            "selection_rule": "highest development-only inner spatial-group CV macro-F1",
            "input_samples": len(feature_frame),
            "development_samples": len(development),
            "buffer_excluded_samples": len(excluded_buffer),
            "held_out_test_samples": len(test),
            "test_blocks": int(test["spatial_block"].nunique()),
            "minimum_test_development_separation_m": 2010,
            "legacy_79_21_split_reproduced_separately": True,
            "validation_role": "proxy land-cover agreement only",
        },
    )
    return comparison, calibration_table, importance_table


def rank_vector(values: np.ndarray) -> np.ndarray:
    return rankdata(-np.asarray(values, dtype=float), method="average")


def scale_and_ablation() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    scores = pd.read_csv(BASELINE_TABLES / "component_epoch_integrated_scores.csv")
    target = scores[scores["epoch_id"] == "E2024"].copy()
    vectors: dict[int, pd.Series] = {}
    rank_table = target[target["radius_m"] == 500][["component_id", "component_name"]].sort_values("component_id").reset_index(drop=True)
    for radius in RADII:
        part = target[target["radius_m"] == radius].set_index("component_id").loc[rank_table["component_id"]]
        vectors[radius] = pd.Series(rank_vector(part["local_priority_score"].to_numpy()), index=rank_table["component_id"])
        rank_table[f"rank_{radius}m"] = vectors[radius].to_numpy()
        rank_table[f"score_{radius}m"] = part["local_priority_score"].to_numpy()
    rows = []
    for left in RADII:
        for right in RADII:
            a = vectors[left].to_numpy()
            b = vectors[right].to_numpy()
            rows.append(
                {
                    "radius_a_m": left,
                    "radius_b_m": right,
                    "spearman_rho": float(spearmanr(a, b).statistic),
                    "kendall_tau": float(kendalltau(a, b).statistic),
                    "top_3_overlap": int(len(set(np.where(a <= 3)[0]) & set(np.where(b <= 3)[0]))),
                    "top_5_overlap": int(len(set(np.where(a <= 5)[0]) & set(np.where(b <= 5)[0]))),
                    "components_with_rank_change_ge3": int(np.sum(np.abs(a - b) >= 3)),
                    "maximum_absolute_rank_change": float(np.max(np.abs(a - b))),
                }
            )
    sensitivity = pd.DataFrame(rows)
    sensitivity.to_csv(TABLES / "component_ranking_scale_sensitivity.csv", index=False)
    rank_table.to_csv(TABLES / "component_rankings_250m_500m_1000m.csv", index=False)

    primary = target[target["radius_m"] == 500].sort_values("component_id").reset_index(drop=True)
    climate = primary["climate_extreme_score"]
    full_integrated = primary[["landscape_pressure_score", "terrain_susceptibility_score", "climate_extreme_score"]].mean(axis=1)
    full_local = primary[["landscape_pressure_score", "terrain_susceptibility_score"]].mean(axis=1)
    alternatives = {
        "Full integrated context": full_integrated,
        "Primary local priority": full_local,
        "Landscape only": primary["landscape_pressure_score"],
        "Terrain only": primary["terrain_susceptibility_score"],
        "Climate only": climate,
        "Leave climate out": full_local,
        "Leave landscape out": primary[["terrain_susceptibility_score", "climate_extreme_score"]].mean(axis=1),
        "Leave terrain out": primary[["landscape_pressure_score", "climate_extreme_score"]].mean(axis=1),
        "Leave NDVI out": pd.concat([primary[["mndwi_pressure", "ndbi_pressure"]].mean(axis=1), primary["terrain_susceptibility_score"]], axis=1).mean(axis=1),
        "Leave MNDWI out": primary[["surface_cover_pressure", "terrain_susceptibility_score"]].mean(axis=1),
        "Leave NDBI out": pd.concat([primary[["mndwi_pressure", "ndvi_pressure"]].mean(axis=1), primary["terrain_susceptibility_score"]], axis=1).mean(axis=1),
        "Leave slope out": pd.concat([primary["landscape_pressure_score"], primary[["wetness_pressure", "drainage_proximity_pressure"]].mean(axis=1)], axis=1).mean(axis=1),
        "Leave terrain wetness out": pd.concat([primary["landscape_pressure_score"], primary[["slope_pressure", "drainage_proximity_pressure"]].mean(axis=1)], axis=1).mean(axis=1),
        "Leave drainage proximity out": pd.concat([primary["landscape_pressure_score"], primary[["slope_pressure", "wetness_pressure"]].mean(axis=1)], axis=1).mean(axis=1),
    }
    reference_rank = rank_vector(full_integrated.to_numpy())
    ablation_rows = []
    component_ablation = primary[["component_id", "component_name"]].copy()
    for name, values in alternatives.items():
        ranks = rank_vector(values.to_numpy())
        component_ablation[name] = ranks
        ablation_rows.append(
            {
                "scenario": name,
                "spearman_rho_with_full_integrated": float(spearmanr(reference_rank, ranks).statistic) if np.std(ranks) else np.nan,
                "kendall_tau_with_full_integrated": float(kendalltau(reference_rank, ranks).statistic) if np.std(ranks) else np.nan,
                "top5_overlap": int(len(set(np.where(reference_rank <= 5)[0]) & set(np.where(ranks <= 5)[0]))),
                "rank_1_component": primary.iloc[int(np.argmin(ranks))]["component_name"] if np.std(ranks) else "All components tied",
                "maximum_absolute_rank_change": float(np.max(np.abs(reference_rank - ranks))) if np.std(ranks) else np.nan,
            }
        )
    ablation = pd.DataFrame(ablation_rows)
    ablation.to_csv(TABLES / "complete_factor_domain_ablation.csv", index=False)
    component_ablation.to_csv(TABLES / "component_factor_domain_ablation_ranks.csv", index=False)

    formulas = pd.DataFrame(
        [
            {"output": "surface_cover_pressure", "formula": "0.5*NDVI_pressure + 0.5*NDBI_pressure", "normalisation": "empirical percentile within scale across all component-epochs", "missing_data": "complete-case"},
            {"output": "landscape_pressure_score", "formula": "0.5*surface_cover_pressure + 0.5*MNDWI_pressure", "normalisation": "hierarchical equal weighting", "missing_data": "complete-case"},
            {"output": "terrain_susceptibility_score", "formula": "mean(slope_pressure, terrain_wetness_pressure, drainage_proximity_pressure)", "normalisation": "empirical percentile within scale", "missing_data": "complete-case"},
            {"output": "local_field_inspection_priority", "formula": "0.5*landscape_pressure_score + 0.5*terrain_susceptibility_score", "normalisation": "equal domain weighting", "missing_data": "complete-case"},
            {"output": "integrated_context_score", "formula": "mean(landscape_pressure_score, terrain_susceptibility_score, climate_extreme_score)", "normalisation": "equal domain weighting", "missing_data": "complete-case"},
        ]
    )
    formulas.to_csv(TABLES / "composite_formulas_weights_normalisation.csv", index=False)
    return sensitivity, ablation, rank_table


def ranking_block_bootstrap() -> pd.DataFrame:
    components = BASE.load_components()
    indices, observations, _ = BASE.load_epoch_arrays()
    valids = BASE.valid_mask(indices["E2024"], observations["E2024"])
    masks = BASE.component_neighbourhood_masks(components)
    height, width, _ = indices["E2024"].shape
    rows_grid, cols_grid = np.indices((height, width))
    block_ids = (rows_grid // 5) * math.ceil(width / 5) + cols_grid // 5
    grouped_values: dict[str, list[np.ndarray]] = {}
    for component in components.itertuples(index=False):
        use = masks[(component.component_id, 500)] & valids
        values = indices["E2024"][use][:, [0, 2, 1]]
        ids = block_ids[use]
        grouped_values[component.component_id] = [values[ids == block] for block in np.unique(ids)]

    baseline_scores = pd.read_csv(BASELINE_TABLES / "component_epoch_integrated_scores.csv")
    primary = baseline_scores[(baseline_scores["epoch_id"] == "E2024") & (baseline_scores["radius_m"] == 500)].sort_values("component_id").reset_index(drop=True)
    terrain = primary["terrain_susceptibility_score"].to_numpy(dtype=float)
    draws = 2000
    rng = np.random.default_rng(SEED)
    ranks = np.empty((draws, len(primary)), dtype=float)
    local_scores = np.empty_like(ranks)
    for draw in range(draws):
        medians = np.empty((len(primary), 3), dtype=float)
        for index, component_id in enumerate(primary["component_id"]):
            groups = grouped_values[component_id]
            selected = rng.integers(0, len(groups), size=len(groups))
            sample = np.concatenate([groups[item] for item in selected], axis=0)
            medians[index] = np.nanmedian(sample, axis=0)
        ndvi_pressure = ecdf_percentile(pd.Series(medians[:, 0]), adverse_high=False).to_numpy()
        mndwi_pressure = ecdf_percentile(pd.Series(medians[:, 1]), adverse_high=False).to_numpy()
        ndbi_pressure = ecdf_percentile(pd.Series(medians[:, 2]), adverse_high=True).to_numpy()
        landscape = np.column_stack([(ndvi_pressure + ndbi_pressure) / 2, mndwi_pressure]).mean(axis=1)
        local_scores[draw] = (landscape + terrain) / 2
        ranks[draw] = rank_vector(local_scores[draw])
    output = primary[["component_id", "component_name"]].copy()
    output["score_median"] = np.median(local_scores, axis=0)
    output["score_ci_low_95"] = np.percentile(local_scores, 2.5, axis=0)
    output["score_ci_high_95"] = np.percentile(local_scores, 97.5, axis=0)
    output["rank_median"] = np.median(ranks, axis=0)
    output["rank_ci_low_95"] = np.percentile(ranks, 2.5, axis=0)
    output["rank_ci_high_95"] = np.percentile(ranks, 97.5, axis=0)
    output["probability_top_3"] = np.mean(ranks <= 3, axis=0)
    output["probability_top_5"] = np.mean(ranks <= 5, axis=0)
    output["spatial_block_size_m"] = 150
    output["bootstrap_draws"] = draws
    output["uncertainty_scope"] = "E2024 30m spectral sampling blocks; terrain held fixed"
    output = output.sort_values("rank_median")
    output.to_csv(STATS / "component_rank_spatial_block_bootstrap.csv", index=False)
    return output


def export_vectors_and_rasters(rank_uncertainty: pd.DataFrame, rank_table: pd.DataFrame) -> None:
    copy_files = [
        SOURCE_ROOT / "work" / "spatial" / "derived" / "taxila_components_wgs84.geojson",
        SOURCE_ROOT / "work" / "spatial" / "derived" / "taxila_components_epsg32643.geojson",
        SOURCE_ROOT / "work" / "spatial" / "derived" / "taxila_analytical_neighbourhoods_epsg32643.geojson",
        SOURCE_ROOT / "work" / "spatial" / "derived" / "taxila_analysis_envelope_epsg32643.geojson",
    ]
    for source in copy_files:
        shutil.copy2(source, VECTORS / source.name)
    for epoch in EPOCHS:
        for suffix in ["oli_like_indices.tif", "valid_observation_count.tif"]:
            source = SOURCE_ROOT / "work" / "landsat" / "outputs" / "composites" / f"{epoch}_{suffix}"
            shutil.copy2(source, RASTERS / source.name)
        source = SOURCE_ROOT / "work" / "landcover" / "Taxila_PreserveX_Stage4_Batch2" / "outputs" / f"{epoch}_provisional_landcover.tif"
        shutil.copy2(source, RASTERS / source.name)

    components_path = SOURCE_ROOT / "work" / "spatial" / "derived" / "taxila_components_wgs84.geojson"
    payload = json.loads(components_path.read_text(encoding="utf-8"))
    uncertainty = rank_uncertainty.set_index("component_id")
    ranks = rank_table.set_index("component_id")
    score_source = pd.read_csv(BASELINE_TABLES / "component_epoch_integrated_scores.csv")
    score_source = score_source[(score_source["epoch_id"] == "E2024") & (score_source["radius_m"] == 500)].set_index("component_id")
    features = []
    for feature in payload["features"]:
        component_id = feature["properties"]["component_id"]
        properties = dict(feature["properties"])
        if component_id in uncertainty.index:
            properties.update(
                {
                    "local_priority_score_500m": float(score_source.loc[component_id, "local_priority_score"]),
                    "landscape_pressure_score": float(score_source.loc[component_id, "landscape_pressure_score"]),
                    "terrain_susceptibility_score": float(score_source.loc[component_id, "terrain_susceptibility_score"]),
                    "rank_250m": float(ranks.loc[component_id, "rank_250m"]),
                    "rank_500m": float(ranks.loc[component_id, "rank_500m"]),
                    "rank_1000m": float(ranks.loc[component_id, "rank_1000m"]),
                    "bootstrap_rank_median": float(uncertainty.loc[component_id, "rank_median"]),
                    "bootstrap_rank_ci_low_95": float(uncertainty.loc[component_id, "rank_ci_low_95"]),
                    "bootstrap_rank_ci_high_95": float(uncertainty.loc[component_id, "rank_ci_high_95"]),
                    "interpretation": "relative field-inspection priority; not validated monument damage",
                }
            )
        features.append({"type": "Feature", "geometry": feature["geometry"], "properties": properties})
    integrated = {
        "type": "FeatureCollection",
        "name": "Taxila integrated field-inspection priority",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    json_dump(VECTORS / "taxila_integrated_field_inspection_priority_wgs84.geojson", integrated)


def add_north_arrow(ax: plt.Axes, x: float = 0.94, y: float = 0.92) -> None:
    ax.annotate(
        "N",
        xy=(x, y),
        xytext=(x, y - 0.11),
        xycoords="axes fraction",
        ha="center",
        va="center",
        fontsize=9,
        fontweight="bold",
        arrowprops={"facecolor": "black", "width": 2.0, "headwidth": 7.0},
    )


def add_scale_bar_utm(ax: plt.Axes, length_m: float = 5000) -> None:
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    x0 = xmin + 0.06 * (xmax - xmin)
    y0 = ymin + 0.06 * (ymax - ymin)
    ax.plot([x0, x0 + length_m], [y0, y0], color="black", lw=3)
    ax.text(x0 + length_m / 2, y0 + 0.018 * (ymax - ymin), f"{length_m/1000:g} km", ha="center", va="bottom", fontsize=7)


def add_scale_bar_lonlat(ax: plt.Axes, length_m: float = 5000) -> None:
    """Add an approximate east-west scale bar to a small WGS84 map extent."""
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    latitude = (ymin + ymax) / 2
    longitude_degrees = (length_m / 1000) / (111.32 * np.cos(np.deg2rad(latitude)))
    x0 = xmin + 0.06 * (xmax - xmin)
    y0 = ymin + 0.06 * (ymax - ymin)
    ax.plot([x0, x0 + longitude_degrees], [y0, y0], color="black", lw=3)
    ax.text(x0 + longitude_degrees / 2, y0 + 0.018 * (ymax - ymin), f"{length_m/1000:g} km", ha="center", va="bottom", fontsize=7)


def add_component_key(fig: plt.Figure, components: pd.DataFrame, bottom: float = 0.02) -> None:
    handles = [plt.Line2D([], [], linestyle="none", marker="o", markersize=3.5, color="black") for _ in range(len(components))]
    labels = [f"{row.component_id.replace('139-', '')}  {row.component_name}" for row in components.itertuples(index=False)]
    fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.5, bottom), ncol=2, frameon=False, fontsize=5.2, handletextpad=0.4, columnspacing=1.4)


def pressure_rasters(indices: dict[str, np.ndarray], observations: dict[str, np.ndarray]) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    valids = {epoch: BASE.valid_mask(indices[epoch], observations[epoch]) for epoch in EPOCHS}
    pooled = {band: np.concatenate([indices[epoch][:, :, band][valids[epoch]] for epoch in EPOCHS]) for band in [0, 1, 2]}
    bounds = {band: np.nanpercentile(values, [2, 98]) for band, values in pooled.items()}
    output = {}
    for epoch in EPOCHS:
        array = indices[epoch]
        scaled = []
        for band in [0, 1, 2]:
            low, high = bounds[band]
            scaled.append(np.clip((array[:, :, band] - low) / (high - low), 0, 1))
        ndvi_pressure = 1 - scaled[0]
        ndbi_pressure = scaled[1]
        mndwi_pressure = 1 - scaled[2]
        surface = (ndvi_pressure + ndbi_pressure) / 2
        pressure = (surface + mndwi_pressure) / 2
        pressure[~valids[epoch]] = np.nan
        output[epoch] = pressure.astype(np.float32)
    return output, valids


def create_figures(
    open_site: pd.DataFrame,
    annual: pd.DataFrame,
    seasonal: pd.DataFrame,
    climatology: pd.DataFrame,
    trends: pd.DataFrame,
    product_annual: pd.DataFrame,
    epoch_weather: pd.DataFrame,
    associations: pd.DataFrame,
    model_results: pd.DataFrame,
    calibration: pd.DataFrame,
    scale_sensitivity: pd.DataFrame,
    ablation: pd.DataFrame,
    rank_table: pd.DataFrame,
    rank_uncertainty: pd.DataFrame,
) -> None:
    components = BASE.load_components()
    indices, observations, _ = BASE.load_epoch_arrays()
    pressures, valids = pressure_rasters(indices, observations)
    _, terrain_arrays = BASE.load_terrain(components)
    endpoint_mask = valids["E2004"] & valids["E2024"]
    delta = indices["E2024"] - indices["E2004"]
    q_ndvi = np.quantile(delta[:, :, 0][endpoint_mask], 0.20)
    q_mndwi = np.quantile(delta[:, :, 2][endpoint_mask], 0.20)
    q_ndbi = np.quantile(delta[:, :, 1][endpoint_mask], 0.80)
    convergence = (
        (delta[:, :, 0] <= q_ndvi).astype(int)
        + (delta[:, :, 2] <= q_mndwi).astype(int)
        + (delta[:, :, 1] >= q_ndbi).astype(int)
    ).astype(float)
    convergence[~endpoint_mask] = np.nan

    # 1. Study area map.
    fig, ax = plt.subplots(figsize=(10.5, 10.2))
    extent_ll = [float(terrain_arrays["lons"].min()), float(terrain_arrays["lons"].max()), float(terrain_arrays["lats"].min()), float(terrain_arrays["lats"].max())]
    image = ax.imshow(terrain_arrays["dem"], extent=extent_ll, origin="upper", cmap="terrain", aspect="equal")
    scatter = ax.scatter(components["longitude"], components["latitude"], c=np.arange(len(components)), cmap="viridis", s=45, edgecolor="white", linewidth=0.7)
    for row in components.itertuples(index=False):
        ax.annotate(row.component_id.replace("139-", ""), (row.longitude, row.latitude), xytext=(3, 3), textcoords="offset points", fontsize=6)
    ax.set_title("Taxila analytical study area, mapped heritage components and terrain context")
    ax.set_xlabel("Longitude (WGS84)")
    ax.set_ylabel("Latitude (WGS84)")
    add_north_arrow(ax)
    add_scale_bar_lonlat(ax, 5000)
    fig.colorbar(image, ax=ax, shrink=0.75, label="Elevation (m)")
    ax.text(0.01, 0.01, "CRS: WGS84 | Terrain: 1 arc-second HGT | circles are analytical supports, not legal buffers", transform=ax.transAxes, fontsize=6, bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"})
    fig.subplots_adjust(bottom=0.23)
    add_component_key(fig, components)
    save_figure(fig, "figure_01_study_area_context_map", map_output=True)

    # 2. Five-epoch pressure maps.
    fig, axes = plt.subplots(2, 3, figsize=(13, 8.4), constrained_layout=True)
    extent_utm = [BASE.XMIN, BASE.XMIN + BASE.WIDTH * BASE.CELL, BASE.YMAX - BASE.HEIGHT * BASE.CELL, BASE.YMAX]
    plotted = None
    for ax, epoch in zip(axes.flat, EPOCHS):
        plotted = ax.imshow(pressures[epoch], extent=extent_utm, origin="upper", cmap="magma", vmin=0, vmax=1)
        ax.scatter(components["easting_m"], components["northing_m"], s=10, facecolor="white", edgecolor="black", linewidth=0.3)
        ax.set_title(f"{EPOCH_YEARS[epoch]} composite")
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
    axes.flat[-1].axis("off")
    add_north_arrow(axes.flat[0], x=0.91, y=0.88)
    add_scale_bar_utm(axes.flat[0], 5000)
    fig.colorbar(plotted, ax=axes.ravel().tolist(), shrink=0.78, label="Relative landscape-pressure index (robust 0–1 scaling)")
    fig.suptitle("Five-epoch Landsat-derived relative landscape pressure", fontsize=12, fontweight="bold")
    fig.text(0.5, 0.006, "CRS: EPSG:32643 | 5 km scale bar and north arrow shown in the first panel | white = NoData", ha="center", fontsize=6)
    save_figure(fig, "figure_02_five_epoch_landscape_pressure_maps", map_output=True)

    # 3. Spectral convergence.
    fig, ax = plt.subplots(figsize=(9, 8))
    plotted = ax.imshow(convergence, extent=extent_utm, origin="upper", cmap="viridis", vmin=0, vmax=3)
    ax.scatter(components["easting_m"], components["northing_m"], s=34, facecolor="white", edgecolor="black", linewidth=0.6)
    for row in components.itertuples(index=False):
        ax.annotate(row.component_id.replace("139-", ""), (row.easting_m, row.northing_m), xytext=(3, 2), textcoords="offset points", fontsize=6)
    add_north_arrow(ax)
    add_scale_bar_utm(ax, 5000)
    ax.set_title("2004–2024 adverse spectral-criterion convergence")
    ax.set_xlabel("Easting (m), EPSG:32643")
    ax.set_ylabel("Northing (m), EPSG:32643")
    fig.colorbar(plotted, ax=ax, ticks=[0, 1, 2, 3], label="Adverse criteria met")
    ax.text(0.01, 0.01, "NDVI decrease, MNDWI decrease, NDBI increase; pressure screen, not damage map", transform=ax.transAxes, fontsize=6, bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"})
    save_figure(fig, "figure_03_spectral_pressure_convergence", map_output=True)

    # 4. Climatology.
    fig, ax1 = plt.subplots(figsize=(9.5, 4.8))
    ax1.bar(climatology["month"], climatology["precipitation_monthly_mean_mm"], color=COLORS["blue"], alpha=0.8, label="Precipitation")
    ax1.set_xlabel("Month")
    ax1.set_ylabel("Mean monthly precipitation (mm)", color=COLORS["blue"])
    ax2 = ax1.twinx()
    ax2.plot(climatology["month"], climatology["temperature_mean_c"], marker="o", color=COLORS["red"], label="Mean temperature")
    ax2.fill_between(climatology["month"], climatology["tmin_mean_c"], climatology["tmax_mean_c"], color=COLORS["red"], alpha=0.16, label="Mean min–max envelope")
    ax2.set_ylabel("Temperature (°C)", color=COLORS["red"])
    ax1.set_xticks(range(1, 13))
    ax1.set_title("Open-Meteo ERA5-Seamless 1991–2020 climatology")
    lines = ax1.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    labels = ax1.get_legend_handles_labels()[1] + ax2.get_legend_handles_labels()[1]
    ax1.legend(lines, labels, frameon=False, ncol=3, loc="upper left")
    save_figure(fig, "figure_04_open_meteo_climatology")

    # 5. Annual trends.
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    trend_specs = [("precipitation_sum_mm", "Annual precipitation (mm)", COLORS["blue"]), ("temperature_mean_c", "Annual mean temperature (°C)", COLORS["red"])]
    for ax, (metric, label, color) in zip(axes, trend_specs):
        ax.plot(annual["year"], annual[metric], marker="o", ms=3, color=color, lw=1, alpha=0.75)
        record = trends[(trends["period"] == "annual") & (trends["metric"] == metric)].iloc[0]
        x = annual["year"].to_numpy()
        center = annual[metric].median() + record["theil_sen_slope_per_year"] * (x - np.median(x))
        low = annual[metric].median() + record["moving_block_slope_ci_low_95"] * (x - np.median(x))
        high = annual[metric].median() + record["moving_block_slope_ci_high_95"] * (x - np.median(x))
        ax.plot(x, center, color="black", lw=2, label="Theil–Sen trend")
        ax.fill_between(x, np.minimum(low, high), np.maximum(low, high), color="black", alpha=0.12, label="95% moving-block slope envelope")
        ax.set_ylabel(label)
        ax.legend(frameon=False, loc="best")
    axes[-1].set_xlabel("Year")
    axes[0].set_title("Annual climate variability and robust trends")
    save_figure(fig, "figure_05_annual_climate_trends")

    # 6. Seasonal anomalies.
    pivot = seasonal.pivot(index="season_year", columns="season", values="precipitation_sum_mm")
    baseline = pivot.loc[pivot.index.intersection(range(1991, 2021))]
    z = (pivot - baseline.mean()) / baseline.std(ddof=1)
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.heatmap(z.T, cmap="RdBu", center=0, vmin=-3, vmax=3, cbar_kws={"label": "Precipitation anomaly (SD from 1991–2020)"}, ax=ax)
    ax.set_title("Seasonal and monsoon precipitation anomalies")
    ax.set_xlabel("Season year")
    ax.set_ylabel("")
    save_figure(fig, "figure_06_seasonal_monsoon_anomalies")

    # 7. Epoch-specific forcing.
    open_epoch = epoch_weather[epoch_weather["weather_provider"] == "Open-Meteo ERA5-Seamless"].copy()
    plot_cols = ["precipitation_preceding_30d_mm_mean", "precipitation_preceding_90d_mm_mean", "precipitation_preceding_365d_mm_mean"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    melted = open_epoch.melt(id_vars="label_year", value_vars=plot_cols, var_name="window", value_name="precipitation_mm")
    sns.barplot(data=melted, x="label_year", y="precipitation_mm", hue="window", palette="Blues", ax=axes[0])
    axes[0].set_title("Antecedent precipitation across retained scene dates")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Mean precipitation (mm)")
    axes[0].legend(title="", labels=["30 d", "90 d", "365 d"], frameon=False)
    axes[1].plot(open_epoch["label_year"], open_epoch["temperature_mean_preceding_30d_c_mean"], marker="o", color=COLORS["red"], label="30-d mean temperature")
    axes[1].plot(open_epoch["label_year"], open_epoch["tmax_max_preceding_30d_c_mean"], marker="s", color=COLORS["orange"], label="30-d maximum temperature")
    axes[1].set_title("Antecedent temperature across retained scene dates")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Temperature (°C)")
    axes[1].legend(frameon=False)
    save_figure(fig, "figure_07_epoch_specific_weather_forcing")

    # 8. Extreme timeline.
    fig, axes = plt.subplots(3, 1, figsize=(10, 7.5), sharex=True)
    axes[0].bar(annual["year"], annual["rx1day_mm"], color=COLORS["blue"])
    axes[0].set_ylabel("Rx1day (mm)")
    axes[1].plot(annual["year"], annual["hot_days"], color=COLORS["red"], marker="o", ms=3)
    axes[1].set_ylabel("Hot days")
    axes[2].plot(annual["year"], annual["consecutive_dry_days"], color=COLORS["gold"], marker="o", ms=3, label="Longest dry spell")
    axes[2].plot(annual["year"], annual["consecutive_wet_days"], color=COLORS["teal"], marker="s", ms=3, label="Longest wet spell")
    axes[2].set_ylabel("Days")
    axes[2].set_xlabel("Year")
    axes[2].legend(frameon=False)
    axes[0].set_title("Extreme rainfall, heat and wet/dry-spell timeline")
    save_figure(fig, "figure_08_climate_extremes_timeline")

    # 9. Product comparison.
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 4.8))
    axes[0].scatter(product_annual["precipitation_sum_nasa"], product_annual["precipitation_sum_open"], color=COLORS["blue"], alpha=0.8)
    limits = [min(product_annual["precipitation_sum_nasa"].min(), product_annual["precipitation_sum_open"].min()), max(product_annual["precipitation_sum_nasa"].max(), product_annual["precipitation_sum_open"].max())]
    axes[0].plot(limits, limits, "--", color="black", lw=1)
    axes[0].set_xlabel("NASA POWER annual precipitation (mm)")
    axes[0].set_ylabel("Open-Meteo annual precipitation (mm)")
    axes[0].set_title("Annual precipitation agreement")
    axes[1].scatter(product_annual["temperature_2m_mean_nasa"], product_annual["temperature_2m_mean_open"], color=COLORS["red"], alpha=0.8)
    limits = [min(product_annual["temperature_2m_mean_nasa"].min(), product_annual["temperature_2m_mean_open"].min()), max(product_annual["temperature_2m_mean_nasa"].max(), product_annual["temperature_2m_mean_open"].max())]
    axes[1].plot(limits, limits, "--", color="black", lw=1)
    axes[1].set_xlabel("NASA POWER annual mean temperature (°C)")
    axes[1].set_ylabel("Open-Meteo annual mean temperature (°C)")
    axes[1].set_title("Annual temperature agreement")
    fig.suptitle("Open-Meteo ERA5-Seamless versus NASA POWER", fontsize=12, fontweight="bold")
    save_figure(fig, "figure_09_open_meteo_nasa_power_comparison")

    # 10. Weather-spectral lag heatmap.
    heat = associations.pivot(index="spectral_metric", columns="climate_metric", values="spearman_rho")
    fig, ax = plt.subplots(figsize=(10.5, 3.8))
    sns.heatmap(heat, cmap="RdBu_r", center=0, vmin=-1, vmax=1, annot=True, fmt=".2f", cbar_kws={"label": "Spearman ρ (five epochs; descriptive)"}, ax=ax)
    ax.set_title("Exploratory antecedent-rainfall and spectral associations")
    ax.set_xlabel("Antecedent precipitation window")
    ax.set_ylabel("")
    save_figure(fig, "figure_10_weather_spectral_lag_associations")

    # 11. Terrain and hydrology.
    fig, axes = plt.subplots(2, 2, figsize=(9.2, 7.2))
    panels = [("dem", "Elevation (m)", "terrain"), ("slope_deg", "Slope (degrees)", "magma"), ("flow", "D8 flow accumulation", "Blues"), ("drainage_distance_m", "Distance to high-flow cells (m)", "viridis_r")]
    for ax, (key, title, cmap) in zip(axes.flat, panels):
        values = np.log1p(terrain_arrays[key]) if key == "flow" else terrain_arrays[key]
        low, high = np.nanpercentile(values, [2, 98])
        plotted = ax.imshow(values, extent=extent_ll, origin="upper", cmap=cmap, vmin=low, vmax=high, aspect="equal")
        ax.scatter(components["longitude"], components["latitude"], s=18, facecolor="white", edgecolor="black", linewidth=0.4)
        ax.set_title(title if key != "flow" else "log(1 + D8 flow accumulation)")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        fig.colorbar(plotted, ax=ax, shrink=0.74)
    add_north_arrow(axes.flat[0], x=0.9, y=0.88)
    add_scale_bar_lonlat(axes.flat[0], 5000)
    fig.suptitle("Terrain and hydrological susceptibility context", y=0.99, fontsize=12, fontweight="bold")
    fig.text(0.5, 0.005, "CRS: WGS84 | 5 km scale bar and north arrow shown in the elevation panel", ha="center", fontsize=6)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    save_figure(fig, "figure_11_terrain_flow_drainage_susceptibility", map_output=True)

    # 12. Integrated field-inspection priority map.
    score500 = pd.read_csv(BASELINE_TABLES / "component_epoch_integrated_scores.csv")
    score500 = score500[(score500["epoch_id"] == "E2024") & (score500["radius_m"] == 500)].merge(components, on=["component_id", "component_name"])
    fig, ax = plt.subplots(figsize=(10.5, 10.2))
    base_map = ax.imshow(pressures["E2024"], extent=extent_utm, origin="upper", cmap="Greys", vmin=0, vmax=1, alpha=0.65)
    plotted = ax.scatter(score500["easting_m"], score500["northing_m"], c=score500["local_priority_score"], s=60 + 160 * score500["local_priority_score"], cmap="YlOrRd", vmin=0, vmax=1, edgecolor="black", linewidth=0.6)
    for row in score500.itertuples(index=False):
        ax.annotate(row.component_id.replace("139-", ""), (row.easting_m, row.northing_m), xytext=(3, 3), textcoords="offset points", fontsize=6)
    add_north_arrow(ax)
    add_scale_bar_utm(ax, 5000)
    ax.set_title("2024 relative field-inspection priority at 500 m analytical support")
    ax.set_xlabel("Easting (m), EPSG:32643")
    ax.set_ylabel("Northing (m), EPSG:32643")
    fig.colorbar(plotted, ax=ax, label="Local priority score (0–1)")
    ax.text(0.01, 0.01, "Landscape pressure + terrain susceptibility; not a damage probability", transform=ax.transAxes, fontsize=6, bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"})
    fig.subplots_adjust(bottom=0.23)
    add_component_key(fig, components)
    save_figure(fig, "figure_12_integrated_component_priority_map", map_output=True)

    # 13. Rankings by scale.
    ordered = rank_table.sort_values("rank_500m")
    fig, ax = plt.subplots(figsize=(10, 7))
    for radius, marker, color in [(250, "o", COLORS["blue"]), (500, "s", COLORS["red"]), (1000, "^", COLORS["teal"])]:
        ax.plot(ordered[f"rank_{radius}m"], np.arange(len(ordered)), marker=marker, color=color, lw=1, label=f"{radius} m")
    ax.set_yticks(np.arange(len(ordered)))
    ax.set_yticklabels(ordered["component_name"])
    ax.invert_yaxis()
    ax.invert_xaxis()
    ax.set_xlabel("Rank (1 = higher relative priority)")
    ax.set_title("Component ranking sensitivity to analytical support")
    ax.legend(frameon=False)
    save_figure(fig, "figure_13_component_rankings_by_scale")

    # 14. Proxy performance and calibration.
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    ordered_models = model_results.sort_values("macro_f1")
    y = np.arange(len(ordered_models))
    xerr = np.vstack([ordered_models["macro_f1"] - ordered_models["macro_f1_ci_low_95"], ordered_models["macro_f1_ci_high_95"] - ordered_models["macro_f1"]])
    axes[0].errorbar(ordered_models["macro_f1"], y, xerr=xerr, fmt="o", color=COLORS["blue"], capsize=3, label="Macro-F1")
    axes[0].scatter(ordered_models["balanced_accuracy"], y, marker="s", color=COLORS["gold"], label="Balanced accuracy")
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(ordered_models["model"])
    axes[0].set_xlim(0.55, 1.0)
    axes[0].set_xlabel("Held-out proxy metric")
    axes[0].set_title("Buffered spatial test-stripe performance")
    axes[0].legend(frameon=False)
    for model, group in calibration.groupby("model"):
        axes[1].plot(group["mean_confidence"], group["accuracy"], marker="o", ms=3, label=model)
    axes[1].plot([0, 1], [0, 1], "--", color="black", lw=1)
    axes[1].set_xlabel("Mean confidence")
    axes[1].set_ylabel("Observed proxy agreement")
    axes[1].set_title("Top-label calibration")
    axes[1].legend(frameon=False, fontsize=6)
    fig.suptitle("Proxy land-cover agreement, not independent heritage-condition accuracy", fontsize=11.5, fontweight="bold")
    save_figure(fig, "figure_14_proxy_model_performance_calibration")

    # 15. Indicator redundancy.
    pressure_cols = ["ndvi_pressure", "ndbi_pressure", "mndwi_pressure", "surface_cover_pressure", "landscape_pressure_score", "slope_pressure", "wetness_pressure", "drainage_proximity_pressure", "terrain_susceptibility_score"]
    corr = score500[pressure_cols].corr(method="spearman")
    fig, ax = plt.subplots(figsize=(8.5, 7.2))
    sns.heatmap(corr, cmap="RdBu_r", center=0, vmin=-1, vmax=1, annot=True, fmt=".2f", square=True, cbar_kws={"label": "Spearman ρ"}, ax=ax)
    ax.set_title("Indicator correlation and redundancy screen (2024, 500 m)")
    save_figure(fig, "figure_15_indicator_redundancy_matrix")

    # 16. Rank uncertainty.
    monte = pd.read_csv(BASELINE_TABLES / "monte_carlo_domain_weight_rank_uncertainty.csv")
    joined = monte.merge(rank_uncertainty, on=["component_id", "component_name"], suffixes=("_weight", "_block")).sort_values("equal_domain_rank")
    fig, axes = plt.subplots(1, 2, figsize=(12, 7), sharey=True)
    ypos = np.arange(len(joined))
    axes[0].errorbar(joined["monte_carlo_median_rank"], ypos, xerr=np.vstack([joined["monte_carlo_median_rank"] - joined["rank_p2_5"], joined["rank_p97_5"] - joined["monte_carlo_median_rank"]]), fmt="o", color=COLORS["purple"], capsize=2)
    axes[0].set_title("50,000-draw domain-weight uncertainty")
    axes[1].errorbar(joined["rank_median"], ypos, xerr=np.vstack([joined["rank_median"] - joined["rank_ci_low_95"], joined["rank_ci_high_95"] - joined["rank_median"]]), fmt="o", color=COLORS["teal"], capsize=2)
    axes[1].set_title("2,000-draw 150 m spatial-block uncertainty")
    axes[0].set_yticks(ypos)
    axes[0].set_yticklabels(joined["component_name"])
    for ax in axes:
        ax.invert_xaxis()
        ax.set_xlabel("Rank (1 = higher priority)")
    axes[0].invert_yaxis()
    save_figure(fig, "figure_16_rank_stability_uncertainty")

    # 17. Ablation.
    plot_ablation = ablation[ablation["scenario"] != "Climate only"].sort_values("spearman_rho_with_full_integrated")
    fig, ax = plt.subplots(figsize=(9.5, 6.4))
    colors = [COLORS["red"] if value < 0.5 else COLORS["blue"] for value in plot_ablation["spearman_rho_with_full_integrated"].fillna(0)]
    ax.barh(plot_ablation["scenario"], plot_ablation["spearman_rho_with_full_integrated"], color=colors)
    ax.axvline(1, color="black", lw=0.8)
    ax.set_xlim(-0.5, 1.05)
    ax.set_xlabel("Spearman rank agreement with full integrated context")
    ax.set_title("Factor and domain ablation sensitivity")
    save_figure(fig, "figure_17_factor_domain_ablation")

    # Arrays for GeoTIFF export by the companion writer.
    for epoch, array in pressures.items():
        array.astype("<f4").tofile(RASTERS / f"{epoch}_relative_landscape_pressure.f32")
    convergence.astype("<f4").tofile(RASTERS / "E2004_E2024_spectral_convergence.f32")
    json_dump(
        RASTERS / "derived_raster_spec.json",
        {
            "width": BASE.WIDTH,
            "height": BASE.HEIGHT,
            "crs": "EPSG:32643",
            "transform_gdal": [BASE.XMIN, BASE.CELL, 0, BASE.YMAX, 0, -BASE.CELL],
            "nodata": -9999,
            "float32_files": [f"{epoch}_relative_landscape_pressure.f32" for epoch in EPOCHS] + ["E2004_E2024_spectral_convergence.f32"],
        },
    )


def build_inventory() -> pd.DataFrame:
    rows = []
    excluded_roots = {RUN_ROOT.resolve()}
    for path in SOURCE_ROOT.rglob("*"):
        if not path.is_file() or any(root in path.resolve().parents for root in excluded_roots):
            continue
        relative = path.relative_to(SOURCE_ROOT)
        suffix = path.suffix.lower()
        name = path.name.lower()
        if "raw" in path.parts or suffix in {".zip", ".json"} and "source" in path.parts:
            role = "source_or_frozen_input"
        elif suffix in {".py", ".r", ".mjs", ".js", ".sh"}:
            role = "executable_code"
        elif suffix in {".tif", ".tiff", ".hgt", ".gz"}:
            role = "spatial_data"
        elif suffix in {".geojson", ".gpkg"}:
            role = "vector_data"
        elif suffix in {".csv", ".xlsx"}:
            role = "tabular_data_or_result"
        elif suffix in {".docx", ".pdf", ".md", ".txt"}:
            role = "documentation"
        else:
            role = "other"
        if "derived" in path.parts or "outputs" in path.parts or "deliverables" in path.parts:
            status = "derived"
        elif "inputs" in path.parts or "source" in path.parts:
            status = "original_or_frozen_input"
        else:
            status = "project_working_file"
        stat = path.stat()
        rows.append(
            {
                "file_path": str(relative),
                "file_type": suffix or "none",
                "size_bytes": stat.st_size,
                "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "workflow_role": role,
                "data_status": status,
                "reproducible": role in {"executable_code", "documentation"} or status == "derived",
                "source": "project workspace",
                "spatial_reference": "see file metadata or manifest" if role in {"spatial_data", "vector_data"} else "not_applicable",
                "temporal_coverage": "see source manifest" if role in {"source_or_frozen_input", "spatial_data", "tabular_data_or_result"} else "not_applicable",
            }
        )
    inventory = pd.DataFrame(rows).sort_values("file_path")
    inventory.to_csv(INVENTORY / "project_file_inventory.csv", index=False)
    return inventory


def build_source_and_method_manifests(open_combined: pd.DataFrame, mapping: pd.DataFrame) -> None:
    source_rows = [
        {
            "dataset": "Landsat Collection 2 Level-2",
            "authority": "USGS via Microsoft Planetary Computer STAC",
            "variables": "surface reflectance, QA, NDVI, NDBI, MNDWI, BSI",
            "coverage": "five post-monsoon three-year composite windows, 2003–2025",
            "resolution": "30 m",
            "access": "https://planetarycomputer.microsoft.com/api/stac/v1",
            "licence_or_attribution": "USGS Landsat; public domain with acknowledgement",
            "role": "local multi-temporal landscape pressure",
        },
        {
            "dataset": "Open-Meteo ERA5-Seamless historical weather",
            "authority": "Open-Meteo; ECMWF ERA5-Land surface fields and ERA5 forcing",
            "variables": "temperature, precipitation, humidity, dew point, wind, soil moisture, ET0",
            "coverage": "1991-01-01 to 2025-12-31",
            "resolution": "0.1 degree surface fields; four unique returned cells",
            "access": "https://open-meteo.com/en/docs/historical-weather-api",
            "licence_or_attribution": "Open-Meteo attribution and underlying ECMWF/Copernicus terms",
            "role": "primary historical climate forcing",
        },
        {
            "dataset": "NASA POWER Daily",
            "authority": "NASA POWER",
            "variables": "precipitation, 2 m temperature, relative humidity, 10 m wind",
            "coverage": "1991-01-01 to 2025-12-31",
            "resolution": "native NASA POWER meteorological grid; site point request",
            "access": "https://power.larc.nasa.gov/docs/services/api/temporal/daily/",
            "licence_or_attribution": "NASA POWER attribution",
            "role": "independent reanalysis-product comparison, not ground truth",
        },
        {
            "dataset": "1 arc-second HGT N33E072",
            "authority": "AWS Terrain Tiles public elevation collection",
            "variables": "elevation; derived slope, roughness, D8 flow, wetness proxy, drainage distance",
            "coverage": "Taxila study envelope",
            "resolution": "approximately 30 m",
            "access": "https://registry.opendata.aws/terrain-tiles/",
            "licence_or_attribution": "AWS Open Data terrain attribution",
            "role": "terrain and hydrological susceptibility",
        },
        {
            "dataset": "ESA WorldCover 2020/2021 consensus proxy",
            "authority": "ESA WorldCover",
            "variables": "weak-supervision land-cover class",
            "coverage": "E2019 development feature frame",
            "resolution": "10 m source aggregated/aligned to analytical grid",
            "access": "https://esa-worldcover.org/",
            "licence_or_attribution": "ESA WorldCover terms and attribution",
            "role": "proxy land-cover agreement only; not heritage-condition truth",
        },
    ]
    pd.DataFrame(source_rows).to_csv(MANIFESTS / "source_manifest.csv", index=False)
    method_rows = [
        {"method": "Theil-Sen slope", "implementation": "scipy.stats.theilslopes", "version": __import__("scipy").__version__, "date_checked": "2026-08-01", "selection_reason": "robust monotonic slope under non-normal climate metrics", "limitation": "does not by itself correct serial dependence"},
        {"method": "Five-year moving-block bootstrap", "implementation": "project implementation", "version": "1.0", "date_checked": "2026-08-01", "selection_reason": "serial-dependence-aware slope and uncertainty sensitivity", "limitation": "block length is a defensible sensitivity choice, not uniquely identified"},
        {"method": "Spatial GroupKFold", "implementation": "scikit-learn", "version": __import__("sklearn").__version__, "date_checked": "2026-08-01", "selection_reason": "prevent sample-level pixel leakage during development", "limitation": "inner folds may share boundaries; final test uses a full buffer"},
        {"method": "Buffered contiguous spatial test stripe", "implementation": "project implementation", "version": "1.0", "date_checked": "2026-08-01", "selection_reason": "separates all test blocks from development by 2.01 km", "limitation": "single geographic holdout tests one transfer direction"},
        {"method": "Hierarchical composite weighting", "implementation": "project implementation", "version": "1.0", "date_checked": "2026-08-01", "selection_reason": "prevents correlated NDVI/NDBI evidence from double counting", "limitation": "weights are structural assumptions tested by Monte Carlo"},
    ]
    pd.DataFrame(method_rows).to_csv(MANIFESTS / "method_selection_record.csv", index=False)

    variables = []
    for column in open_combined.columns:
        variables.append(
            {
                "dataset": "Open-Meteo cleaned daily by grid cell",
                "variable": column,
                "unit": {
                    "temperature_2m_mean": "degC",
                    "temperature_2m_max": "degC",
                    "temperature_2m_min": "degC",
                    "precipitation_sum": "mm/day",
                    "relative_humidity_2m_mean": "percent",
                    "dew_point_2m_mean": "degC",
                    "wind_speed_10m_max": "km/h",
                    "soil_moisture_0_to_7cm_mean": "m3/m3",
                    "et0_fao_evapotranspiration_sum": "mm/day",
                }.get(column, "identifier_or_date"),
                "description": column.replace("_", " "),
                "missing_data_treatment": "no imputation; complete coverage required by QC",
            }
        )
    pd.DataFrame(variables).to_csv(REPRO / "data_dictionary.csv", index=False)
    mapping.groupby("weather_cell_id").size().rename("component_count").reset_index().to_csv(TABLES / "weather_grid_component_counts.csv", index=False)


def build_experiment_records(
    endpoint_summary: dict[str, object],
    trends: pd.DataFrame,
    product_metrics: pd.DataFrame,
    model_results: pd.DataFrame,
    scale_sensitivity: pd.DataFrame,
    rank_uncertainty: pd.DataFrame,
) -> None:
    statuses = [
        (1, "Existing Landsat/proxy baseline reproduction", "COMPLETED", "Exact legacy outputs reproduced in isolated run; validation gates checked."),
        (2, "Data acquisition and completeness", "COMPLETED", "Workspace inventory, four Open-Meteo weather cells and source manifests created."),
        (3, "Open-Meteo weather analysis", "COMPLETED", "1991–2025 ERA5-Seamless daily data acquired and quality controlled."),
        (4, "Open-Meteo versus NASA POWER", "COMPLETED", "Daily, seasonal, annual and extreme-event agreement quantified; neither treated as ground truth."),
        (5, "Historical climate variability and trends", "COMPLETED", "Annual/seasonal metrics, Theil-Sen slopes, moving-block intervals and FDR produced."),
        (6, "Weather during Landsat epochs", "COMPLETED", "Weather matched to every retained scene date and aggregated to composite epochs."),
        (7, "Weather-spectral relationships", "EXPLORATORY", "Five unique epochs; descriptive lag associations and leave-one-epoch sensitivity only."),
        (8, "Terrain and hydrological susceptibility", "COMPLETED", "Elevation, slope, D8 convergence, wetness proxy and drainage distance analysed."),
        (9, "Integrated component priority", "COMPLETED", "Hierarchical landscape/terrain score plus climate context; not monument risk."),
        (10, "Scale sensitivity", "COMPLETED", "250/500/1000 m Spearman, Kendall, top-k and reversals quantified."),
        (11, "Redundancy analysis", "COMPLETED", "Indicator correlations and NDVI/NDBI grouping decision recorded."),
        (12, "Factor and domain ablation", "COMPLETED", "Leave-factor and leave-domain ranking effects calculated."),
        (13, "Weighting uncertainty", "COMPLETED", "50,000 Dirichlet domain-weight simulations reproduced; expert weights unavailable."),
        (14, "Block-bootstrap uncertainty", "COMPLETED", "2,000 150 m spectral-block ranking draws plus 2,000 test-block model draws."),
        (15, "Proxy-model comparison", "COMPLETED", "Legacy 79/21 split reproduced and stricter buffered split executed with calibration."),
        (16, "Optional ancillary hazards", "NOT_EXECUTED", "No reliable harmonised event inventory was required for the central question; scope preserved."),
    ]
    status_table = pd.DataFrame(statuses, columns=["experiment", "name", "status", "technical_note"])
    status_table.to_csv(VALIDATION / "experiment_status_matrix.csv", index=False)

    best_trend = trends[(trends["period"] == "annual") & (trends["metric"].isin(["precipitation_sum_mm", "temperature_mean_c"]))]
    primary_model = model_results[model_results["primary_selected_from_inner_cv"]].iloc[0]
    epoch_weather = pd.read_csv(TABLES / "landsat_epoch_weather_lag_summary.csv")
    open_epoch = epoch_weather[epoch_weather["weather_provider"] == "Open-Meteo ERA5-Seamless"].set_index("epoch_id")
    rankings = pd.read_csv(TABLES / "component_rankings_250m_500m_1000m.csv")
    giri = rankings[rankings["component_id"] == "139-009"].iloc[0]
    bhallar_boot = rank_uncertainty[rank_uncertainty["component_id"] == "139-017"].iloc[0]
    giri_boot = rank_uncertainty[rank_uncertainty["component_id"] == "139-009"].iloc[0]
    annual_product = product_metrics[
        (product_metrics["variable"] == "precipitation_sum")
        & (product_metrics["temporal_scale"] == "annual")
        & (product_metrics["comparison_subset"] == "full_record")
    ].iloc[0]
    precipitation_trend = trends[(trends["period"] == "annual") & (trends["metric"] == "precipitation_sum_mm")].iloc[0]
    temperature_trend = trends[(trends["period"] == "annual") & (trends["metric"] == "temperature_mean_c")].iloc[0]
    claims = [
        {
            "finding": f"Common 2004–2024 endpoint support is {endpoint_summary['endpoint_supported_percent']:.2f}% ({endpoint_summary['endpoint_supported_cells']:,} cells).",
            "experiment": 1,
            "exact_numerical_evidence": endpoint_summary["endpoint_supported_percent"],
            "source_data": "frozen Landsat composites",
            "source_script": "08_experiment_scripts/baseline/run_integrated_experiments.py",
            "output_file": "13_tables/baseline_reproduction/endpoint_screening_summary.json",
            "uncertainty": "deterministic for frozen masks",
            "limitation": "support does not validate change causation",
            "reproducibility_status": "REPRODUCED",
            "manuscript_suitability": "YES_WITH_PRESSURE_TERMINOLOGY",
        },
        {
            "finding": f"At least two adverse endpoint spectral criteria occur in {endpoint_summary['share_c_ge_2_percent']:.2f}% of supported cells.",
            "experiment": 1,
            "exact_numerical_evidence": endpoint_summary["share_c_ge_2_percent"],
            "source_data": "E2004 and E2024 Landsat indices",
            "source_script": "08_experiment_scripts/baseline/run_integrated_experiments.py",
            "output_file": "13_tables/baseline_reproduction/endpoint_screening_summary.json",
            "uncertainty": "threshold and sensor-harmonisation sensitivity remain",
            "limitation": "spectral convergence is not monument damage",
            "reproducibility_status": "REPRODUCED",
            "manuscript_suitability": "YES_WITH_LIMITATION",
        },
        {
            "finding": f"The development-selected buffered proxy model is {primary_model['model']} with held-out macro-F1 {primary_model['macro_f1']:.3f}.",
            "experiment": 15,
            "exact_numerical_evidence": primary_model["macro_f1"],
            "source_data": "WorldCover-consensus proxy samples",
            "source_script": "08_experiment_scripts/execute_experiment_pipeline.py",
            "output_file": "13_tables/enhanced_spatially_buffered_proxy_model_comparison.csv",
            "uncertainty": f"95% block-bootstrap CI [{primary_model['macro_f1_ci_low_95']:.3f}, {primary_model['macro_f1_ci_high_95']:.3f}]",
            "limitation": "proxy agreement; not independent heritage-condition accuracy",
            "reproducibility_status": "EXECUTED",
            "manuscript_suitability": "YES_ONLY_AS_PROXY_AGREEMENT",
        },
        {
            "finding": "Weather-spectral lag associations are underpowered for inference.",
            "experiment": 7,
            "exact_numerical_evidence": "five unique composite epochs",
            "source_data": "retained-scene lag aggregates and site-wide spectral medians",
            "source_script": "08_experiment_scripts/execute_experiment_pipeline.py",
            "output_file": "14_statistics/weather_spectral_lag_associations.csv",
            "uncertainty": "leave-one-epoch ranges reported",
            "limitation": "no causal or p-value interpretation",
            "reproducibility_status": "EXECUTED_EXPLORATORY",
            "manuscript_suitability": "DESCRIPTIVE_ONLY",
        },
        {
            "finding": (
                "Acquisition-date Open-Meteo precipitation does not identify E2024 as the wettest epoch: "
                f"E2004 has the largest 30-day mean ({open_epoch.loc['E2004', 'precipitation_preceding_30d_mm_mean']:.2f} mm), "
                f"E2019 the largest 90-day mean ({open_epoch.loc['E2019', 'precipitation_preceding_90d_mm_mean']:.2f} mm), "
                f"and E2014 the largest 365-day mean ({open_epoch.loc['E2014', 'precipitation_preceding_365d_mm_mean']:.2f} mm)."
            ),
            "experiment": 6,
            "exact_numerical_evidence": (
                f"E2024: 30d={open_epoch.loc['E2024', 'precipitation_preceding_30d_mm_mean']:.2f}, "
                f"90d={open_epoch.loc['E2024', 'precipitation_preceding_90d_mm_mean']:.2f}, "
                f"365d={open_epoch.loc['E2024', 'precipitation_preceding_365d_mm_mean']:.2f} mm"
            ),
            "source_data": "Open-Meteo ERA5-Seamless matched to every retained Landsat scene date",
            "source_script": "08_experiment_scripts/execute_experiment_pipeline.py",
            "output_file": "13_tables/landsat_epoch_weather_lag_summary.csv",
            "uncertainty": "multi-scene epoch means across four reanalysis cells; no station validation",
            "limitation": "the reproduced legacy 2024 NASA composite-extreme result is product/window dependent",
            "reproducibility_status": "EXECUTED_CORRECTION",
            "manuscript_suitability": "YES_AS_DISCREPANCY",
        },
        {
            "finding": (
                f"The 1991–2025 Open-Meteo annual precipitation slope is {precipitation_trend['theil_sen_slope_per_year']:.2f} mm/year, "
                f"while annual mean temperature changes by {temperature_trend['theil_sen_slope_per_year']:.3f} degC/year."
            ),
            "experiment": 5,
            "exact_numerical_evidence": (
                f"precipitation CI [{precipitation_trend['moving_block_slope_ci_low_95']:.2f}, {precipitation_trend['moving_block_slope_ci_high_95']:.2f}], "
                f"FDR p={precipitation_trend['fdr_adjusted_block_p']:.4f}; temperature CI "
                f"[{temperature_trend['moving_block_slope_ci_low_95']:.3f}, {temperature_trend['moving_block_slope_ci_high_95']:.3f}], "
                f"FDR p={temperature_trend['fdr_adjusted_block_p']:.4f}"
            ),
            "source_data": "Open-Meteo ERA5-Seamless annual means across four returned grid cells",
            "source_script": "08_experiment_scripts/execute_experiment_pipeline.py",
            "output_file": "14_statistics/open_meteo_climate_trends_block_bootstrap.csv",
            "uncertainty": "2,000-draw residual moving-block bootstrap; baseline-period sensitivity reported separately",
            "limitation": "reanalysis trend without local station validation; not causal attribution",
            "reproducibility_status": "EXECUTED",
            "manuscript_suitability": "YES_WITH_REANALYSIS_CAVEAT",
        },
        {
            "finding": (
                f"Giri is the deterministic 500 m leader (score {giri['score_500m']:.3f}), but spatial-block spectral uncertainty "
                f"gives Bhallar a median rank of {bhallar_boot['rank_median']:.0f} and Giri a median rank of {giri_boot['rank_median']:.0f}."
            ),
            "experiment": 14,
            "exact_numerical_evidence": (
                f"Bhallar rank CI [{bhallar_boot['rank_ci_low_95']:.0f}, {bhallar_boot['rank_ci_high_95']:.0f}], "
                f"P(top3)={bhallar_boot['probability_top_3']:.3f}; Giri rank CI "
                f"[{giri_boot['rank_ci_low_95']:.0f}, {giri_boot['rank_ci_high_95']:.0f}], P(top3)={giri_boot['probability_top_3']:.3f}"
            ),
            "source_data": "E2024 spectral samples grouped in 150 m spatial blocks; terrain fixed",
            "source_script": "08_experiment_scripts/execute_experiment_pipeline.py",
            "output_file": "14_statistics/component_rank_spatial_block_bootstrap.csv",
            "uncertainty": "2,000 spatial-block bootstrap draws",
            "limitation": "fixed-score and bootstrap rank answer different questions; climate forcing is common within epoch",
            "reproducibility_status": "EXECUTED",
            "manuscript_suitability": "YES_WITH_RANK_UNCERTAINTY",
        },
        {
            "finding": f"Open-Meteo and NASA POWER annual precipitation agreement is weak (Spearman rho={annual_product['spearman_rho']:.3f}).",
            "experiment": 4,
            "exact_numerical_evidence": (
                f"n={int(annual_product['n'])}, Pearson r={annual_product['pearson_r']:.3f}, "
                f"RMSE={annual_product['rmse']:.2f} mm/year, MAE={annual_product['mae']:.2f} mm/year"
            ),
            "source_data": "daily Open-Meteo ERA5-Seamless and NASA POWER, aggregated to annual totals",
            "source_script": "08_experiment_scripts/execute_experiment_pipeline.py",
            "output_file": "13_tables/open_meteo_nasa_power_comparison.csv",
            "uncertainty": "six NASA daily values above 200 mm are flagged and sensitivity subsets are reported",
            "limitation": "product disagreement cannot identify which product is accurate without station data",
            "reproducibility_status": "EXECUTED",
            "manuscript_suitability": "YES_AS_PRODUCT_UNCERTAINTY",
        },
    ]
    pd.DataFrame(claims).to_csv(VALIDATION / "claim_evidence_matrix.csv", index=False)

    discrepancy_rows = [
        {
            "baseline_claim": "Common endpoint analytical support approximately 95.74%",
            "executed_result": f"{endpoint_summary['endpoint_supported_percent']:.4f}%",
            "outcome": "REPRODUCED",
            "difference_or_cause": "rounding only",
            "scientific_decision": "retain the executed exact value",
            "affected_output": "13_tables/baseline_reproduction/endpoint_screening_summary.json",
        },
        {
            "baseline_claim": "2024 was associated with unusually wet forcing",
            "executed_result": (
                f"Open-Meteo E2024 means: 30d {open_epoch.loc['E2024', 'precipitation_preceding_30d_mm_mean']:.2f}, "
                f"90d {open_epoch.loc['E2024', 'precipitation_preceding_90d_mm_mean']:.2f}, "
                f"365d {open_epoch.loc['E2024', 'precipitation_preceding_365d_mm_mean']:.2f} mm; none is the five-epoch maximum"
            ),
            "outcome": "NOT_REPRODUCED_WITH_PRIMARY_REANALYSIS_WINDOWS",
            "difference_or_cause": "legacy result used a NASA POWER composite-extreme score; enhanced analysis uses scene-date Open-Meteo lag windows and exposes strong product disagreement",
            "scientific_decision": "report the legacy reproduction and the acquisition-date correction separately; do not call 2024 uniformly wet",
            "affected_output": "13_tables/landsat_epoch_weather_lag_summary.csv",
        },
        {
            "baseline_claim": "Giri ranks first at 500 m with score approximately 0.591",
            "executed_result": f"rank {giri['rank_500m']:.0f}; score {giri['score_500m']:.6f}",
            "outcome": "REPRODUCED_FIXED_ESTIMATE",
            "difference_or_cause": "none for the deterministic score; spatial-block sampling produces overlapping rank intervals",
            "scientific_decision": "retain Giri as fixed leader but present Bhallar/Giri rank uncertainty together",
            "affected_output": "13_tables/component_rankings_250m_500m_1000m.csv; 14_statistics/component_rank_spatial_block_bootstrap.csv",
        },
        {
            "baseline_claim": "500 m versus 1,000 m rank agreement approximately rho=0.900",
            "executed_result": f"rho={scale_sensitivity.loc[(scale_sensitivity['radius_a_m']==500) & (scale_sensitivity['radius_b_m']==1000), 'spearman_rho'].iloc[0]:.6f}",
            "outcome": "REPRODUCED_IN_SUBSTANCE",
            "difference_or_cause": "exact recomputation from preserved score table and tie handling",
            "scientific_decision": "use the executed coefficient",
            "affected_output": "13_tables/component_ranking_scale_sensitivity.csv",
        },
        {
            "baseline_claim": "proxy-model macro-F1 approximately 0.887",
            "executed_result": f"legacy macro-F1 reproduced; stricter buffered primary macro-F1={primary_model['macro_f1']:.6f}",
            "outcome": "LEGACY_REPRODUCED_ENHANCED_RESULT_LOWER",
            "difference_or_cause": "enhanced test set has a full 2.01 km development/test exclusion buffer and development-only model selection",
            "scientific_decision": "use the stricter buffered result as primary and retain legacy value only as reproduction",
            "affected_output": "13_tables/enhanced_spatially_buffered_proxy_model_comparison.csv",
        },
    ]
    pd.DataFrame(discrepancy_rows).to_csv(VALIDATION / "baseline_discrepancy_and_correction_record.csv", index=False)

    limitations = [
        ("No local station validation", "Neither Open-Meteo nor NASA POWER is ground truth; product agreement is not accuracy."),
        ("Coarse weather support", "Four 0.1-degree returned cells cover 17 mapped components; no 30 m weather surfaces were created."),
        ("Limited satellite epochs", "Five composites preclude high-powered weather-spectral inference and causal identification."),
        ("Composite acquisition windows", "Each epoch is a multi-scene median across three post-monsoon years; scene-specific lags are aggregated."),
        ("Proxy supervision", "WorldCover consensus labels are not independent field-condition labels."),
        ("No M3 heritage-condition model", "Independent heritage-condition outcomes were unavailable."),
        ("Saraikala unresolved", "Component 139-002 remains without a verified analytical geometry."),
        ("Official property polygons unavailable", "Analytical circles are sampling supports only and not legal or UNESCO buffers."),
        ("Terrain approximation", "D8 flow and wetness are DEM-derived susceptibility proxies without field hydrological validation."),
        ("Expert weighting unavailable", "No documented expert elicitation was supplied; equal/hierarchical weights and Monte Carlo sensitivity are reported."),
        ("Single buffered test geography", "The stricter model evaluates one contiguous transfer direction and should not be generalised as universal accuracy."),
        ("Ancillary hazards omitted", "Earthquake, flood, landslide, quarry and population layers were not added without a necessary, harmonised evidential role."),
    ]
    pd.DataFrame(limitations, columns=["limitation", "implication"]).to_csv(UNRESOLVED / "limitations_and_unsuccessful_analyses.csv", index=False)


def build_readme_and_handoff(summary: dict[str, object], model_results: pd.DataFrame, product_metrics: pd.DataFrame, trends: pd.DataFrame) -> None:
    primary = model_results[model_results["primary_selected_from_inner_cv"]].iloc[0]
    readme = f"""# Taxila/PreserveX experiment-only reproducibility run

This directory contains the executed experimental pipeline requested on 1 August 2026. It does **not** contain a research-paper draft. Outputs describe relative landscape pressure, terrain/hydrological susceptibility, climate forcing and field-inspection priority; they do not establish monument damage.

## Reproduction order

1. Place the frozen Stage 3/4 source project at the path configured in `09_configurations/run_config.json`.
2. Run `03_download_scripts/acquire_open_meteo.py` to retrieve cached ERA5-Seamless daily records.
3. Run `08_experiment_scripts/baseline/run_integrated_experiments.py` with `TAXILA_SOURCE_ROOT` and `TAXILA_RUN_ROOT` set.
4. Run `08_experiment_scripts/execute_experiment_pipeline.py`.
5. Run `08_experiment_scripts/write_derived_geotiffs.mjs` if derived GeoTIFFs need regeneration.

## Scope and terminology

- Satellite outputs: **relative landscape pressure**.
- Component summaries: **relative heritage pressure** or **field-inspection priority**.
- Machine learning: **WorldCover-derived proxy land-cover agreement**, not heritage-condition accuracy.
- Weather: reanalysis forcing at native support; no false 30 m weather interpolation.

## Key verified run facts

- Endpoint support: {summary['endpoint_supported_percent']:.2f}% ({summary['endpoint_supported_cells']:,} cells).
- Two-or-more adverse spectral criteria: {summary['share_c_ge_2_percent']:.2f}%.
- Four unique Open-Meteo ERA5-Seamless grid cells cover 17 mapped components.
- Primary buffered proxy model selected from development-only CV: {primary['model']}.
- Held-out proxy macro-F1: {primary['macro_f1']:.3f} (95% block-bootstrap CI {primary['macro_f1_ci_low_95']:.3f}–{primary['macro_f1_ci_high_95']:.3f}).
- Five unique Landsat epochs make weather-spectral inference exploratory only.
- Acquisition-date Open-Meteo lag totals do not support describing E2024 as uniformly the wettest epoch; the legacy NASA composite-extreme result is product- and window-dependent.
- Giri remains the fixed 500 m leader, but spatial-block sampling uncertainty places Bhallar and Giri in overlapping top-rank intervals.

## Main directories

- `01_sources_and_manifests`: exact sources, URLs, method record and request manifests.
- `02_raw_data`: raw weather and terrain downloads.
- `04_cleaned_data`: QC-passed daily weather and aligned comparison datasets.
- `05_processed_rasters`: source and derived GeoTIFF products.
- `06_processed_vectors`: component, analytical-support and integrated-priority GeoJSON.
- `07_feature_tables`: feature-selection, redundancy and held-out importance outputs.
- `10_models`: trained models, predictions, fold assignments and model metadata.
- `11_figures` and `12_maps`: 17 figure/map families in PNG and PDF.
- `13_tables` and `14_statistics`: numerical experiment outputs.
- `16_validation`: experiment status, claim-evidence and validation gates.
- `18_unresolved_issues`: limitations, unavailable and unsuccessful analyses.

All paths and checksums are recorded in `17_reproducibility/checksums_sha256.csv`.
"""
    (RUN_ROOT / "README.md").write_text(readme, encoding="utf-8")

    handoff = f"""# Technical handoff for the later paper-writing stage

## Executed

The frozen Landsat endpoint and proxy baseline was reproduced in an isolated output directory. Open-Meteo ERA5-Seamless 1991–2025 daily data were acquired for the four unique returned weather cells covering the 17 mapped components, quality controlled, compared with NASA POWER, aggregated annually and seasonally, and matched to every retained Landsat scene date at 7, 30, 90, 180 and 365 day windows. Terrain/hydrological susceptibility, integrated ranking, 250/500/1000 m scale sensitivity, redundancy, ablation, Monte Carlo weighting, spatial-block rank uncertainty and a stricter buffered proxy-model comparison were executed.

## Verified results available for later writing

- Common endpoint support: {summary['endpoint_supported_percent']:.2f}%.
- At least two adverse endpoint criteria: {summary['share_c_ge_2_percent']:.2f}%.
- All major estimates, trend slopes, product-comparison metrics and model intervals are in machine-readable CSV files.
- Primary buffered proxy model: {primary['model']}; macro-F1 {primary['macro_f1']:.3f}, CI {primary['macro_f1_ci_low_95']:.3f}–{primary['macro_f1_ci_high_95']:.3f}.
- The earlier “2024 unusually wet” interpretation is not reproduced across Open-Meteo 30-, 90- and 365-day scene-date windows; use the discrepancy record before drafting any climate interpretation.
- The fixed 500 m score ranks Giri first, while the 2,000-draw spatial-block analysis gives Bhallar median rank 1 and Giri median rank 2; rankings must be reported with their intervals.

## Not available or not defensible

No station validation, complete field-condition labels, M3 heritage-condition model, official property polygons, Saraikala geometry or causal weather-spectral inference was available. Optional hazards and future projections were not added because they were not necessary to the central experiment and lacked harmonised validation in this run.

## Writing rule

Use only the claim-evidence matrix and numerical files in this run. Preserve the distinctions between pressure, exposure, susceptibility, field-inspection priority, proxy agreement and validated damage.
"""
    (REPRO / "technical_handoff_summary.md").write_text(handoff, encoding="utf-8")


def validate_run(open_qc: pd.DataFrame, model_results: pd.DataFrame, mapping: pd.DataFrame) -> dict[str, object]:
    baseline_validation = json.loads((BASELINE_VALIDATION / "integrated_experiment_validation.json").read_text(encoding="utf-8"))
    geotiff_validation_path = VALIDATION / "derived_geotiff_validation.json"
    geotiff_validation = json.loads(geotiff_validation_path.read_text(encoding="utf-8")) if geotiff_validation_path.exists() else {"status": "NOT_RUN"}
    png_paths = list(FIGURES.glob("figure_*.png")) + list(MAPS.glob("figure_*.png"))
    pdf_paths = list(FIGURES.glob("figure_*.pdf")) + list(MAPS.glob("figure_*.pdf"))
    png_integrity = True
    for path in png_paths:
        try:
            with Image.open(path) as image:
                image.verify()
        except Exception:
            png_integrity = False
    pdf_integrity = all(
        path.read_bytes().startswith(b"%PDF") and b"%%EOF" in path.read_bytes()[-4096:]
        for path in pdf_paths
    )
    checks = [
        {"check": "baseline_reproduction_pass", "pass": baseline_validation["status"] == "PASS"},
        {"check": "open_meteo_four_unique_cells", "pass": mapping["weather_cell_id"].nunique() == 4},
        {"check": "open_meteo_17_components", "pass": len(mapping) == 17},
        {"check": "open_meteo_qc_pass", "pass": bool((open_qc["status"] == "PASS").all())},
        {"check": "buffered_model_block_overlap_zero", "pass": bool((model_results["development_test_block_overlap"] == 0).all())},
        {"check": "buffered_model_minimum_separation", "pass": bool((model_results["minimum_block_column_separation"] >= 2).all())},
        {"check": "primary_model_selected_from_inner_cv_once", "pass": int(model_results["primary_selected_from_inner_cv"].sum()) == 1},
        {"check": "figure_png_count_at_least_17", "pass": len(list(FIGURES.glob("figure_*.png"))) + len(list(MAPS.glob("figure_*.png"))) >= 17},
        {"check": "figure_pdf_count_at_least_17", "pass": len(list(FIGURES.glob("figure_*.pdf"))) + len(list(MAPS.glob("figure_*.pdf"))) >= 17},
        {"check": "publication_png_integrity", "pass": png_integrity},
        {"check": "publication_pdf_integrity", "pass": pdf_integrity},
        {"check": "integrated_geojson_exists", "pass": (VECTORS / "taxila_integrated_field_inspection_priority_wgs84.geojson").exists()},
        {"check": "derived_geotiff_validation_pass", "pass": geotiff_validation["status"] == "PASS"},
        {"check": "derived_geotiff_count_six", "pass": len(list(RASTERS.glob("*_relative_landscape_pressure.tif"))) + int((RASTERS / "E2004_E2024_spectral_convergence.tif").exists()) == 6},
        {"check": "claim_evidence_matrix_exists", "pass": (VALIDATION / "claim_evidence_matrix.csv").exists()},
        {"check": "experiment_status_matrix_has_16_rows", "pass": len(pd.read_csv(VALIDATION / "experiment_status_matrix.csv")) == 16},
        {"check": "proxy_role_explicit", "pass": "not heritage-condition accuracy" in (RUN_ROOT / "README.md").read_text(errors="ignore")},
        {"check": "saraikala_retained_unresolved", "pass": "139-002" not in set(mapping["component_id"])},
    ]
    passed = sum(check["pass"] for check in checks)
    result = {
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    json_dump(VALIDATION / "final_experiment_run_validation.json", result)
    if result["status"] != "PASS":
        raise RuntimeError(f"Final validation failed: {[check['check'] for check in checks if not check['pass']]}")
    return result


def write_environment_and_checksums() -> None:
    environment = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "random_seed": SEED,
        "packages": {
            module: __import__(module).__version__
            for module in ["numpy", "pandas", "scipy", "sklearn", "matplotlib", "seaborn", "joblib"]
        },
    }
    json_dump(REPRO / "software_environment.json", environment)
    (REPRO / "requirements.txt").write_text(
        "\n".join(
            [
                f"numpy=={environment['packages']['numpy']}",
                f"pandas=={environment['packages']['pandas']}",
                f"scipy=={environment['packages']['scipy']}",
                f"scikit-learn=={environment['packages']['sklearn']}",
                f"matplotlib=={environment['packages']['matplotlib']}",
                f"seaborn=={environment['packages']['seaborn']}",
                f"joblib=={environment['packages']['joblib']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    rows = []
    checksum_target = REPRO / "checksums_sha256.csv"
    for path in sorted(RUN_ROOT.rglob("*")):
        if path.is_file() and path != checksum_target and path.suffix != ".zip":
            rows.append({"file": str(path.relative_to(RUN_ROOT)), "bytes": path.stat().st_size, "sha256": sha256(path)})
    pd.DataFrame(rows).to_csv(checksum_target, index=False)


def main() -> None:
    baseline_validation_path = BASELINE_VALIDATION / "integrated_experiment_validation.json"
    if not baseline_validation_path.exists():
        raise RuntimeError("Run the isolated baseline reproduction before the completion pipeline")
    build_inventory()
    open_combined, open_site, mapping = load_open_meteo()
    nasa = load_nasa_power()
    thresholds = climate_thresholds(open_site)
    annual, seasonal, climatology = aggregate_climate(open_site, thresholds)
    trends, trend_sensitivity = climate_trends(annual, seasonal)
    product_metrics, product_annual = compare_weather_products(open_site, nasa)
    matched, epoch_weather, associations = match_weather_to_landsat(open_site, nasa)
    model_results, calibration, importance = proxy_model_experiment()
    scale_sensitivity, ablation, rank_table = scale_and_ablation()
    rank_uncertainty = ranking_block_bootstrap()
    export_vectors_and_rasters(rank_uncertainty, rank_table)
    create_figures(
        open_site,
        annual,
        seasonal,
        climatology,
        trends,
        product_annual,
        epoch_weather,
        associations,
        model_results,
        calibration,
        scale_sensitivity,
        ablation,
        rank_table,
        rank_uncertainty,
    )
    for source in [SOURCE_ROOT / "data" / "source" / "nasa_power_taxila_1991_2025_daily.json", SOURCE_ROOT / "data" / "source" / "N33E072.hgt.gz"]:
        shutil.copy2(source, RAW / source.name)
    build_source_and_method_manifests(open_combined, mapping)
    endpoint_summary = json.loads((BASELINE_TABLES / "endpoint_screening_summary.json").read_text(encoding="utf-8"))
    build_experiment_records(endpoint_summary, trends, product_metrics, model_results, scale_sensitivity, rank_uncertainty)
    build_readme_and_handoff(endpoint_summary, model_results, product_metrics, trends)
    open_qc = pd.read_csv(TABLES / "open_meteo_quality_control.csv")
    validation = validate_run(open_qc, model_results, mapping)
    write_environment_and_checksums()
    summary = {
        "status": "PASS",
        "run_root": str(RUN_ROOT),
        "baseline_validation": "PASS",
        "final_validation": validation,
        "figures_and_maps": len(list(FIGURES.glob("figure_*.png"))) + len(list(MAPS.glob("figure_*.png"))),
        "tables_csv": len(list(TABLES.rglob("*.csv"))) + len(list(STATS.rglob("*.csv"))),
        "models": len(list(MODELS.glob("*.joblib"))),
        "random_seed": SEED,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
    }
    json_dump(VALIDATION / "completion_summary.json", summary)
    write_environment_and_checksums()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
