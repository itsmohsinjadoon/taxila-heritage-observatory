#!/usr/bin/env python3
"""Discover auditable Landsat C2 L2 candidates for the fixed Taxila epochs."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import sys
import urllib.error
import urllib.request
from typing import Any, Iterable


USER_AGENT = "PreserveX-Taxila-Reproducibility/1.0"


def load_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=False)
        stream.write("\n")


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def point_in_ring(point: tuple[float, float], ring: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test; boundary points are treated as inside."""
    x, y = point
    inside = False
    for i in range(len(ring)):
        x1, y1 = ring[i - 1][0], ring[i - 1][1]
        x2, y2 = ring[i][0], ring[i][1]
        cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
        if abs(cross) < 1e-10 and min(x1, x2) - 1e-10 <= x <= max(x1, x2) + 1e-10 and min(y1, y2) - 1e-10 <= y <= max(y1, y2) + 1e-10:
            return True
        intersects = (y1 > y) != (y2 > y)
        if intersects:
            x_at_y = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x <= x_at_y:
                inside = not inside
    return inside


def point_in_polygon(point: tuple[float, float], polygon: list[list[list[float]]]) -> bool:
    if not polygon or not point_in_ring(point, polygon[0]):
        return False
    return not any(point_in_ring(point, hole) for hole in polygon[1:])


def geometry_contains_point(geometry: dict[str, Any], point: tuple[float, float]) -> bool:
    kind = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if kind == "Polygon":
        return point_in_polygon(point, coords)
    if kind == "MultiPolygon":
        return any(point_in_polygon(point, polygon) for polygon in coords)
    return False


def geometry_covers_bbox(geometry: dict[str, Any], bbox: list[float]) -> bool:
    xmin, ymin, xmax, ymax = bbox
    corners = [(xmin, ymin), (xmin, ymax), (xmax, ymin), (xmax, ymax)]
    return all(geometry_contains_point(geometry, corner) for corner in corners)


def search_all(endpoint: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    page_payload = dict(payload)
    seen_tokens: set[str] = set()
    for _page_number in range(100):
        page = post_json(f"{endpoint.rstrip('/')}/search", page_payload)
        features.extend(page.get("features", []))
        next_link = next((link for link in page.get("links", []) if link.get("rel") == "next"), None)
        if not next_link:
            return features
        if next_link.get("method", "GET").upper() != "POST" or not next_link.get("body"):
            raise RuntimeError("Unexpected non-POST STAC pagination response")
        page_payload = next_link["body"]
        token = str(page_payload.get("token", ""))
        if token in seen_tokens:
            raise RuntimeError(f"Repeated STAC pagination token: {token}")
        seen_tokens.add(token)
    raise RuntimeError("STAC pagination exceeded the 100-page safety limit")


def seasonal_searches(config: dict[str, Any], epoch: dict[str, Any]) -> Iterable[dict[str, Any]]:
    start_md = config["temporal_contract"]["season"]["start_month_day"]
    end_md = config["temporal_contract"]["season"]["end_month_day"]
    stac = config["stac"]
    for year in epoch["years"]:
        platform_query = {"eq": epoch["primary_platforms"][0]} if len(epoch["primary_platforms"]) == 1 else {"in": epoch["primary_platforms"]}
        yield {
            "collections": [stac["collection"]],
            "bbox": config["spatial_contract"]["aoi_bbox_wgs84"],
            "datetime": f"{year}-{start_md}T00:00:00Z/{year}-{end_md}T23:59:59Z",
            "query": {
                "platform": platform_query,
                "landsat:collection_category": {"eq": stac["collection_category"]},
            },
            "limit": 100,
        }


def reduce_item(item: dict[str, Any], epoch: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    props = item["properties"]
    wanted_assets = (
        config["spectral_contract"]["reflectance_assets"]
        + config["spectral_contract"]["required_qa_assets"]
        + [config["spectral_contract"]["oli_only_qa_asset"]]
    )
    assets = {key: item.get("assets", {}).get(key, {}).get("href") for key in wanted_assets if key in item.get("assets", {})}
    return {
        "epoch_id": epoch["epoch_id"],
        "label_year": epoch["label_year"],
        "item_id": item["id"],
        "datetime": props.get("datetime"),
        "platform": props.get("platform"),
        "sensor": epoch["sensor"],
        "wrs_path": props.get("landsat:wrs_path"),
        "wrs_row": props.get("landsat:wrs_row"),
        "processing_level": props.get("landsat:correction"),
        "collection_category": props.get("landsat:collection_category"),
        "catalogue_cloud_cover_percent": props.get("eo:cloud_cover"),
        "proj_epsg": props.get("proj:epsg"),
        "full_aoi_coverage": geometry_covers_bbox(item["geometry"], config["spatial_contract"]["aoi_bbox_wgs84"]),
        "geometry": item["geometry"],
        "assets": assets,
        "item_url": next((link.get("href") for link in item.get("links", []) if link.get("rel") == "self"), None),
    }


def discover(config_path: pathlib.Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_json(config_path)
    candidates: list[dict[str, Any]] = []
    raw_count = 0
    rejection_counts = {"cloud_threshold": 0, "processing_level": 0, "asset_completeness": 0, "full_aoi_coverage": 0}
    required_common = set(config["spectral_contract"]["reflectance_assets"] + config["spectral_contract"]["required_qa_assets"])
    allowed_levels = set(config["stac"]["allowed_processing_levels"])

    for epoch in config["temporal_contract"]["epochs"]:
        seen: set[str] = set()
        for payload in seasonal_searches(config, epoch):
            year = payload["datetime"][:4]
            items = search_all(config["stac"]["endpoint"], payload)
            print(f"discover {epoch['epoch_id']} {year}: {len(items)} intersecting items", file=sys.stderr, flush=True)
            for item in items:
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                raw_count += 1
                row = reduce_item(item, epoch, config)
                if row["catalogue_cloud_cover_percent"] is None or row["catalogue_cloud_cover_percent"] > config["stac"]["maximum_catalogue_cloud_cover_percent"]:
                    rejection_counts["cloud_threshold"] += 1
                    continue
                if row["processing_level"] not in allowed_levels:
                    rejection_counts["processing_level"] += 1
                    continue
                if not required_common.issubset(row["assets"]):
                    rejection_counts["asset_completeness"] += 1
                    continue
                if config["stac"]["require_full_aoi_footprint_coverage"] and not row["full_aoi_coverage"]:
                    rejection_counts["full_aoi_coverage"] += 1
                    continue
                candidates.append(row)

    candidates.sort(key=lambda row: (row["epoch_id"], row["datetime"], row["item_id"]))
    counts = {epoch["epoch_id"]: sum(row["epoch_id"] == epoch["epoch_id"] for row in candidates) for epoch in config["temporal_contract"]["epochs"]}
    checks = [
        {"check": "stac_returned_items", "status": "PASS" if raw_count > 0 else "FAIL", "observed": raw_count},
        {"check": "every_epoch_has_candidates", "status": "PASS" if all(value > 0 for value in counts.values()) else "FAIL", "observed": counts},
        {"check": "all_candidates_tier_1", "status": "PASS" if all(row["collection_category"] == "T1" for row in candidates) else "FAIL"},
        {"check": "all_candidates_have_full_aoi_coverage", "status": "PASS" if all(row["full_aoi_coverage"] for row in candidates) else "FAIL"},
        {"check": "all_candidates_have_required_assets", "status": "PASS" if all(required_common.issubset(row["assets"]) for row in candidates) else "FAIL"},
        {"check": "all_candidates_within_cloud_ceiling", "status": "PASS" if all(row["catalogue_cloud_cover_percent"] <= config["stac"]["maximum_catalogue_cloud_cover_percent"] for row in candidates) else "FAIL"},
    ]
    inventory = {
        "schema_version": "1.0",
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "catalogue": config["stac"]["endpoint"],
        "collection": config["stac"]["collection"],
        "raw_unique_items_examined": raw_count,
        "accepted_candidate_count": len(candidates),
        "accepted_count_by_epoch": counts,
        "rejection_counts": rejection_counts,
        "candidates": candidates,
    }
    validation = {
        "schema_version": "1.0",
        "checks": checks,
        "pass_count": sum(check["status"] == "PASS" for check in checks),
        "fail_count": sum(check["status"] == "FAIL" for check in checks),
    }
    return inventory, validation


def write_inventory_csv(path: pathlib.Path, candidates: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "epoch_id", "label_year", "item_id", "datetime", "platform", "sensor", "wrs_path", "wrs_row",
        "processing_level", "collection_category", "catalogue_cloud_cover_percent", "proj_epsg", "full_aoi_coverage", "item_url",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow({field: candidate.get(field) for field in fields})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="batch1_config.json")
    args = parser.parse_args()
    config_path = pathlib.Path(args.config).resolve()
    config = load_json(config_path)
    inventory, validation = discover(config_path)
    output = config["output"]
    inventory_path = (config_path.parent / output["inventory_json"]).resolve()
    csv_path = (config_path.parent / output["inventory_csv"]).resolve()
    validation_path = (config_path.parent / output["discovery_validation_json"]).resolve()
    write_json(inventory_path, inventory)
    write_inventory_csv(csv_path, inventory["candidates"])
    write_json(validation_path, validation)
    print(json.dumps({"inventory": str(inventory_path), "candidate_counts": inventory["accepted_count_by_epoch"], "validation": validation}, indent=2))
    return 0 if validation["fail_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
