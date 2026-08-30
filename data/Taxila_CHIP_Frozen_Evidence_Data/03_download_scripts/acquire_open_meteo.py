#!/usr/bin/env python3
"""Acquire reproducible Open-Meteo ERA5-Seamless daily records for Taxila.

ERA5-Seamless is used because Open-Meteo documents that ERA5-Land supplies
surface temperature/humidity/soil fields while precipitation and wind are
provided from ERA5 forcing. This retains ERA5-Land where suitable without
silently accepting null precipitation from an ERA5-Land-only request.
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


RUN_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = RUN_ROOT / "02_raw_data" / "open_meteo"
MANIFEST_DIR = RUN_ROOT / "01_sources_and_manifests"
TABLE_DIR = RUN_ROOT / "13_tables"
RAW_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"
MODEL = "era5_seamless"
START_DATE = "1991-01-01"
END_DATE = "2025-12-31"
VARIABLES = [
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "relative_humidity_2m_mean",
    "dew_point_2m_mean",
    "wind_speed_10m_max",
    "soil_moisture_0_to_7cm_mean",
    "et0_fao_evapotranspiration_sum",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_url(latitude: str, longitude: str, start: str, end: str) -> str:
    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start,
            "end_date": end,
            "daily": ",".join(VARIABLES),
            "timezone": "UTC",
            "models": MODEL,
        },
        safe=",",
    )
    return f"{ENDPOINT}?{query}"


def fetch_json(url: str, attempts: int = 4) -> object:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Taxila-PreserveX-reproducibility/1.0"},
            )
            with urllib.request.urlopen(request, timeout=240) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:  # recorded after final attempt
            last_error = error
            if attempt < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"Open-Meteo request failed after {attempts} attempts: {last_error}")


def load_components() -> list[dict[str, object]]:
    source = SOURCE_ROOT / "work" / "spatial" / "derived" / "taxila_components_wgs84.geojson"
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for feature in payload["features"]:
        if feature.get("geometry") is None:
            continue
        props = feature["properties"]
        lon, lat = feature["geometry"]["coordinates"]
        rows.append(
            {
                "component_id": props["component_id"],
                "component_name": props["name"],
                "requested_latitude": float(lat),
                "requested_longitude": float(lon),
            }
        )
    rows.sort(key=lambda row: str(row["component_id"]))
    if len(rows) != 17:
        raise RuntimeError(f"Expected 17 mapped components; found {len(rows)}")
    return rows


def main() -> None:
    retrieved = datetime.now(timezone.utc).isoformat()
    components = load_components()
    mapping_path = TABLE_DIR / "component_open_meteo_grid_mapping.csv"
    if mapping_path.exists():
        with mapping_path.open(newline="", encoding="utf-8") as handle:
            mapping_rows = list(csv.DictReader(handle))
        grid_cells = {
            (round(float(row["returned_latitude"]), 6), round(float(row["returned_longitude"]), 6)): row["weather_cell_id"]
            for row in mapping_rows
        }
    else:
        latitudes = ",".join(f"{row['requested_latitude']:.7f}" for row in components)
        longitudes = ",".join(f"{row['requested_longitude']:.7f}" for row in components)
        discovery_url = build_url(latitudes, longitudes, "2020-01-01", "2020-01-01")
        discovery = fetch_json(discovery_url)
        if not isinstance(discovery, list) or len(discovery) != len(components):
            raise RuntimeError("Unexpected multi-location Open-Meteo discovery response")

        grid_cells: dict[tuple[float, float], str] = {}
        mapping_rows: list[dict[str, object]] = []
        for component, response in zip(components, discovery):
            key = (round(float(response["latitude"]), 6), round(float(response["longitude"]), 6))
            if key not in grid_cells:
                grid_cells[key] = f"OM_{len(grid_cells) + 1:02d}"
            mapping_rows.append(
                {
                    **component,
                    "weather_cell_id": grid_cells[key],
                    "returned_latitude": key[0],
                    "returned_longitude": key[1],
                    "weather_elevation_m": response.get("elevation"),
                    "model": MODEL,
                    "nominal_resolution": "ERA5-Land 0.1 degree surface fields; ERA5 forcing for precipitation/wind",
                }
            )
        with mapping_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(mapping_rows[0]))
            writer.writeheader()
            writer.writerows(mapping_rows)

    manifest_rows: list[dict[str, object]] = []
    missing = [
        (key, cell_id)
        for key, cell_id in grid_cells.items()
        if not (RAW_DIR / f"{cell_id}_era5_seamless_daily_1991_2025.json").exists()
    ]
    payload_by_cell: dict[str, dict[str, object]] = {}
    batch_url = ""
    if missing:
        batch_url = build_url(
            ",".join(str(key[0]) for key, _ in missing),
            ",".join(str(key[1]) for key, _ in missing),
            START_DATE,
            END_DATE,
        )
        batch_payload = fetch_json(batch_url)
        responses = batch_payload if isinstance(batch_payload, list) else [batch_payload]
        if len(responses) != len(missing):
            raise RuntimeError("Unexpected multi-location full-period Open-Meteo response")
        for (_, cell_id), payload in zip(missing, responses):
            if not isinstance(payload, dict) or "daily" not in payload:
                raise RuntimeError(f"Unexpected Open-Meteo response for {cell_id}")
            payload_by_cell[cell_id] = payload

    for (latitude, longitude), cell_id in sorted(grid_cells.items(), key=lambda item: item[1]):
        output = RAW_DIR / f"{cell_id}_era5_seamless_daily_1991_2025.json"
        if cell_id in payload_by_cell:
            output.write_text(
                json.dumps(payload_by_cell[cell_id], separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
        payload = json.loads(output.read_text(encoding="utf-8"))
        url = batch_url if cell_id in payload_by_cell else build_url(
            str(latitude), str(longitude), START_DATE, END_DATE
        )
        manifest_rows.append(
            {
                "weather_cell_id": cell_id,
                "requested_latitude": latitude,
                "requested_longitude": longitude,
                "returned_latitude": payload.get("latitude"),
                "returned_longitude": payload.get("longitude"),
                "elevation_m": payload.get("elevation"),
                "model": MODEL,
                "start_date": START_DATE,
                "end_date": END_DATE,
                "variables": ",".join(VARIABLES),
                "temporal_resolution": "daily",
                "timezone": payload.get("timezone"),
                "retrieved_utc": retrieved,
                "official_documentation": "https://open-meteo.com/en/docs/historical-weather-api",
                "request_url": url,
                "raw_file": str(output.relative_to(RUN_ROOT)),
                "sha256": sha256(output),
                "bytes": output.stat().st_size,
            }
        )

    manifest_path = MANIFEST_DIR / "open_meteo_request_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
        writer.writeheader()
        writer.writerows(manifest_rows)

    summary = {
        "status": "PASS",
        "retrieved_utc": retrieved,
        "model": MODEL,
        "components_mapped": len(mapping_rows),
        "unique_weather_cells": len(grid_cells),
        "period": [START_DATE, END_DATE],
        "variables": VARIABLES,
        "mapping_file": str(mapping_path.relative_to(RUN_ROOT)),
        "request_manifest": str(manifest_path.relative_to(RUN_ROOT)),
        "reason_for_era5_seamless": (
            "Open-Meteo ERA5-Land supplies surface temperature, humidity and soil fields; "
            "ERA5 forcing supplies precipitation and wind, which are unavailable in the "
            "ERA5-Land-only API selection."
        ),
    }
    (MANIFEST_DIR / "open_meteo_acquisition_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
