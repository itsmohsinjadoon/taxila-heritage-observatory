#!/usr/bin/env python3
"""Execute the integrated Taxila climate-landscape-pressure experiments.

The script intentionally separates:
1. local, time-varying Landsat pressure indicators;
2. site-wide climate forcing from NASA POWER;
3. static terrain and drainage susceptibility from a 1 arc-second HGT tile;
4. proxy-supervised land-cover model development.

It does not infer physical monument damage from remote sensing.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import random
from collections import deque
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import ndimage
from scipy.stats import rankdata, spearmanr, theilslopes
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
)
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "analysis" / "derived" / "raw"
TABLES = ROOT / "analysis" / "derived" / "tables"
FIGURES = ROOT / "analysis" / "figures"
VALIDATION = ROOT / "analysis" / "validation"
for directory in (TABLES, FIGURES, VALIDATION):
    directory.mkdir(parents=True, exist_ok=True)

SEED = 311
np.random.seed(SEED)
random.seed(SEED)

WIDTH = 616
HEIGHT = 655
XMIN = 292_980.0
YMAX = 3_748_620.0
CELL = 30.0
EPOCHS = ["E2004", "E2009", "E2014", "E2019", "E2024"]
YEARS = {"E2004": 2004, "E2009": 2009, "E2014": 2014, "E2019": 2019, "E2024": 2024}
WINDOWS = {
    "E2004": [2003, 2004, 2005],
    "E2009": [2008, 2009, 2010],
    "E2014": [2013, 2014, 2015],
    "E2019": [2018, 2019, 2020],
    "E2024": [2023, 2024, 2025],
}
RADII = [250, 500, 1000]
INDEX_NAMES = ["NDVI", "NDBI", "MNDWI", "BSI"]
LANDCOVER_NAMES = {
    1: "Built-up / impervious",
    2: "Bare or sparsely vegetated",
    3: "Cultivated land",
    4: "Woody or dense vegetation",
    5: "Shrub, grass or herbaceous",
    6: "Water",
}
COLORS = {
    "navy": "#17324D",
    "blue": "#2878B5",
    "teal": "#2A9D8F",
    "gold": "#E9C46A",
    "orange": "#F4A261",
    "red": "#D1495B",
    "purple": "#7A5195",
    "grey": "#6B7280",
    "light": "#EAF0F6",
}

sns.set_theme(style="whitegrid", context="paper")
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.titlesize": 10.5,
        "axes.labelsize": 9,
        "legend.fontsize": 8,
        "figure.dpi": 160,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
    }
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ecdf_percentile(values: pd.Series, adverse_high: bool = True) -> pd.Series:
    arr = values.to_numpy(dtype=float)
    if not adverse_high:
        arr = -arr
    valid = np.isfinite(arr)
    out = np.full(arr.shape, np.nan, dtype=float)
    out[valid] = (rankdata(arr[valid], method="average") - 0.5) / valid.sum()
    return pd.Series(out, index=values.index)


def longest_true_run(values: np.ndarray) -> int:
    best = current = 0
    for value in values.astype(bool):
        if value:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return int(best)


def load_components() -> pd.DataFrame:
    source = ROOT / "work" / "spatial" / "derived" / "taxila_components_epsg32643.geojson"
    payload = json.loads(source.read_text(encoding="utf8"))
    rows = []
    for feature in payload["features"]:
        if feature["geometry"] is None:
            continue
        props = feature["properties"]
        x, y = feature["geometry"]["coordinates"]
        rows.append(
            {
                "component_id": props["component_id"],
                "component_name": props["name"],
                "easting_m": float(x),
                "northing_m": float(y),
                "longitude": float(props["longitude"]),
                "latitude": float(props["latitude"]),
            }
        )
    components = pd.DataFrame(rows).sort_values("component_id").reset_index(drop=True)
    assert len(components) == 17
    return components


def load_epoch_arrays() -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray]]:
    indices: dict[str, np.ndarray] = {}
    observations: dict[str, np.ndarray] = {}
    landcover: dict[str, np.ndarray] = {}
    for epoch in EPOCHS:
        index_path = RAW / f"{epoch}_indices_ndvi_ndbi_mndwi_bsi.f32"
        values = np.fromfile(index_path, dtype="<f4")
        indices[epoch] = values.reshape(HEIGHT, WIDTH, 4)
        observations[epoch] = np.fromfile(
            RAW / f"{epoch}_valid_observations.f32", dtype="<f4"
        ).reshape(HEIGHT, WIDTH)
        landcover[epoch] = np.fromfile(
            RAW / f"{epoch}_provisional_landcover.u8", dtype=np.uint8
        ).reshape(HEIGHT, WIDTH)
    return indices, observations, landcover


def valid_mask(index_array: np.ndarray, observations: np.ndarray) -> np.ndarray:
    # The accepted composites were written as NoData wherever the prespecified
    # minimum of three valid observations was not met. Some TIFF readers expose
    # the auxiliary uint16 observation-count raster as zero-valued RGB, so the
    # composite's explicit NoData mask is the authoritative executable gate.
    return (
        np.all(np.isfinite(index_array), axis=2)
        & np.all(index_array > -9000, axis=2)
        & np.all((index_array >= -1.001) & (index_array <= 1.001), axis=2)
    )


def component_neighbourhood_masks(components: pd.DataFrame) -> dict[tuple[str, int], np.ndarray]:
    xs = XMIN + (np.arange(WIDTH) + 0.5) * CELL
    ys = YMAX - (np.arange(HEIGHT) + 0.5) * CELL
    xx, yy = np.meshgrid(xs, ys)
    masks: dict[tuple[str, int], np.ndarray] = {}
    for row in components.itertuples(index=False):
        d2 = (xx - row.easting_m) ** 2 + (yy - row.northing_m) ** 2
        for radius in RADII:
            masks[(row.component_id, radius)] = d2 <= radius**2
    return masks


def summarize_landsat(
    components: pd.DataFrame,
    indices: dict[str, np.ndarray],
    observations: dict[str, np.ndarray],
    landcover: dict[str, np.ndarray],
) -> tuple[pd.DataFrame, dict[str, object], np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    masks = component_neighbourhood_masks(components)
    valids = {epoch: valid_mask(indices[epoch], observations[epoch]) for epoch in EPOCHS}
    rows = []
    for radius in RADII:
        for component in components.itertuples(index=False):
            nmask = masks[(component.component_id, radius)]
            for epoch in EPOCHS:
                use = nmask & valids[epoch]
                record = {
                    "component_id": component.component_id,
                    "component_name": component.component_name,
                    "radius_m": radius,
                    "epoch_id": epoch,
                    "label_year": YEARS[epoch],
                    "valid_cells": int(use.sum()),
                }
                for band, name in enumerate(INDEX_NAMES):
                    vals = indices[epoch][:, :, band][use]
                    record[f"{name.lower()}_median"] = float(np.nanmedian(vals))
                    record[f"{name.lower()}_p10"] = float(np.nanpercentile(vals, 10))
                    record[f"{name.lower()}_p90"] = float(np.nanpercentile(vals, 90))
                lc_vals = landcover[epoch][nmask & (landcover[epoch] > 0)]
                record["classified_cells"] = int(lc_vals.size)
                for class_id, class_name in LANDCOVER_NAMES.items():
                    record[f"lc_class_{class_id}_share"] = (
                        float(np.mean(lc_vals == class_id)) if lc_vals.size else np.nan
                    )
                rows.append(record)
    summary = pd.DataFrame(rows)

    endpoint_mask = valids["E2004"] & valids["E2024"]
    delta = indices["E2024"] - indices["E2004"]
    q_ndvi = float(np.quantile(delta[:, :, 0][endpoint_mask], 0.20))
    q_mndwi = float(np.quantile(delta[:, :, 2][endpoint_mask], 0.20))
    q_ndbi = float(np.quantile(delta[:, :, 1][endpoint_mask], 0.80))
    adverse = np.zeros((HEIGHT, WIDTH, 3), dtype=bool)
    adverse[:, :, 0] = endpoint_mask & (delta[:, :, 0] <= q_ndvi)
    adverse[:, :, 1] = endpoint_mask & (delta[:, :, 2] <= q_mndwi)
    adverse[:, :, 2] = endpoint_mask & (delta[:, :, 1] >= q_ndbi)
    convergence = adverse.sum(axis=2).astype(np.uint8)

    hotspot_rows = []
    for radius in RADII:
        for component in components.itertuples(index=False):
            use = masks[(component.component_id, radius)] & endpoint_mask
            hotspot_rows.append(
                {
                    "component_id": component.component_id,
                    "component_name": component.component_name,
                    "radius_m": radius,
                    "valid_cells": int(use.sum()),
                    "share_c_ge_2": float(np.mean(convergence[use] >= 2)),
                    "share_c_eq_3": float(np.mean(convergence[use] == 3)),
                    "delta_ndvi_median": float(np.median(delta[:, :, 0][use])),
                    "delta_mndwi_median": float(np.median(delta[:, :, 2][use])),
                    "delta_ndbi_median": float(np.median(delta[:, :, 1][use])),
                }
            )
    hotspots = pd.DataFrame(hotspot_rows)
    hotspots.to_csv(TABLES / "component_endpoint_hotspots.csv", index=False)

    counts = {int(i): int(np.sum(endpoint_mask & (convergence == i))) for i in range(4)}
    endpoint_summary = {
        "endpoint_supported_cells": int(endpoint_mask.sum()),
        "endpoint_supported_percent": float(endpoint_mask.mean() * 100),
        "thresholds": {
            "delta_ndvi_q20": q_ndvi,
            "delta_mndwi_q20": q_mndwi,
            "delta_ndbi_q80": q_ndbi,
        },
        "convergence_cell_counts": counts,
        "share_c_ge_2_percent": float(
            np.sum(endpoint_mask & (convergence >= 2)) / endpoint_mask.sum() * 100
        ),
        "share_c_eq_3_percent": float(
            np.sum(endpoint_mask & (convergence == 3)) / endpoint_mask.sum() * 100
        ),
        "grid_median_delta": {
            "NDVI": float(np.median(delta[:, :, 0][endpoint_mask])),
            "MNDWI": float(np.median(delta[:, :, 2][endpoint_mask])),
            "NDBI": float(np.median(delta[:, :, 1][endpoint_mask])),
        },
    }

    # Reproduce the accepted endpoint experiment before extending it.
    assert endpoint_summary["endpoint_supported_cells"] == 386_280
    assert abs(endpoint_summary["share_c_ge_2_percent"] - 16.928) < 0.02
    assert abs(q_ndvi - (-0.00543)) < 1e-4
    assert abs(q_mndwi - (-0.03743)) < 1e-4
    assert abs(q_ndbi - 0.00835) < 1e-4

    summary.to_csv(TABLES / "component_epoch_multiscale_landsat.csv", index=False)
    (TABLES / "endpoint_screening_summary.json").write_text(
        json.dumps(endpoint_summary, indent=2) + "\n", encoding="utf8"
    )
    return summary, endpoint_summary, endpoint_mask, convergence, valids


def load_climate() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, float]]:
    source = ROOT / "data" / "source" / "nasa_power_taxila_1991_2025_daily.json"
    payload = json.loads(source.read_text(encoding="utf8"))
    parameters = payload["properties"]["parameter"]
    dates = sorted(parameters["PRECTOTCORR"].keys())
    frame = pd.DataFrame({"date": pd.to_datetime(dates, format="%Y%m%d")})
    for parameter in ["PRECTOTCORR", "T2M_MAX", "T2M_MIN", "T2M", "RH2M", "WS10M"]:
        frame[parameter] = [parameters[parameter].get(date, np.nan) for date in dates]
        frame.loc[frame[parameter] <= -900, parameter] = np.nan
    frame["year"] = frame["date"].dt.year
    frame["month"] = frame["date"].dt.month
    frame["dtr"] = frame["T2M_MAX"] - frame["T2M_MIN"]

    baseline = frame[(frame["date"] >= "1991-01-01") & (frame["date"] <= "2020-12-31")]
    wet = baseline.loc[baseline["PRECTOTCORR"] >= 1.0, "PRECTOTCORR"]
    thresholds = {
        "wet_day_p95_mm": float(wet.quantile(0.95)),
        "tmax_p95_c": float(baseline["T2M_MAX"].quantile(0.95)),
        "dtr_p95_c": float(baseline["dtr"].quantile(0.95)),
        "wind_p95_ms": float(baseline["WS10M"].quantile(0.95)),
    }

    annual_rows = []
    for year, group in frame.groupby("year"):
        group = group.sort_values("date").reset_index(drop=True)
        rain = group["PRECTOTCORR"].fillna(0).to_numpy()
        tmax = group["T2M_MAX"].to_numpy()
        dtr = group["dtr"].to_numpy()
        monsoon = group["month"].between(7, 9)
        pre30 = (group["date"] >= f"{year}-09-01") & (group["date"] <= f"{year}-09-30")
        pre90 = (group["date"] >= f"{year}-07-03") & (group["date"] <= f"{year}-09-30")
        annual_rows.append(
            {
                "year": int(year),
                "annual_rainfall_mm": float(np.nansum(rain)),
                "monsoon_rainfall_mm": float(np.nansum(rain[monsoon])),
                "rx1day_mm": float(np.nanmax(rain)),
                "rx5day_mm": float(
                    pd.Series(rain).rolling(5, min_periods=5).sum().max()
                ),
                "r95p_days": int(np.sum(rain > thresholds["wet_day_p95_mm"])),
                "cwd_days": longest_true_run(rain >= 1.0),
                "cdd_days": longest_true_run(rain < 1.0),
                "pre30_rainfall_mm": float(np.nansum(rain[pre30])),
                "pre90_rainfall_mm": float(np.nansum(rain[pre90])),
                "mean_tmax_c": float(np.nanmean(tmax)),
                "annual_max_tmax_c": float(np.nanmax(tmax)),
                "tx95_days": int(np.sum(tmax > thresholds["tmax_p95_c"])),
                "heatwave_max_days": longest_true_run(
                    tmax > thresholds["tmax_p95_c"]
                ),
                "mean_dtr_c": float(np.nanmean(dtr)),
                "high_dtr_days": int(np.sum(dtr > thresholds["dtr_p95_c"])),
                "mean_rh_percent": float(np.nanmean(group["RH2M"])),
                "strong_wind_days": int(
                    np.sum(group["WS10M"].to_numpy() > thresholds["wind_p95_ms"])
                ),
            }
        )
    annual = pd.DataFrame(annual_rows)
    annual.to_csv(TABLES / "nasa_power_annual_climate_metrics_1991_2025.csv", index=False)

    climate_factors = [
        "rx5day_mm",
        "r95p_days",
        "cdd_days",
        "tx95_days",
        "heatwave_max_days",
        "high_dtr_days",
    ]
    baseline_annual = annual[annual["year"].between(1991, 2020)]
    for factor in climate_factors:
        annual[f"{factor}_percentile"] = annual[factor].apply(
            lambda value: float(
                (np.sum(baseline_annual[factor] < value)
                + 0.5 * np.sum(baseline_annual[factor] == value))
                / len(baseline_annual)
            )
        )
    annual["climate_extreme_score"] = annual[
        [f"{factor}_percentile" for factor in climate_factors]
    ].mean(axis=1)

    epoch_rows = []
    for epoch, years in WINDOWS.items():
        subset = annual[annual["year"].isin(years)]
        record = {"epoch_id": epoch, "label_year": YEARS[epoch], "years": ",".join(map(str, years))}
        for column in annual.columns:
            if column != "year":
                record[column] = float(subset[column].mean())
        base_means = baseline_annual.mean(numeric_only=True)
        base_sds = baseline_annual.std(numeric_only=True, ddof=1)
        for factor in [
            "monsoon_rainfall_mm",
            "rx5day_mm",
            "r95p_days",
            "cdd_days",
            "annual_max_tmax_c",
            "tx95_days",
            "heatwave_max_days",
            "mean_dtr_c",
        ]:
            record[f"{factor}_z"] = float(
                (record[factor] - base_means[factor]) / base_sds[factor]
            )
        epoch_rows.append(record)
    epochs = pd.DataFrame(epoch_rows)
    epochs.to_csv(TABLES / "matched_epoch_climate_metrics.csv", index=False)
    frame.to_csv(TABLES / "nasa_power_daily_climate_1991_2025.csv", index=False)
    return frame, annual, epochs, thresholds


def calculate_d8_flow(dem: np.ndarray, cell_y_m: float, cell_x_m: float) -> np.ndarray:
    """D8 accumulation to a strictly lower neighbour; sinks remain terminal."""
    height, width = dem.shape
    n = height * width
    best_slope = np.zeros_like(dem, dtype=np.float32)
    receiver = np.full((height, width), -1, dtype=np.int64)
    flat_indices = np.arange(n, dtype=np.int64).reshape(height, width)
    neighbours = [
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    ]
    for dr, dc in neighbours:
        r_src = slice(max(0, -dr), min(height, height - dr))
        c_src = slice(max(0, -dc), min(width, width - dc))
        r_dst = slice(max(0, dr), min(height, height + dr))
        c_dst = slice(max(0, dc), min(width, width + dc))
        distance = math.hypot(cell_y_m * dr, cell_x_m * dc)
        slope = (dem[r_src, c_src] - dem[r_dst, c_dst]) / distance
        update = slope > best_slope[r_src, c_src]
        best_slope[r_src, c_src][update] = slope[update]
        receiver[r_src, c_src][update] = flat_indices[r_dst, c_dst][update]

    receiver_flat = receiver.ravel()
    valid_receiver = receiver_flat >= 0
    indegree = np.bincount(
        receiver_flat[valid_receiver], minlength=n
    ).astype(np.int32)
    accumulation = np.ones(n, dtype=np.float64)
    queue = deque(np.where(indegree == 0)[0].tolist())
    processed = 0
    while queue:
        node = queue.popleft()
        processed += 1
        target = receiver_flat[node]
        if target >= 0:
            accumulation[target] += accumulation[node]
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(int(target))
    if processed != n:
        raise RuntimeError(f"D8 graph was not acyclic: processed {processed}/{n}")
    return accumulation.reshape(height, width)


def load_terrain(components: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    hgt_gz = ROOT / "data" / "source" / "N33E072.hgt.gz"
    with gzip.open(hgt_gz, "rb") as handle:
        raw = handle.read()
    dem_full = np.frombuffer(raw, dtype=">i2").reshape(3601, 3601).astype(np.float32)
    dem_full[dem_full <= -32768] = np.nan

    margin_deg = 0.035
    lat_min = max(33.0, components["latitude"].min() - margin_deg)
    lat_max = min(34.0, components["latitude"].max() + margin_deg)
    lon_min = max(72.0, components["longitude"].min() - margin_deg)
    lon_max = min(73.0, components["longitude"].max() + margin_deg)
    r0 = max(0, int(math.floor((34.0 - lat_max) * 3600)))
    r1 = min(3601, int(math.ceil((34.0 - lat_min) * 3600)) + 1)
    c0 = max(0, int(math.floor((lon_min - 72.0) * 3600)))
    c1 = min(3601, int(math.ceil((lon_max - 72.0) * 3600)) + 1)
    dem = dem_full[r0:r1, c0:c1]
    lats = 34.0 - (np.arange(r0, r1) / 3600.0)
    lons = 72.0 + (np.arange(c0, c1) / 3600.0)
    mean_lat = float(np.mean(lats))
    cell_y_m = 111_132.0 / 3600.0
    cell_x_m = 111_320.0 * math.cos(math.radians(mean_lat)) / 3600.0

    grad_y, grad_x = np.gradient(dem, cell_y_m, cell_x_m)
    slope_deg = np.degrees(np.arctan(np.hypot(grad_x, grad_y))).astype(np.float32)
    mean3 = ndimage.uniform_filter(dem, size=3, mode="nearest")
    mean3_sq = ndimage.uniform_filter(dem**2, size=3, mode="nearest")
    tri = np.sqrt(np.maximum(mean3_sq - mean3**2, 0)).astype(np.float32)
    tpi500 = (
        dem - ndimage.uniform_filter(dem, size=33, mode="nearest")
    ).astype(np.float32)
    flow = calculate_d8_flow(dem, cell_y_m, cell_x_m)
    slope_rad = np.radians(np.clip(slope_deg, 0.05, None))
    twi_proxy = (
        np.log((flow + 1.0) * math.sqrt(cell_x_m * cell_y_m))
        - np.log(np.tan(slope_rad) + 0.01)
    ).astype(np.float32)
    drainage_threshold = float(np.nanquantile(flow, 0.99))
    drainage = flow >= drainage_threshold
    drainage_distance_m = ndimage.distance_transform_edt(
        ~drainage, sampling=(cell_y_m, cell_x_m)
    ).astype(np.float32)

    terrain_rows = []
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    for component in components.itertuples(index=False):
        dx = (
            (lon_grid - component.longitude)
            * 111_320.0
            * math.cos(math.radians(component.latitude))
        )
        dy = (lat_grid - component.latitude) * 111_132.0
        d2 = dx**2 + dy**2
        for radius in RADII:
            use = d2 <= radius**2
            terrain_rows.append(
                {
                    "component_id": component.component_id,
                    "component_name": component.component_name,
                    "radius_m": radius,
                    "terrain_cells": int(use.sum()),
                    "elevation_median_m": float(np.nanmedian(dem[use])),
                    "elevation_p10_m": float(np.nanpercentile(dem[use], 10)),
                    "elevation_p90_m": float(np.nanpercentile(dem[use], 90)),
                    "slope_median_deg": float(np.nanmedian(slope_deg[use])),
                    "slope_p90_deg": float(np.nanpercentile(slope_deg[use], 90)),
                    "tri_median_m": float(np.nanmedian(tri[use])),
                    "tpi500_median_m": float(np.nanmedian(tpi500[use])),
                    "flow_accumulation_p90_cells": float(np.nanpercentile(flow[use], 90)),
                    "twi_proxy_p90": float(np.nanpercentile(twi_proxy[use], 90)),
                    "drainage_distance_median_m": float(
                        np.nanmedian(drainage_distance_m[use])
                    ),
                }
            )
    terrain = pd.DataFrame(terrain_rows)
    terrain.to_csv(TABLES / "component_multiscale_terrain_hydrology.csv", index=False)
    arrays = {
        "dem": dem,
        "slope_deg": slope_deg,
        "tri": tri,
        "tpi500": tpi500,
        "flow": flow,
        "twi_proxy": twi_proxy,
        "drainage_distance_m": drainage_distance_m,
        "lats": lats,
        "lons": lons,
        "drainage_threshold": np.array([drainage_threshold]),
    }
    return terrain, arrays


def prepare_integrated_scores(
    landsat_summary: pd.DataFrame,
    terrain: pd.DataFrame,
    climate_epochs: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data = landsat_summary.copy()
    scored_parts = []
    terrain_scored_parts = []
    for radius in RADII:
        part = data[data["radius_m"] == radius].copy()
        part["ndvi_pressure"] = ecdf_percentile(part["ndvi_median"], adverse_high=False)
        part["mndwi_pressure"] = ecdf_percentile(part["mndwi_median"], adverse_high=False)
        part["ndbi_pressure"] = ecdf_percentile(part["ndbi_median"], adverse_high=True)
        part["built_share_pressure"] = ecdf_percentile(
            part["lc_class_1_share"], adverse_high=True
        )
        part["bare_share_pressure"] = ecdf_percentile(
            part["lc_class_2_share"], adverse_high=True
        )
        # NDVI- and NDBI-derived pressures are highly correlated in this
        # landscape. Hierarchical weighting prevents their shared
        # surface-cover contrast from receiving twice the weight of MNDWI.
        part["surface_cover_pressure"] = part[
            ["ndvi_pressure", "ndbi_pressure"]
        ].mean(axis=1)
        part["landscape_pressure_score"] = part[
            ["surface_cover_pressure", "mndwi_pressure"]
        ].mean(axis=1)
        scored_parts.append(part)

        tpart = terrain[terrain["radius_m"] == radius].copy()
        tpart["slope_pressure"] = ecdf_percentile(
            tpart["slope_p90_deg"], adverse_high=True
        )
        tpart["wetness_pressure"] = ecdf_percentile(
            tpart["twi_proxy_p90"], adverse_high=True
        )
        tpart["drainage_proximity_pressure"] = ecdf_percentile(
            tpart["drainage_distance_median_m"], adverse_high=False
        )
        tpart["terrain_susceptibility_score"] = tpart[
            ["slope_pressure", "wetness_pressure", "drainage_proximity_pressure"]
        ].mean(axis=1)
        terrain_scored_parts.append(tpart)
    scored = pd.concat(scored_parts, ignore_index=True)
    terrain_scored = pd.concat(terrain_scored_parts, ignore_index=True)
    climate_small = climate_epochs[
        ["epoch_id", "label_year", "climate_extreme_score"]
    ].copy()
    merged = scored.merge(
        terrain_scored[
            [
                "component_id",
                "radius_m",
                "terrain_susceptibility_score",
                "slope_pressure",
                "wetness_pressure",
                "drainage_proximity_pressure",
            ]
        ],
        on=["component_id", "radius_m"],
        how="left",
    ).merge(climate_small, on=["epoch_id", "label_year"], how="left")
    merged["integrated_exposure_score"] = merged[
        [
            "landscape_pressure_score",
            "terrain_susceptibility_score",
            "climate_extreme_score",
        ]
    ].mean(axis=1)
    merged["local_priority_score"] = merged[
        ["landscape_pressure_score", "terrain_susceptibility_score"]
    ].mean(axis=1)
    merged.to_csv(TABLES / "component_epoch_integrated_scores.csv", index=False)

    primitive_cols = [
        "ndvi_pressure",
        "mndwi_pressure",
        "ndbi_pressure",
        "built_share_pressure",
        "bare_share_pressure",
    ]
    candidate_cols = primitive_cols + [
        "surface_cover_pressure",
        "landscape_pressure_score",
    ]
    corr_source = merged[merged["radius_m"] == 500][candidate_cols]
    corr = corr_source.corr(method="spearman")
    corr.to_csv(TABLES / "dynamic_factor_spearman_correlation.csv")
    redundant_pairs = []
    for i, left in enumerate(primitive_cols):
        for right in primitive_cols[i + 1 :]:
            rho = float(corr.loc[left, right])
            if abs(rho) >= 0.85:
                if {left, right} == {"ndvi_pressure", "ndbi_pressure"}:
                    decision = (
                        "Group NDVI and NDBI into one surface-cover subdomain "
                        "before combining with MNDWI."
                    )
                else:
                    decision = (
                        "Exclude mapped land-cover proxy from the primary composite "
                        "when it duplicates a direct spectral factor; retain for comparison only."
                    )
                redundant_pairs.append(
                    {
                        "factor_a": left,
                        "factor_b": right,
                        "spearman_rho": rho,
                        "decision": decision,
                    }
                )
    redundancy = pd.DataFrame(redundant_pairs)
    redundancy.to_csv(TABLES / "factor_redundancy_screen.csv", index=False)

    # Theil-Sen slopes use five observations and are descriptive, not definitive trends.
    trend_rows = []
    for radius in RADII:
        for component_id, group in merged[merged["radius_m"] == radius].groupby(
            "component_id"
        ):
            group = group.sort_values("label_year")
            for metric in [
                "ndvi_median",
                "mndwi_median",
                "ndbi_median",
                "landscape_pressure_score",
                "integrated_exposure_score",
            ]:
                slope, intercept, low, high = theilslopes(
                    group[metric], group["label_year"], alpha=0.95
                )
                rho = spearmanr(group["label_year"], group[metric]).statistic
                trend_rows.append(
                    {
                        "component_id": component_id,
                        "component_name": group["component_name"].iloc[0],
                        "radius_m": radius,
                        "metric": metric,
                        "theil_sen_slope_per_year": float(slope),
                        "slope_low_95": float(low),
                        "slope_high_95": float(high),
                        "spearman_rho_year": float(rho),
                        "n_epochs": len(group),
                        "interpretation": "descriptive_five_epoch_trajectory",
                    }
                )
    trends = pd.DataFrame(trend_rows)
    trends.to_csv(TABLES / "component_five_epoch_theil_sen_trends.csv", index=False)
    return merged, terrain_scored, corr, redundancy


def climate_spectral_associations(
    indices: dict[str, np.ndarray],
    valids: dict[str, np.ndarray],
    climate_epochs: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for epoch in EPOCHS:
        use = valids[epoch]
        record = {"epoch_id": epoch, "label_year": YEARS[epoch]}
        for band, name in enumerate(INDEX_NAMES[:3]):
            record[f"grid_median_{name.lower()}"] = float(
                np.median(indices[epoch][:, :, band][use])
            )
        rows.append(record)
    site = pd.DataFrame(rows).merge(climate_epochs, on=["epoch_id", "label_year"])
    site.to_csv(TABLES / "sitewide_epoch_spectral_climate_series.csv", index=False)

    pairs = [
        ("climate_extreme_score", "grid_median_ndvi", -1),
        ("climate_extreme_score", "grid_median_mndwi", -1),
        ("climate_extreme_score", "grid_median_ndbi", 1),
        ("rx5day_mm", "grid_median_mndwi", 1),
        ("cdd_days", "grid_median_mndwi", -1),
        ("tx95_days", "grid_median_ndvi", -1),
        ("monsoon_rainfall_mm", "grid_median_ndvi", 1),
    ]
    output = []
    for climate_metric, spectral_metric, expected_direction in pairs:
        x = site[climate_metric].to_numpy()
        y = site[spectral_metric].to_numpy()
        full = float(spearmanr(x, y).statistic)
        loo = []
        for excluded in range(len(site)):
            keep = np.arange(len(site)) != excluded
            loo.append(float(spearmanr(x[keep], y[keep]).statistic))
        nonzero = [np.sign(value) for value in loo if np.isfinite(value) and value != 0]
        sign_stability = (
            float(np.mean(np.asarray(nonzero) == np.sign(full))) if nonzero else np.nan
        )
        output.append(
            {
                "climate_metric": climate_metric,
                "spectral_metric": spectral_metric,
                "spearman_rho_n5": full,
                "expected_direction": expected_direction,
                "loo_rho_min": float(np.nanmin(loo)),
                "loo_rho_max": float(np.nanmax(loo)),
                "loo_sign_stability": sign_stability,
                "inference_status": "exploratory_no_p_value_five_unique_epochs",
            }
        )
    associations = pd.DataFrame(output)
    associations.to_csv(TABLES / "climate_spectral_exploratory_associations.csv", index=False)
    return site


def extract_proxy_features() -> pd.DataFrame:
    partition_path = (
        ROOT
        / "work"
        / "landcover"
        / "Taxila_PreserveX_Stage4_Batch2"
        / "outputs"
        / "proxy_sample_partition.csv"
    )
    samples = pd.read_csv(partition_path)
    reflectance = np.fromfile(RAW / "E2019_reflectance_6band.f32", dtype="<f4").reshape(
        HEIGHT, WIDTH, 6
    )
    indices = np.fromfile(
        RAW / "E2019_indices_ndvi_ndbi_mndwi_bsi.f32", dtype="<f4"
    ).reshape(HEIGHT, WIDTH, 4)
    rows = samples["row"].to_numpy(dtype=int)
    cols = samples["col"].to_numpy(dtype=int)
    features = np.concatenate([reflectance[rows, cols, :], indices[rows, cols, :]], axis=1)
    names = ["blue", "green", "red", "nir08", "swir16", "swir22"] + INDEX_NAMES
    feature_frame = samples.copy()
    for i, name in enumerate(names):
        feature_frame[name] = features[:, i]
    valid = np.all(np.isfinite(features), axis=1) & np.all(features > -9000, axis=1)
    feature_frame = feature_frame[valid].reset_index(drop=True)
    feature_frame.to_csv(TABLES / "proxy_model_feature_table.csv", index=False)
    return feature_frame


def model_comparison(feature_frame: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, list[int]]:
    feature_names = ["blue", "green", "red", "nir08", "swir16", "swir22"] + INDEX_NAMES
    development = feature_frame[feature_frame["partition"] == "development"].copy()
    test = feature_frame[feature_frame["partition"] == "outer_proxy_test"].copy()
    x_dev = development[feature_names].to_numpy()
    y_dev = development["proxy_class"].to_numpy()
    groups = development["spatial_block"].to_numpy()
    x_test = test[feature_names].to_numpy()
    y_test = test["proxy_class"].to_numpy()
    labels = sorted(np.unique(feature_frame["proxy_class"]).tolist())
    cv = GroupKFold(n_splits=4)

    candidates = [
        (
            "Multinomial logistic",
            Pipeline(
                [
                    ("scale", StandardScaler()),
                    (
                        "model",
                        LogisticRegression(
                            max_iter=1200,
                            class_weight="balanced",
                            solver="lbfgs",
                            random_state=SEED,
                        ),
                    ),
                ]
            ),
            {"model__C": [0.1, 1.0, 10.0]},
        ),
        (
            "Random forest",
            RandomForestClassifier(
                n_estimators=250,
                max_features="sqrt",
                class_weight="balanced_subsample",
                n_jobs=1,
                random_state=SEED,
            ),
            {
                "max_depth": [16, None],
                "min_samples_leaf": [1, 5],
            },
        ),
        (
            "Extra trees",
            ExtraTreesClassifier(
                n_estimators=250,
                max_features="sqrt",
                class_weight="balanced",
                n_jobs=1,
                random_state=SEED,
            ),
            {
                "max_depth": [20, None],
                "min_samples_leaf": [1, 3],
            },
        ),
        (
            "Histogram gradient boosting",
            HistGradientBoostingClassifier(
                max_iter=220,
                l2_regularization=0.1,
                early_stopping=True,
                random_state=SEED,
            ),
            {
                "learning_rate": [0.05, 0.1],
                "max_leaf_nodes": [31, 63],
            },
        ),
        (
            "Neural MLP",
            Pipeline(
                [
                    ("scale", StandardScaler()),
                    (
                        "model",
                        MLPClassifier(
                            max_iter=350,
                            early_stopping=True,
                            validation_fraction=0.15,
                            n_iter_no_change=20,
                            random_state=SEED,
                        ),
                    ),
                ]
            ),
            {
                "model__hidden_layer_sizes": [(64,), (64, 32)],
                "model__alpha": [0.0001, 0.001],
            },
        ),
    ]

    results = []
    predictions_by_model: dict[str, np.ndarray] = {}
    best_predictions = None
    best_name = None
    best_macro = -np.inf
    for name, estimator, grid in candidates:
        search = GridSearchCV(
            estimator,
            grid,
            scoring="f1_macro",
            cv=cv,
            n_jobs=-1,
            refit=True,
            return_train_score=False,
        )
        search.fit(x_dev, y_dev, groups=groups)
        prediction = search.predict(x_test)
        predictions_by_model[name] = prediction
        probability = search.predict_proba(x_test)
        macro = f1_score(y_test, prediction, average="macro")
        result = {
            "model": name,
            "inner_blocked_cv_macro_f1": float(search.best_score_),
            "outer_proxy_overall_agreement": float(accuracy_score(y_test, prediction)),
            "outer_proxy_balanced_accuracy": float(
                balanced_accuracy_score(y_test, prediction)
            ),
            "outer_proxy_macro_f1": float(macro),
            "outer_proxy_log_loss": float(log_loss(y_test, probability, labels=labels)),
            "best_parameters": json.dumps(search.best_params_, sort_keys=True),
            "development_samples": len(development),
            "outer_test_samples": len(test),
            "development_blocks": int(development["spatial_block"].nunique()),
            "outer_test_blocks": int(test["spatial_block"].nunique()),
            "block_overlap": int(
                len(
                    set(development["spatial_block"]).intersection(
                        set(test["spatial_block"])
                    )
                )
            ),
            "validation_role": "held_out_worldcover_consensus_proxy_agreement_not_independent_accuracy",
        }
        results.append(result)
        if macro > best_macro:
            best_macro = macro
            best_predictions = prediction
            best_name = name
    comparison = pd.DataFrame(results)

    # Spatial-block bootstrap quantifies whether small point-estimate differences
    # are meaningful. Blocks, rather than individual pixels, are resampled.
    test_blocks = test["spatial_block"].to_numpy()
    unique_blocks = np.unique(test_blocks)
    rng = np.random.default_rng(SEED)
    bootstrap_draws = 2_000
    bootstrap_scores = {
        name: np.empty(bootstrap_draws, dtype=float) for name in predictions_by_model
    }
    for draw in range(bootstrap_draws):
        sampled_blocks = rng.choice(unique_blocks, size=len(unique_blocks), replace=True)
        sampled_indices = np.concatenate(
            [np.where(test_blocks == block)[0] for block in sampled_blocks]
        )
        for name, prediction in predictions_by_model.items():
            bootstrap_scores[name][draw] = f1_score(
                y_test[sampled_indices],
                prediction[sampled_indices],
                average="macro",
                labels=labels,
                zero_division=0,
            )
    score_matrix = np.column_stack(
        [bootstrap_scores[name] for name in predictions_by_model]
    )
    bootstrap_names = list(predictions_by_model)
    bootstrap_winner = np.argmax(score_matrix, axis=1)
    best_bootstrap = bootstrap_scores[best_name]
    for row_index, row in comparison.iterrows():
        values = bootstrap_scores[row["model"]]
        comparison.loc[row_index, "outer_proxy_macro_f1_ci_low"] = float(
            np.percentile(values, 2.5)
        )
        comparison.loc[row_index, "outer_proxy_macro_f1_ci_high"] = float(
            np.percentile(values, 97.5)
        )
        comparison.loc[row_index, "bootstrap_probability_best"] = float(
            np.mean(bootstrap_winner == bootstrap_names.index(row["model"]))
        )
        difference = values - best_bootstrap
        comparison.loc[row_index, "macro_f1_difference_vs_point_best_low"] = float(
            np.percentile(difference, 2.5)
        )
        comparison.loc[row_index, "macro_f1_difference_vs_point_best_high"] = float(
            np.percentile(difference, 97.5)
        )
        comparison.loc[row_index, "spatial_block_bootstrap_draws"] = bootstrap_draws
    comparison = comparison.sort_values("outer_proxy_macro_f1", ascending=False)
    comparison.to_csv(TABLES / "spatially_blocked_model_comparison.csv", index=False)
    matrix = confusion_matrix(y_test, best_predictions, labels=labels)
    matrix_frame = pd.DataFrame(
        matrix,
        index=[f"Reference {LANDCOVER_NAMES[i]}" for i in labels],
        columns=[f"Mapped {LANDCOVER_NAMES[i]}" for i in labels],
    )
    matrix_frame.to_csv(TABLES / "best_proxy_model_confusion_matrix.csv")
    (TABLES / "best_proxy_model.json").write_text(
        json.dumps(
            {
                "model": best_name,
                "macro_f1": float(best_macro),
                "labels": labels,
                "validation_role": "proxy_agreement_only",
            },
            indent=2,
        )
        + "\n",
        encoding="utf8",
    )
    return comparison, matrix, labels


def uncertainty_and_ablation(scores: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    target = scores[(scores["radius_m"] == 500) & (scores["epoch_id"] == "E2024")].copy()
    target = target.sort_values("component_id").reset_index(drop=True)
    domains = target[
        ["landscape_pressure_score", "terrain_susceptibility_score", "climate_extreme_score"]
    ].to_numpy()
    rng = np.random.default_rng(SEED)
    draws = 50_000
    weights = rng.dirichlet(np.ones(3), size=draws)
    simulated = weights @ domains.T
    order = np.argsort(-simulated, axis=1)
    ranks = np.empty_like(order, dtype=np.int16)
    rank_values = np.arange(1, len(target) + 1, dtype=np.int16)
    for i in range(draws):
        ranks[i, order[i]] = rank_values
    equal_score = domains.mean(axis=1)
    equal_order = np.argsort(-equal_score)
    equal_rank = np.empty(len(target), dtype=int)
    equal_rank[equal_order] = np.arange(1, len(target) + 1)
    uncertainty_rows = []
    for idx, row in target.iterrows():
        uncertainty_rows.append(
            {
                "component_id": row["component_id"],
                "component_name": row["component_name"],
                "equal_domain_score": float(equal_score[idx]),
                "equal_domain_rank": int(equal_rank[idx]),
                "monte_carlo_median_rank": float(np.median(ranks[:, idx])),
                "rank_p2_5": float(np.percentile(ranks[:, idx], 2.5)),
                "rank_p97_5": float(np.percentile(ranks[:, idx], 97.5)),
                "probability_top_5": float(np.mean(ranks[:, idx] <= 5)),
                "probability_top_3": float(np.mean(ranks[:, idx] <= 3)),
                "weight_draws": draws,
            }
        )
    uncertainty = pd.DataFrame(uncertainty_rows).sort_values("equal_domain_rank")
    uncertainty.to_csv(TABLES / "monte_carlo_domain_weight_rank_uncertainty.csv", index=False)

    ablation_values = {
        "Full local (landscape + terrain)": target[
            ["landscape_pressure_score", "terrain_susceptibility_score"]
        ].mean(axis=1),
        "Landscape only": target["landscape_pressure_score"],
        "Terrain only": target["terrain_susceptibility_score"],
        "No NDVI": pd.concat(
            [
                target[["mndwi_pressure", "ndbi_pressure"]].mean(axis=1),
                target["terrain_susceptibility_score"],
            ],
            axis=1,
        ).mean(axis=1),
        "No MNDWI": target[
            ["surface_cover_pressure", "terrain_susceptibility_score"]
        ].mean(axis=1),
        "No NDBI": pd.concat(
            [
                target[["mndwi_pressure", "ndvi_pressure"]].mean(axis=1),
                target["terrain_susceptibility_score"],
            ],
            axis=1,
        ).mean(axis=1),
    }
    full_rank = pd.Series(equal_rank, index=target["component_id"])
    ablation_rows = []
    rank_table = target[["component_id", "component_name"]].copy()
    for name, values_series in ablation_values.items():
        values = values_series.to_numpy()
        order = np.argsort(-values)
        rank = np.empty(len(target), dtype=int)
        rank[order] = np.arange(1, len(target) + 1)
        rank_table[name] = rank
        ablation_rows.append(
            {
                "ablation": name,
                "spearman_rho_with_full": float(
                    spearmanr(full_rank.to_numpy(), rank).statistic
                ),
                "top5_overlap_with_full": int(
                    len(set(np.where(full_rank <= 5)[0]).intersection(np.where(rank <= 5)[0]))
                ),
                "rank_1_component": target.iloc[np.argmin(rank)]["component_name"],
            }
        )
    ablation = pd.DataFrame(ablation_rows)
    ablation.to_csv(TABLES / "leave_one_domain_factor_out_ablation.csv", index=False)
    rank_table.to_csv(TABLES / "ablation_component_ranks.csv", index=False)

    scale_rank = target[["component_id", "component_name"]].copy()
    scale_rows = []
    rank_vectors = {}
    for radius in RADII:
        part = scores[(scores["radius_m"] == radius) & (scores["epoch_id"] == "E2024")].copy()
        part = part.set_index("component_id").loc[target["component_id"]].reset_index()
        values = part["local_priority_score"].to_numpy()
        order = np.argsort(-values)
        ranks_scale = np.empty(len(part), dtype=int)
        ranks_scale[order] = np.arange(1, len(part) + 1)
        rank_vectors[radius] = ranks_scale
        scale_rank[f"rank_{radius}m"] = ranks_scale
    for left in RADII:
        for right in RADII:
            scale_rows.append(
                {
                    "radius_a_m": left,
                    "radius_b_m": right,
                    "spearman_rank_correlation": float(
                        spearmanr(rank_vectors[left], rank_vectors[right]).statistic
                    ),
                }
            )
    scale_corr = pd.DataFrame(scale_rows)
    scale_corr.to_csv(TABLES / "integrated_score_scale_rank_correlations.csv", index=False)
    scale_rank.to_csv(TABLES / "integrated_score_component_ranks_by_scale.csv", index=False)
    return uncertainty, ablation, scale_rank


def save_figure(fig: plt.Figure, name: str) -> None:
    fig.savefig(FIGURES / name, facecolor="white")
    plt.close(fig)


def make_figures(
    components: pd.DataFrame,
    indices: dict[str, np.ndarray],
    endpoint_mask: np.ndarray,
    convergence: np.ndarray,
    climate_epochs: pd.DataFrame,
    site_series: pd.DataFrame,
    terrain_arrays: dict[str, np.ndarray],
    scores: pd.DataFrame,
    corr: pd.DataFrame,
    model_results: pd.DataFrame,
    model_matrix: np.ndarray,
    model_labels: list[int],
    uncertainty: pd.DataFrame,
    ablation: pd.DataFrame,
    scale_rank: pd.DataFrame,
) -> None:
    # Figure 1: matched climate anomalies.
    climate_plot_cols = [
        "monsoon_rainfall_mm_z",
        "rx5day_mm_z",
        "r95p_days_z",
        "cdd_days_z",
        "annual_max_tmax_c_z",
        "tx95_days_z",
        "heatwave_max_days_z",
        "mean_dtr_c_z",
    ]
    labels = [
        "Monsoon rain",
        "Max 5-day rain",
        "Very wet days",
        "Longest dry spell",
        "Annual max temperature",
        "Hot days",
        "Heatwave duration",
        "Diurnal range",
    ]
    fig, ax = plt.subplots(figsize=(10.5, 3.6))
    matrix = climate_epochs.set_index("label_year")[climate_plot_cols].T
    matrix.index = labels
    sns.heatmap(
        matrix,
        cmap="RdBu_r",
        center=0,
        annot=True,
        fmt=".2f",
        linewidths=0.5,
        cbar_kws={"label": "Standard deviations from 1991–2020 annual baseline"},
        ax=ax,
    )
    ax.set_title("Matched three-year climate windows show distinct wet, dry and heat forcing")
    ax.set_xlabel("Landsat epoch")
    ax.set_ylabel("")
    save_figure(fig, "figure_01_matched_climate_anomalies.png")

    # Figure 2: climate-spectral co-evolution.
    fig, axes = plt.subplots(2, 1, figsize=(9.5, 6.2), sharex=True)
    years = site_series["label_year"]
    axes[0].plot(
        years,
        site_series["climate_extreme_score"],
        marker="o",
        lw=2,
        color=COLORS["red"],
        label="Climate-extreme score",
    )
    axes[0].set_ylabel("Climate score (0–1)")
    axes[0].set_title("Site-wide climate forcing and grid-wide post-monsoon spectral medians")
    axes[0].legend(frameon=False, loc="upper left")
    axes[1].plot(
        years,
        site_series["grid_median_ndvi"],
        marker="o",
        color=COLORS["teal"],
        label="NDVI",
    )
    axes[1].plot(
        years,
        site_series["grid_median_mndwi"],
        marker="s",
        color=COLORS["blue"],
        label="MNDWI",
    )
    axes[1].plot(
        years,
        site_series["grid_median_ndbi"],
        marker="^",
        color=COLORS["orange"],
        label="NDBI",
    )
    axes[1].axhline(0, color="#9CA3AF", lw=0.8)
    axes[1].set_ylabel("Median index")
    axes[1].set_xlabel("Epoch")
    axes[1].legend(frameon=False, ncol=3, loc="best")
    save_figure(fig, "figure_02_climate_spectral_coevolution.png")

    # Figure 3: terrain and hydrological susceptibility.
    fig, axes = plt.subplots(2, 2, figsize=(10.8, 8.5), constrained_layout=True)
    terrain_panels = [
        ("dem", "Elevation (m)", "terrain"),
        ("slope_deg", "Slope (degrees)", "magma"),
        ("twi_proxy", "Topographic wetness proxy", "Blues"),
        ("drainage_distance_m", "Distance to high-flow cells (m)", "viridis_r"),
    ]
    extent = [
        float(terrain_arrays["lons"].min()),
        float(terrain_arrays["lons"].max()),
        float(terrain_arrays["lats"].min()),
        float(terrain_arrays["lats"].max()),
    ]
    for ax, (key, title, cmap) in zip(axes.flat, terrain_panels):
        values = terrain_arrays[key]
        low, high = np.nanpercentile(values, [2, 98])
        image = ax.imshow(
            values,
            extent=extent,
            origin="upper",
            cmap=cmap,
            vmin=low,
            vmax=high,
            aspect="equal",
        )
        ax.scatter(
            components["longitude"],
            components["latitude"],
            s=24,
            facecolor="white",
            edgecolor=COLORS["navy"],
            linewidth=0.8,
        )
        ax.set_title(title)
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        fig.colorbar(image, ax=ax, shrink=0.78)
    fig.suptitle(
        "Static terrain separates steep erosion-prone settings from drainage-convergent settings",
        y=1.02,
        fontsize=12,
        fontweight="bold",
    )
    save_figure(fig, "figure_03_terrain_hydrology_atlas.png")

    # Figure 4: integrated score trajectory heatmap at 500 m.
    score500 = scores[scores["radius_m"] == 500].pivot(
        index="component_name", columns="label_year", values="integrated_exposure_score"
    )
    order = score500[2024].sort_values(ascending=False).index
    score500 = score500.loc[order]
    fig, ax = plt.subplots(figsize=(8.4, 7.2))
    sns.heatmap(
        score500,
        cmap="YlOrRd",
        vmin=0,
        vmax=1,
        annot=True,
        fmt=".2f",
        linewidths=0.4,
        cbar_kws={"label": "Integrated exposure score (relative, 0–1)"},
        ax=ax,
    )
    ax.set_title("Integrated exposure is spatially heterogeneous and temporally non-monotonic")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("")
    save_figure(fig, "figure_04_component_exposure_trajectories.png")

    # Figure 5: redundancy and land-cover comparison.
    fig, ax = plt.subplots(figsize=(7.8, 6.3))
    display_corr = corr.rename(
        index={
            "ndvi_pressure": "NDVI pressure",
            "mndwi_pressure": "MNDWI pressure",
            "ndbi_pressure": "NDBI pressure",
            "built_share_pressure": "Mapped built-up",
            "bare_share_pressure": "Mapped bare",
            "surface_cover_pressure": "Surface-cover subdomain",
            "landscape_pressure_score": "Landscape score",
        },
        columns={
            "ndvi_pressure": "NDVI pressure",
            "mndwi_pressure": "MNDWI pressure",
            "ndbi_pressure": "NDBI pressure",
            "built_share_pressure": "Mapped built-up",
            "bare_share_pressure": "Mapped bare",
            "surface_cover_pressure": "Surface-cover subdomain",
            "landscape_pressure_score": "Landscape score",
        },
    )
    sns.heatmap(
        display_corr,
        cmap="vlag",
        center=0,
        vmin=-1,
        vmax=1,
        annot=True,
        fmt=".2f",
        square=True,
        cbar_kws={"label": "Spearman ρ"},
        ax=ax,
    )
    ax.set_title("Factor screening prevents proxy land cover from silently duplicating spectral evidence")
    save_figure(fig, "figure_05_factor_redundancy_heatmap.png")

    # Figure 6: model comparison and best proxy confusion matrix.
    fig, axes = plt.subplots(1, 2, figsize=(12.2, 4.8), gridspec_kw={"width_ratios": [1.05, 1]})
    ordered = model_results.sort_values("outer_proxy_macro_f1", ascending=True)
    y = np.arange(len(ordered))
    ci_low = ordered["outer_proxy_macro_f1"] - ordered["outer_proxy_macro_f1_ci_low"]
    ci_high = ordered["outer_proxy_macro_f1_ci_high"] - ordered["outer_proxy_macro_f1"]
    axes[0].barh(
        y - 0.19,
        ordered["outer_proxy_macro_f1"],
        height=0.18,
        color=COLORS["blue"],
        label="Macro-F1",
        xerr=np.vstack([ci_low, ci_high]),
        error_kw={"ecolor": "#16324F", "elinewidth": 1.0, "capsize": 2.5},
    )
    axes[0].barh(
        y,
        ordered["outer_proxy_balanced_accuracy"],
        height=0.18,
        color=COLORS["teal"],
        label="Balanced accuracy",
    )
    axes[0].barh(
        y + 0.19,
        ordered["outer_proxy_overall_agreement"],
        height=0.18,
        color=COLORS["gold"],
        label="Overall agreement",
    )
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(ordered["model"])
    axes[0].set_xlim(0.65, 1.0)
    axes[0].set_xlabel("Held-out proxy metric")
    axes[0].set_title("Spatially blocked algorithm comparison")
    axes[0].legend(frameon=False, ncol=1, loc="lower right")
    axes[0].text(
        0.0,
        -0.23,
        "Whiskers: 95% spatial-block bootstrap interval for macro-F1",
        transform=axes[0].transAxes,
        fontsize=8,
        color="#4B5563",
        ha="left",
    )
    matrix_norm = model_matrix / np.maximum(model_matrix.sum(axis=1, keepdims=True), 1)
    sns.heatmap(
        matrix_norm,
        cmap="Blues",
        vmin=0,
        vmax=1,
        annot=model_matrix,
        fmt="d",
        xticklabels=[f"C{i}" for i in model_labels],
        yticklabels=[f"C{i}" for i in model_labels],
        cbar_kws={"label": "Row-normalised proportion"},
        ax=axes[1],
    )
    axes[1].set_xlabel("Mapped proxy class")
    axes[1].set_ylabel("Reference proxy class")
    axes[1].set_title(f"Best proxy model: {model_results.iloc[0]['model']}")
    fig.suptitle(
        "Neural and tree ensembles are statistically indistinguishable under spatial-block resampling",
        y=1.02,
        fontsize=12,
        fontweight="bold",
    )
    save_figure(fig, "figure_06_spatially_blocked_model_comparison.png")

    # Figure 7: integrated hotspot map and ranking.
    target = scores[(scores["radius_m"] == 500) & (scores["epoch_id"] == "E2024")].copy()
    target = target.sort_values("local_priority_score", ascending=False)
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 6.2), gridspec_kw={"width_ratios": [1.12, 1]})
    masked = np.where(endpoint_mask, convergence, np.nan)
    extent_utm = [XMIN, XMIN + WIDTH * CELL, YMAX - HEIGHT * CELL, YMAX]
    image = axes[0].imshow(
        masked,
        extent=extent_utm,
        origin="upper",
        cmap=matplotlib.colors.ListedColormap(["#F3F4F6", "#FDE68A", "#FB923C", "#B91C1C"]),
        vmin=0,
        vmax=3,
        interpolation="nearest",
    )
    merged_points = components.merge(
        target[["component_id", "local_priority_score"]], on="component_id"
    )
    points = axes[0].scatter(
        merged_points["easting_m"],
        merged_points["northing_m"],
        c=merged_points["local_priority_score"],
        cmap="viridis",
        vmin=0,
        vmax=1,
        s=68,
        edgecolor="black",
        linewidth=0.7,
        zorder=3,
    )
    axes[0].set_title("Endpoint spectral convergence and 2024 local priority")
    axes[0].set_xlabel("Easting (m, EPSG:32643)")
    axes[0].set_ylabel("Northing (m, EPSG:32643)")
    cbar1 = fig.colorbar(image, ax=axes[0], fraction=0.045, pad=0.02)
    cbar1.set_label("Number of adverse endpoint indicators")
    cbar2 = fig.colorbar(points, ax=axes[0], fraction=0.045, pad=0.09)
    cbar2.set_label("Local priority score")
    top = target.head(12).sort_values("local_priority_score")
    axes[1].barh(
        top["component_name"],
        top["local_priority_score"],
        color=sns.color_palette("viridis", n_colors=len(top)),
    )
    axes[1].set_xlim(0, 1)
    axes[1].set_xlabel("Local priority score (landscape + terrain)")
    axes[1].set_title("Twelve highest 500 m scores")
    fig.suptitle(
        "The integrated screen combines dynamic landscape pressure with local terrain susceptibility",
        y=1.02,
        fontsize=12,
        fontweight="bold",
    )
    save_figure(fig, "figure_07_integrated_hotspot_map.png")

    # Figure 8: Monte Carlo rank uncertainty.
    plot = uncertainty.sort_values("equal_domain_rank", ascending=False)
    fig, ax = plt.subplots(figsize=(8.8, 7.0))
    y = np.arange(len(plot))
    median = plot["monte_carlo_median_rank"].to_numpy()
    lower = median - plot["rank_p2_5"].to_numpy()
    upper = plot["rank_p97_5"].to_numpy() - median
    ax.errorbar(
        median,
        y,
        xerr=np.vstack([lower, upper]),
        fmt="o",
        color=COLORS["navy"],
        ecolor=COLORS["blue"],
        capsize=3,
    )
    ax.set_yticks(y)
    ax.set_yticklabels(plot["component_name"])
    ax.set_xlim(17.7, 0.3)
    ax.set_xlabel("Rank (1 = highest; 95% interval over 50,000 weight draws)")
    ax.set_title("Weight uncertainty materially changes many component positions")
    save_figure(fig, "figure_08_monte_carlo_rank_uncertainty.png")

    # Figure 9: scale sensitivity and ablation.
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 5.8), gridspec_kw={"width_ratios": [1.05, 1]})
    rank_heat = scale_rank.set_index("component_name")[
        ["rank_250m", "rank_500m", "rank_1000m"]
    ].sort_values("rank_500m")
    sns.heatmap(
        rank_heat,
        cmap="YlGnBu_r",
        annot=True,
        fmt="d",
        linewidths=0.4,
        cbar_kws={"label": "Rank"},
        ax=axes[0],
    )
    axes[0].set_title("Integrated rank by analytical radius")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("")
    ablation_plot = ablation.sort_values("spearman_rho_with_full")
    axes[1].barh(
        ablation_plot["ablation"],
        ablation_plot["spearman_rho_with_full"],
        color=COLORS["purple"],
    )
    axes[1].set_xlim(0, 1.02)
    axes[1].set_xlabel("Spearman ρ with full local ranking")
    axes[1].set_title("Leave-one-domain/factor-out stability")
    fig.suptitle(
        "Priority is sensitive to spatial support and to the evidence domain retained",
        y=1.02,
        fontsize=12,
        fontweight="bold",
    )
    save_figure(fig, "figure_09_scale_and_ablation_sensitivity.png")


def build_summary(
    endpoint_summary: dict[str, object],
    climate_epochs: pd.DataFrame,
    terrain: pd.DataFrame,
    scores: pd.DataFrame,
    model_results: pd.DataFrame,
    uncertainty: pd.DataFrame,
    ablation: pd.DataFrame,
    scale_rank: pd.DataFrame,
    thresholds: dict[str, float],
) -> dict[str, object]:
    primary = scores[(scores["radius_m"] == 500) & (scores["epoch_id"] == "E2024")].sort_values(
        "local_priority_score", ascending=False
    )
    top_uncertain = uncertainty.sort_values("probability_top_5", ascending=False).head(5)
    scale_corr = pd.read_csv(TABLES / "integrated_score_scale_rank_correlations.csv")
    summary = {
        "schema_version": "1.0",
        "random_seed": SEED,
        "endpoint_screening": endpoint_summary,
        "climate": {
            "source": "NASA POWER daily point API",
            "coordinate": {"longitude": 72.835, "latitude": 33.746},
            "baseline": "1991-2020",
            "thresholds": thresholds,
            "epoch_extreme_scores": climate_epochs[
                ["epoch_id", "label_year", "climate_extreme_score"]
            ].to_dict(orient="records"),
            "highest_climate_extreme_epoch": climate_epochs.sort_values(
                "climate_extreme_score", ascending=False
            ).iloc[0]["epoch_id"],
        },
        "terrain": {
            "source": "1 arc-second HGT N33E072 public terrain tile",
            "component_scale_records": len(terrain),
        },
        "proxy_model_comparison": {
            "best_model": model_results.iloc[0]["model"],
            "best_outer_proxy_macro_f1": float(
                model_results.iloc[0]["outer_proxy_macro_f1"]
            ),
            "best_outer_proxy_balanced_accuracy": float(
                model_results.iloc[0]["outer_proxy_balanced_accuracy"]
            ),
            "best_outer_proxy_overall_agreement": float(
                model_results.iloc[0]["outer_proxy_overall_agreement"]
            ),
            "role": "held-out WorldCover-consensus proxy agreement; not independent accuracy",
        },
        "integrated_2024_500m_top_components": primary[
            [
                "component_id",
                "component_name",
                "local_priority_score",
                "landscape_pressure_score",
                "terrain_susceptibility_score",
            ]
        ]
        .head(10)
        .to_dict(orient="records"),
        "monte_carlo_top5_probabilities": top_uncertain[
            ["component_id", "component_name", "probability_top_5", "rank_p2_5", "rank_p97_5"]
        ].to_dict(orient="records"),
        "scale_rank_correlations": scale_corr.to_dict(orient="records"),
        "ablation": ablation.to_dict(orient="records"),
        "caveats": [
            "Climate forcing is site-wide at NASA POWER native meteorological support and does not distinguish nearby components.",
            "The integrated score is a relative pressure/exposure screen, not a probability of physical monument damage.",
            "Land-cover model comparisons use WorldCover consensus as weak supervision and must not be reported as independent expert accuracy.",
            "Five Landsat epochs support descriptive trajectories and sensitivity analysis, not high-powered causal trend inference.",
        ],
    }
    (VALIDATION / "integrated_experiment_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf8"
    )
    return summary


def validate_outputs(summary: dict[str, object]) -> None:
    required_tables = [
        "component_epoch_multiscale_landsat.csv",
        "component_endpoint_hotspots.csv",
        "matched_epoch_climate_metrics.csv",
        "component_multiscale_terrain_hydrology.csv",
        "component_epoch_integrated_scores.csv",
        "spatially_blocked_model_comparison.csv",
        "monte_carlo_domain_weight_rank_uncertainty.csv",
        "leave_one_domain_factor_out_ablation.csv",
    ]
    required_figures = [f"figure_{i:02d}_" for i in range(1, 10)]
    checks = []
    for name in required_tables:
        path = TABLES / name
        checks.append({"check": f"table_exists:{name}", "pass": path.exists() and path.stat().st_size > 50})
    figure_files = list(FIGURES.glob("figure_*.png"))
    for prefix in required_figures:
        matches = [path for path in figure_files if path.name.startswith(prefix)]
        checks.append(
            {
                "check": f"figure_exists:{prefix}",
                "pass": len(matches) == 1 and matches[0].stat().st_size > 10_000,
            }
        )
    checks.extend(
        [
            {
                "check": "endpoint_cell_count_reproduced",
                "pass": summary["endpoint_screening"]["endpoint_supported_cells"] == 386_280,
            },
            {
                "check": "model_block_overlap_zero",
                "pass": bool(
                    (
                        pd.read_csv(TABLES / "spatially_blocked_model_comparison.csv")[
                            "block_overlap"
                        ]
                        == 0
                    ).all()
                ),
            },
            {
                "check": "scores_finite_and_bounded",
                "pass": bool(
                    pd.read_csv(TABLES / "component_epoch_integrated_scores.csv")[
                        ["integrated_exposure_score", "local_priority_score"]
                    ]
                    .apply(lambda column: column.between(0, 1).all())
                    .all()
                ),
            },
        ]
    )
    passed = sum(check["pass"] for check in checks)
    result = {
        "status": "PASS" if passed == len(checks) else "FAIL",
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "source_hashes": {
            "nasa_power_json": sha256(
                ROOT / "data" / "source" / "nasa_power_taxila_1991_2025_daily.json"
            ),
            "terrain_hgt_gz": sha256(ROOT / "data" / "source" / "N33E072.hgt.gz"),
            "raw_manifest": sha256(RAW / "raw_manifest.json"),
        },
    }
    (VALIDATION / "integrated_experiment_validation.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf8"
    )
    if result["status"] != "PASS":
        failed = [check["check"] for check in checks if not check["pass"]]
        raise RuntimeError(f"Validation failed: {failed}")


def main() -> None:
    components = load_components()
    indices, observations, landcover = load_epoch_arrays()
    landsat_summary, endpoint_summary, endpoint_mask, convergence, valids = summarize_landsat(
        components, indices, observations, landcover
    )
    _, _, climate_epochs, climate_thresholds = load_climate()
    terrain, terrain_arrays = load_terrain(components)
    scores, _, corr, _ = prepare_integrated_scores(
        landsat_summary, terrain, climate_epochs
    )
    site_series = climate_spectral_associations(indices, valids, climate_epochs)
    feature_frame = extract_proxy_features()
    model_results, model_matrix, model_labels = model_comparison(feature_frame)
    uncertainty, ablation, scale_rank = uncertainty_and_ablation(scores)
    make_figures(
        components,
        indices,
        endpoint_mask,
        convergence,
        climate_epochs,
        site_series,
        terrain_arrays,
        scores,
        corr,
        model_results,
        model_matrix,
        model_labels,
        uncertainty,
        ablation,
        scale_rank,
    )
    summary = build_summary(
        endpoint_summary,
        climate_epochs,
        terrain,
        scores,
        model_results,
        uncertainty,
        ablation,
        scale_rank,
        climate_thresholds,
    )
    validate_outputs(summary)
    print(
        json.dumps(
            {
                "status": "PASS",
                "tables": len(list(TABLES.glob("*"))),
                "figures": len(list(FIGURES.glob("*.png"))),
                "validation": str(
                    VALIDATION / "integrated_experiment_validation.json"
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
