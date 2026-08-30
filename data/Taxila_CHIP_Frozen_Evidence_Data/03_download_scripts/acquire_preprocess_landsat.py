#!/usr/bin/env python3
"""Acquire clipped Landsat bands and create validated epoch composites.

The Microsoft Planetary Computer data API performs bounded COG reads and returns
GeoTIFFs on the frozen Taxila grid. Raw reflectance and QA are requested
separately so continuous and categorical resampling rules cannot be mixed.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import io
import json
import math
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from typing import Any

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.vrt import WarpedVRT


USER_AGENT = "PreserveX-Taxila-Reproducibility/1.0"
DATA_API = "https://planetarycomputer.microsoft.com/api/data/v1/item/bbox"
SCRIPT_ROOT = pathlib.Path(__file__).resolve().parent


def load_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def expected_transform(config: dict[str, Any]) -> Affine:
    gdal = config["spatial_contract"]["transform_gdal"]
    return Affine.from_gdal(*gdal)


def data_api_url(config: dict[str, Any], item_id: str, assets: list[str], resampling: str) -> str:
    xmin, ymin, xmax, ymax = config["spatial_contract"]["aoi_bounds_target_crs"]
    width = config["spatial_contract"]["width"]
    height = config["spatial_contract"]["height"]
    query = urllib.parse.urlencode(
        {
            "collection": config["stac"]["collection"],
            "item": item_id,
            "assets": assets,
            "asset_as_band": "true",
            "coord_crs": config["spatial_contract"]["target_crs"].lower(),
            "dst_crs": config["spatial_contract"]["target_crs"].lower(),
            "resampling": resampling,
            "reproject": resampling,
            "return_mask": "false",
            "unscale": "false",
        },
        doseq=True,
    )
    return f"{DATA_API}/{xmin:g},{ymin:g},{xmax:g},{ymax:g}/{width}x{height}.tif?{query}"


def download(url: str, attempts: int = 4) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=240) as response:
                payload = response.read()
                if not payload.startswith((b"II*\x00", b"MM\x00*")):
                    raise RuntimeError(f"Expected TIFF response, received {payload[:120]!r}")
                return payload
        except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
            last_error = error
            if attempt < attempts:
                time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"Download failed after {attempts} attempts: {last_error}")


def get_sas_token(config: dict[str, Any]) -> str:
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            request = urllib.request.Request(config["stac"]["sas_endpoint"], headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=150) as response:
                value = json.load(response)
            if not value.get("token"):
                raise RuntimeError("Planetary Computer SAS endpoint returned no token")
            return value["token"]
        except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
            last_error = error
            if attempt < 4:
                time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"Unable to obtain SAS token: {last_error}")


def read_signed_cog_assets(
    candidate: dict[str, Any], assets: list[str], resampling: str, config: dict[str, Any],
    sas_token: str, allow_unsafe_tls: bool,
) -> np.ndarray:
    method = Resampling.nearest if resampling == "nearest" else Resampling.bilinear
    arrays: list[np.ndarray] = []
    env_options = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".TIF,.tif",
    }
    if allow_unsafe_tls:
        env_options["GDAL_HTTP_UNSAFESSL"] = "YES"
    with rasterio.Env(**env_options):
        for asset in assets:
            base_url = candidate["assets"][asset]
            signed_url = f"{base_url}?{sas_token}"
            with rasterio.open(signed_url) as source:
                with WarpedVRT(
                    source,
                    crs=config["spatial_contract"]["target_crs"],
                    transform=expected_transform(config),
                    width=config["spatial_contract"]["width"],
                    height=config["spatial_contract"]["height"],
                    resampling=method,
                    src_nodata=source.nodata,
                    nodata=source.nodata,
                ) as vrt:
                    arrays.append(vrt.read(1))
    return np.stack(arrays)


def read_grid_tiff(payload: bytes, config: dict[str, Any], expected_count: int) -> np.ndarray:
    with MemoryFile(payload) as memfile, memfile.open() as dataset:
        observed = {
            "count": dataset.count,
            "width": dataset.width,
            "height": dataset.height,
            "crs": str(dataset.crs),
            "transform": dataset.transform,
        }
        if observed["count"] != expected_count:
            raise RuntimeError(f"Unexpected band count: {observed}")
        if observed["width"] != config["spatial_contract"]["width"] or observed["height"] != config["spatial_contract"]["height"]:
            raise RuntimeError(f"Unexpected raster dimensions: {observed}")
        if observed["crs"] != config["spatial_contract"]["target_crs"]:
            raise RuntimeError(f"Unexpected CRS: {observed}")
        if not observed["transform"].almost_equals(expected_transform(config), precision=1e-9):
            raise RuntimeError(f"Unexpected grid transform: {observed}")
        return dataset.read()


def qa_masks(qa: np.ndarray, platform: str) -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    qa_pixel = qa[0].astype(np.uint16, copy=False)
    qa_radsat = qa[1].astype(np.uint16, copy=False)
    rejected_pixel_bits = sum(1 << bit for bit in (0, 1, 2, 3, 4, 5))
    baseline = ((qa_pixel & rejected_pixel_bits) == 0) & (qa_radsat == 0)
    strict = baseline.copy()
    aerosol_valid_retrieval_fraction = math.nan
    if platform in {"landsat-8", "landsat-9"}:
        aerosol = qa[2].astype(np.uint16, copy=False)
        aerosol_fill = (aerosol & 1) != 0
        aerosol_retrieval_valid = (aerosol & (1 << 1)) != 0
        aerosol_interpolated = (aerosol & (1 << 5)) != 0
        aerosol_level = (aerosol >> 6) & 3
        baseline &= ~aerosol_fill & (aerosol_level != 3)
        strict = baseline & aerosol_retrieval_valid & ~aerosol_interpolated
        aerosol_valid_retrieval_fraction = float(aerosol_retrieval_valid.mean())
    stats = {
        "baseline_qa_valid_percent": float(baseline.mean() * 100.0),
        "strict_qa_valid_percent": float(strict.mean() * 100.0),
        "aerosol_valid_retrieval_percent": None if math.isnan(aerosol_valid_retrieval_fraction) else aerosol_valid_retrieval_fraction * 100.0,
    }
    return baseline, strict, stats


def process_scene(
    candidate: dict[str, Any], config: dict[str, Any], transport: str,
    allow_unsafe_tls: bool, sas_token: str | None,
) -> dict[str, Any]:
    reflectance_assets = config["spectral_contract"]["reflectance_assets"]
    qa_assets = list(config["spectral_contract"]["required_qa_assets"])
    if candidate["platform"] in {"landsat-8", "landsat-9"}:
        qa_assets.append(config["spectral_contract"]["oli_only_qa_asset"])
    qa_url = data_api_url(config, candidate["item_id"], qa_assets, "nearest")
    sr_url = data_api_url(config, candidate["item_id"], reflectance_assets, "bilinear")
    if transport == "signed-cog":
        if not sas_token:
            raise RuntimeError("Signed COG transport requires a SAS token")
        qa = read_signed_cog_assets(candidate, qa_assets, "nearest", config, sas_token, allow_unsafe_tls)
        sr_dn = read_signed_cog_assets(candidate, reflectance_assets, "bilinear", config, sas_token, allow_unsafe_tls).astype(np.float32)
        request_audit: dict[str, Any] = {
            "transport": "signed-cog",
            "qa_assets": [candidate["assets"][name] for name in qa_assets],
            "reflectance_assets": [candidate["assets"][name] for name in reflectance_assets],
            "sas_token_recorded": False,
            "unsafe_tls_override": allow_unsafe_tls,
        }
    else:
        qa = read_grid_tiff(download(qa_url), config, len(qa_assets))
        sr_dn = read_grid_tiff(download(sr_url), config, len(reflectance_assets)).astype(np.float32)
        request_audit = {"transport": "data-api", "qa": qa_url, "reflectance": sr_url}
    baseline_mask, strict_mask, qa_stats = qa_masks(qa, candidate["platform"])
    scale = config["spectral_contract"]["surface_reflectance_scale"]
    offset = config["spectral_contract"]["surface_reflectance_offset"]
    reflectance = sr_dn * np.float32(scale) + np.float32(offset)
    low, high = config["spectral_contract"]["physical_reflectance_range"]
    physical = np.all(np.isfinite(reflectance) & (reflectance >= low) & (reflectance <= high), axis=0)
    valid = baseline_mask & physical
    strict_valid = strict_mask & physical
    reflectance[:, ~valid] = np.nan
    local_valid = float(valid.mean() * 100.0)
    threshold = config["composite_contract"]["scene_local_clear_fraction_floor_percent"]
    retained = local_valid >= threshold
    return {
        "candidate": candidate,
        "reflectance": reflectance if retained else None,
        "valid": valid if retained else None,
        "strict_valid": strict_valid if retained else None,
        "audit": {
            "epoch_id": candidate["epoch_id"],
            "item_id": candidate["item_id"],
            "datetime": candidate["datetime"],
            "platform": candidate["platform"],
            "catalogue_cloud_cover_percent": candidate["catalogue_cloud_cover_percent"],
            **qa_stats,
            "physical_and_baseline_valid_percent": local_valid,
            "physical_and_strict_valid_percent": float(strict_valid.mean() * 100.0),
            "retained": retained,
            "rejection_reason": None if retained else f"local valid fraction below {threshold}%",
            "acquisition": request_audit,
        },
    }


def write_multiband(path: pathlib.Path, array: np.ndarray, config: dict[str, Any], descriptions: list[str], tags: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    nodata = -9999.0
    output = np.where(np.isfinite(array), array, nodata).astype(np.float32)
    profile = {
        "driver": "GTiff",
        "width": config["spatial_contract"]["width"],
        "height": config["spatial_contract"]["height"],
        "count": output.shape[0],
        "dtype": "float32",
        "crs": config["spatial_contract"]["target_crs"],
        "transform": expected_transform(config),
        "nodata": nodata,
        "compress": "deflate",
        "predictor": 3,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(output)
        dataset.descriptions = tuple(descriptions)
        dataset.update_tags(**tags)


def write_count(path: pathlib.Path, count: np.ndarray, config: dict[str, Any], tags: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "width": config["spatial_contract"]["width"],
        "height": config["spatial_contract"]["height"],
        "count": 1,
        "dtype": "uint16",
        "crs": config["spatial_contract"]["target_crs"],
        "transform": expected_transform(config),
        "nodata": 0,
        "compress": "deflate",
        "predictor": 2,
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    with rasterio.open(path, "w", **profile) as dataset:
        dataset.write(count.astype(np.uint16), 1)
        dataset.set_band_description(1, "valid_observation_count")
        dataset.update_tags(**tags)


def indices_from_sr(sr: np.ndarray) -> tuple[np.ndarray, list[str]]:
    blue, green, red, nir, swir1, _swir2 = sr
    def ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            result = numerator / denominator
        result[~np.isfinite(result)] = np.nan
        return result.astype(np.float32)
    ndvi = ratio(nir - red, nir + red)
    ndbi = ratio(swir1 - nir, swir1 + nir)
    mndwi = ratio(green - swir1, green + swir1)
    bsi = ratio((swir1 + red) - (nir + blue), (swir1 + red) + (nir + blue))
    return np.stack([ndvi, ndbi, mndwi, bsi]), ["NDVI", "NDBI", "MNDWI", "BSI"]


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path(path: pathlib.Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(SCRIPT_ROOT))
    except ValueError:
        return str(resolved)


def composite_epoch(
    epoch_id: str, rows: list[dict[str, Any]], config: dict[str, Any], output_dir: pathlib.Path,
    max_workers: int, transport_mode: str, allow_unsafe_tls: bool, sas_token: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[pathlib.Path]]:
    print(f"preprocess {epoch_id}: {len(rows)} catalogue candidates", flush=True)
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {}
        for row in rows:
            scene_year = int(row["datetime"][:4])
            scene_transport = "signed-cog" if transport_mode == "auto" and scene_year >= 2018 else ("data-api" if transport_mode == "auto" else transport_mode)
            future_map[executor.submit(process_scene, row, config, scene_transport, allow_unsafe_tls, sas_token)] = row
        for future in concurrent.futures.as_completed(future_map):
            row = future_map[future]
            try:
                result = future.result()
                results.append(result)
                print(f"  {row['item_id']}: valid={result['audit']['physical_and_baseline_valid_percent']:.2f}% retained={result['audit']['retained']}", flush=True)
            except Exception as error:
                results.append({"candidate": row, "reflectance": None, "valid": None, "strict_valid": None, "audit": {
                    "epoch_id": epoch_id, "item_id": row["item_id"], "datetime": row["datetime"], "platform": row["platform"],
                    "catalogue_cloud_cover_percent": row["catalogue_cloud_cover_percent"], "retained": False,
                    "rejection_reason": f"processing error: {type(error).__name__}: {error}",
                }})
                print(f"  {row['item_id']}: ERROR {error}", flush=True)
    results.sort(key=lambda value: value["candidate"]["datetime"])
    retained = [result for result in results if result["reflectance"] is not None]
    if not retained:
        raise RuntimeError(f"No scenes retained for {epoch_id}")
    stack = np.stack([result["reflectance"] for result in retained])
    valid_stack = np.stack([result["valid"] for result in retained])
    strict_stack = np.stack([result["strict_valid"] for result in retained])
    observation_count = valid_stack.sum(axis=0).astype(np.uint16)
    strict_observation_count = strict_stack.sum(axis=0).astype(np.uint16)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice encountered")
        native = np.nanmedian(stack, axis=0).astype(np.float32)
    minimum = config["composite_contract"]["minimum_valid_observations"]
    preferred = config["composite_contract"]["preferred_valid_observations"]
    eligible = observation_count >= minimum
    native[:, ~eligible] = np.nan
    platforms = sorted({result["candidate"]["platform"] for result in retained})
    platform = "+".join(platforms)
    common = native.copy()
    if platforms == ["landsat-7"]:
        coefficients = config["harmonisation_contract"]["etm_plus_to_oli_coefficients"]
        for index, band in enumerate(config["spectral_contract"]["reflectance_assets"]):
            common[index] = coefficients[band]["intercept"] + coefficients[band]["slope"] * native[index]
    common[:, ~eligible] = np.nan
    indices, index_names = indices_from_sr(common)
    tags = {
        "project": config["project"], "epoch_id": epoch_id, "source_platforms": platform,
        "minimum_valid_observations": str(minimum), "grid_contract": "Stage3_EPSG32643_30m",
    }
    paths = {
        "native_surface_reflectance": output_dir / f"{epoch_id}_sensor_native_surface_reflectance.tif",
        "oli_like_surface_reflectance": output_dir / f"{epoch_id}_oli_like_surface_reflectance.tif",
        "indices": output_dir / f"{epoch_id}_oli_like_indices.tif",
        "observation_count": output_dir / f"{epoch_id}_valid_observation_count.tif",
        "strict_observation_count": output_dir / f"{epoch_id}_strict_valid_observation_count.tif",
    }
    write_multiband(paths["native_surface_reflectance"], native, config, config["spectral_contract"]["reflectance_assets"], {**tags, "representation": "sensor_native"})
    write_multiband(paths["oli_like_surface_reflectance"], common, config, config["spectral_contract"]["reflectance_assets"], {**tags, "representation": "OLI_like_Roy2016" if platforms == ["landsat-7"] else "native_OLI_family"})
    write_multiband(paths["indices"], indices, config, index_names, {**tags, "representation": "indices_from_OLI_like_reflectance"})
    write_count(paths["observation_count"], observation_count, config, {**tags, "mask": "baseline"})
    write_count(paths["strict_observation_count"], strict_observation_count, config, {**tags, "mask": "strict_OLI_aerosol_retrieval"})
    coverage = float(eligible.mean() * 100.0)
    preferred_coverage = float((observation_count >= preferred).mean() * 100.0)
    strict_coverage = float((strict_observation_count >= minimum).mean() * 100.0)
    epoch_audit = {
        "epoch_id": epoch_id,
        "source_platforms": platforms,
        "catalogue_candidates": len(rows),
        "retained_scenes": len(retained),
        "processing_failures": sum((result["audit"].get("rejection_reason") or "").startswith("processing error") for result in results),
        "minimum_valid_observations": minimum,
        "preferred_valid_observations": preferred,
        "baseline_eligible_grid_coverage_percent": coverage,
        "preferred_observation_grid_coverage_percent": preferred_coverage,
        "strict_aerosol_eligible_grid_coverage_percent": strict_coverage,
        "observation_count_min": int(observation_count.min()),
        "observation_count_median": float(np.median(observation_count)),
        "observation_count_max": int(observation_count.max()),
        "checks": {
            "minimum_retained_scenes": "PASS" if len(retained) >= config["composite_contract"]["minimum_retained_scenes_per_epoch"] else "FAIL",
            "minimum_grid_coverage": "PASS" if coverage >= config["composite_contract"]["minimum_epoch_grid_coverage_percent"] else "FAIL",
            "finite_composite_values": "PASS" if np.isfinite(common[:, eligible]).all() else "FAIL",
        },
        "outputs": {name: {"path": portable_path(path), "sha256": sha256(path), "bytes": path.stat().st_size} for name, path in paths.items()},
    }
    del stack, valid_stack, strict_stack
    return epoch_audit, [result["audit"] for result in results], list(paths.values())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="batch1_config.json")
    parser.add_argument("--inventory", default=None)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--epochs", nargs="*", default=None)
    parser.add_argument("--transport", choices=["auto", "data-api", "signed-cog"], default="auto")
    parser.add_argument("--allow-unsafe-tls", action="store_true", help="Only for controlled proxy environments whose certificate cannot be loaded by GDAL.")
    parser.add_argument("--sas-token-file", default=None, help="Optional temporary Planetary Computer token JSON; tokens are never written to reports.")
    args = parser.parse_args()
    config_path = pathlib.Path(args.config).resolve()
    config = load_json(config_path)
    inventory_path = pathlib.Path(args.inventory).resolve() if args.inventory else (config_path.parent / config["output"]["inventory_json"]).resolve()
    inventory = load_json(inventory_path)
    selected_epochs = set(args.epochs or [epoch["epoch_id"] for epoch in config["temporal_contract"]["epochs"]])
    output_dir = (config_path.parent / config["output"]["composite_directory"]).resolve()
    needs_token = args.transport in {"auto", "signed-cog"}
    if needs_token and args.sas_token_file:
        sas_token = load_json(pathlib.Path(args.sas_token_file).resolve()).get("token")
        if not sas_token:
            raise RuntimeError("The supplied SAS token file contains no token")
    else:
        sas_token = get_sas_token(config) if needs_token else None
    epoch_audits: list[dict[str, Any]] = []
    scene_audits: list[dict[str, Any]] = []
    all_paths: list[pathlib.Path] = []
    for epoch in config["temporal_contract"]["epochs"]:
        epoch_id = epoch["epoch_id"]
        if epoch_id not in selected_epochs:
            continue
        rows = [row for row in inventory["candidates"] if row["epoch_id"] == epoch_id]
        audit, scenes, paths = composite_epoch(
            epoch_id, rows, config, output_dir, max(1, args.max_workers),
            args.transport, args.allow_unsafe_tls, sas_token,
        )
        epoch_audits.append(audit)
        scene_audits.extend(scenes)
        all_paths.extend(paths)
    checks = [
        {"check": "all_requested_epochs_processed", "status": "PASS" if len(epoch_audits) == len(selected_epochs) else "FAIL", "observed": len(epoch_audits), "expected": len(selected_epochs)},
        {"check": "all_epoch_acceptance_gates_pass", "status": "PASS" if all(all(status == "PASS" for status in audit["checks"].values()) for audit in epoch_audits) else "FAIL"},
        {"check": "all_outputs_exist", "status": "PASS" if all(path.exists() and path.stat().st_size > 0 for path in all_paths) else "FAIL"},
    ]
    report = {
        "schema_version": "1.0",
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "config": portable_path(config_path),
        "inventory": portable_path(inventory_path),
        "data_api": DATA_API,
        "transport_mode": args.transport,
        "unsafe_tls_override": args.allow_unsafe_tls,
        "requested_epochs": sorted(selected_epochs),
        "epoch_audits": epoch_audits,
        "scene_audits": scene_audits,
        "global_checks": checks,
        "pass_count": sum(check["status"] == "PASS" for check in checks),
        "fail_count": sum(check["status"] == "FAIL" for check in checks),
    }
    report_path = (config_path.parent / config["output"]["preprocessing_report_json"]).resolve()
    write_json(report_path, report)
    print(json.dumps({"report": str(report_path), "epochs": epoch_audits, "global_checks": checks}, indent=2))
    return 0 if report["fail_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
