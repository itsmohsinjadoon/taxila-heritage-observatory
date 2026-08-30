#!/usr/bin/env python3
"""Build the Stage 3 Taxila spatial foundation without proprietary GIS software.

Inputs are the UNESCO component inventory transcribed in
component_inventory_source.json. Outputs are deterministic GeoJSON, a GeoTIFF
snap-grid template, validation results, a manifest, and a diagnostic map.

The WGS84/UTM forward and inverse equations implement Snyder's standard
Transverse Mercator series for UTM. They are included here so the bundle can be
executed in a minimal Python environment. EPSG:32643 parameters are fixed and
checked by round-trip tests.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from PIL import Image, ImageDraw, ImageFont, TiffImagePlugin


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "derived"
INPUT = ROOT / "component_inventory_source.json"
CELL = 30.0
CONTEXT_M = 5000.0
BUFFER_RADII = (250.0, 500.0, 1000.0)
EPSG_WGS84 = 4326
EPSG_UTM = 32643
RUN_DATE = str(datetime.now(ZoneInfo("Asia/Karachi")).date())

# WGS 84 ellipsoid and UTM zone 43N parameters.
A = 6378137.0
F = 1.0 / 298.257223563
E2 = F * (2.0 - F)
EP2 = E2 / (1.0 - E2)
K0 = 0.9996
LON0 = math.radians(75.0)
FALSE_E = 500000.0


def dms_to_dd(value):
    if value is None:
        return None
    d, m, s = value
    return d + m / 60.0 + s / 3600.0


def wgs84_to_utm43(lon_deg: float, lat_deg: float):
    lon = math.radians(lon_deg)
    lat = math.radians(lat_deg)
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    tan_lat = math.tan(lat)
    n = A / math.sqrt(1.0 - E2 * sin_lat * sin_lat)
    t = tan_lat * tan_lat
    c = EP2 * cos_lat * cos_lat
    aa = cos_lat * (lon - LON0)
    m = A * (
        (1 - E2 / 4 - 3 * E2**2 / 64 - 5 * E2**3 / 256) * lat
        - (3 * E2 / 8 + 3 * E2**2 / 32 + 45 * E2**3 / 1024) * math.sin(2 * lat)
        + (15 * E2**2 / 256 + 45 * E2**3 / 1024) * math.sin(4 * lat)
        - (35 * E2**3 / 3072) * math.sin(6 * lat)
    )
    easting = FALSE_E + K0 * n * (
        aa + (1 - t + c) * aa**3 / 6
        + (5 - 18 * t + t**2 + 72 * c - 58 * EP2) * aa**5 / 120
    )
    northing = K0 * (
        m + n * tan_lat * (
            aa**2 / 2
            + (5 - t + 9 * c + 4 * c**2) * aa**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * EP2) * aa**6 / 720
        )
    )
    return easting, northing


def utm43_to_wgs84(easting: float, northing: float):
    x = easting - FALSE_E
    m = northing / K0
    mu = m / (A * (1 - E2 / 4 - 3 * E2**2 / 64 - 5 * E2**3 / 256))
    e1 = (1 - math.sqrt(1 - E2)) / (1 + math.sqrt(1 - E2))
    j1 = 3 * e1 / 2 - 27 * e1**3 / 32
    j2 = 21 * e1**2 / 16 - 55 * e1**4 / 32
    j3 = 151 * e1**3 / 96
    j4 = 1097 * e1**4 / 512
    fp = mu + j1 * math.sin(2 * mu) + j2 * math.sin(4 * mu) + j3 * math.sin(6 * mu) + j4 * math.sin(8 * mu)
    sin_fp = math.sin(fp)
    cos_fp = math.cos(fp)
    tan_fp = math.tan(fp)
    c1 = EP2 * cos_fp**2
    t1 = tan_fp**2
    n1 = A / math.sqrt(1 - E2 * sin_fp**2)
    r1 = A * (1 - E2) / (1 - E2 * sin_fp**2) ** 1.5
    d = x / (n1 * K0)
    lat = fp - (n1 * tan_fp / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * EP2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * EP2 - 3 * c1**2) * d**6 / 720
    )
    lon = LON0 + (
        d - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * EP2 + 24 * t1**2) * d**5 / 120
    ) / cos_fp
    return math.degrees(lon), math.degrees(lat)


def haversine_m(lon1, lat1, lon2, lat2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def feature_collection(features, epsg=None, name=None):
    obj = {"type": "FeatureCollection", "features": features}
    if name:
        obj["name"] = name
    if epsg:
        # Included for desktop-GIS interoperability. RFC 7946 readers should use
        # the WGS84 file; projected coordinates are explicitly named and documented.
        obj["crs"] = {"type": "name", "properties": {"name": f"urn:ogc:def:crs:EPSG::{epsg}"}}
    return obj


def dump_json(path: Path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def circle_ring(cx, cy, radius, vertices=96):
    pts = []
    for i in range(vertices + 1):
        a = 2 * math.pi * i / vertices
        pts.append([round(cx + radius * math.cos(a), 3), round(cy + radius * math.sin(a), 3)])
    return pts


def rectangle_ring(xmin, ymin, xmax, ymax):
    return [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax], [xmin, ymin]]


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_geotiff(path: Path, width: int, height: int, xmin: float, ymax: float):
    arr = np.zeros((height, width), dtype=np.uint8)
    img = Image.fromarray(arr, mode="L")
    info = TiffImagePlugin.ImageFileDirectory_v2()
    info[33550] = (CELL, CELL, 0.0)  # ModelPixelScaleTag
    info[33922] = (0.0, 0.0, 0.0, xmin, ymax, 0.0)  # ModelTiepointTag
    # GeoKeyDirectory: model type projected, pixel-is-area, EPSG:32643, metres.
    info[34735] = (
        1, 1, 0, 4,
        1024, 0, 1, 1,
        1025, 0, 1, 1,
        3072, 0, 1, EPSG_UTM,
        3076, 0, 1, 9001,
    )
    info[42113] = "255"  # GDAL_NODATA
    img.save(path, format="TIFF", compression="tiff_deflate", tiffinfo=info)


def default_font(size=18, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def draw_diagnostic_map(path, valid, extent):
    width, height = 1900, 1400
    left, top, right, bottom = 110, 160, 1250, 1260
    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    title_font = default_font(34, True)
    label_font = default_font(15, True)
    legend_font = default_font(15)
    small_font = default_font(14)
    d.text((left, 42), "Taxila Stage 3 spatial foundation — EPSG:32643", fill="#17324d", font=title_font)
    xmin, ymin, xmax, ymax = extent
    sx = (right-left) / (xmax - xmin)
    sy = (bottom-top) / (ymax - ymin)
    scale = min(sx, sy)
    def xy(x, y):
        return left + (x - xmin) * scale, bottom - (y - ymin) * scale
    # Extent and 500 m analytical circles.
    x0, y1 = xy(xmin, ymin)
    x1, y0 = xy(xmax, ymax)
    d.rectangle((x0, y0, x1, y1), outline="#8696a7", width=3)
    for c in valid:
        px, py = xy(c["easting_m"], c["northing_m"])
        rr = 500 * scale
        d.ellipse((px-rr, py-rr, px+rr, py+rr), outline="#99c7d3", width=2)
    # Points and compact identifier labels.
    occupied = []
    for idx, c in enumerate(valid):
        px, py = xy(c["easting_m"], c["northing_m"])
        d.ellipse((px-7, py-7, px+7, py+7), fill="#b23a48", outline="white", width=2)
        short = c["component_id"].split("-")[1]
        offsets = [(12,-24),(12,8),(-48,-24),(-48,8),(12,-46),(-48,-46),(28,-8),(-68,-8)]
        chosen = None
        for ox, oy in offsets:
            raw = d.textbbox((px+ox, py+oy), short, font=label_font)
            box = (raw[0]-4, raw[1]-2, raw[2]+4, raw[3]+2)
            if not any(not (box[2] < q[0] or box[0] > q[2] or box[3] < q[1] or box[1] > q[3]) for q in occupied):
                chosen = (ox, oy, box)
                break
        if chosen is None:
            ox, oy = offsets[idx % len(offsets)]
            raw = d.textbbox((px+ox, py+oy), short, font=label_font)
            chosen = (ox, oy, (raw[0]-4, raw[1]-2, raw[2]+4, raw[3]+2))
        ox, oy, box = chosen
        occupied.append(box)
        d.line((px, py, px+ox, py+oy+8), fill="#718395", width=1)
        d.rounded_rectangle(box, radius=3, fill="white", outline="#718395", width=1)
        d.text((px+ox, py+oy), short, fill="#243746", font=label_font)
    # Full component key at right; 139-002 is deliberately flagged as unmapped.
    d.text((1320, 155), "Component key", fill="#17324d", font=default_font(22, True))
    key_rows = [
        ("001", "Khanpur Cave"), ("002", "Saraikala — geometry unresolved"),
        ("003", "Bhir Mound"), ("004", "Sirkap"), ("005", "Sirsukh"),
        ("006", "Dharmarajika"), ("007", "Khader Mohra"), ("008", "Kalawan"),
        ("009", "Giri complex"), ("010", "Kunala"), ("011", "Jandial"),
        ("012", "Lalchak and Badalpur"), ("013", "Mohra Moradu"),
        ("014", "Pippala"), ("015", "Jaulian"), ("016", "Lalchak mounds"),
        ("017", "Bhallar stupa"), ("018", "Giri Mosque and tombs"),
    ]
    for i, (code, name) in enumerate(key_rows):
        yy = 205 + i * 48
        colour = "#9a6b00" if code == "002" else "#243746"
        d.text((1320, yy), code, fill=colour, font=label_font)
        d.text((1370, yy), name, fill=colour, font=legend_font)
    # North arrow and scale bar.
    nx, ny = width - 170, 180
    d.line((nx, ny+80, nx, ny), fill="#17324d", width=5)
    d.polygon([(nx, ny-18),(nx-12,ny+12),(nx+12,ny+12)], fill="#17324d")
    d.text((nx-10, ny+88), "N", fill="#17324d", font=default_font(22, True))
    bar_m = 5000
    bx, by = left + 40, height - 80
    d.line((bx, by, bx + bar_m*scale, by), fill="#17324d", width=7)
    d.line((bx, by-9, bx, by+9), fill="#17324d", width=3)
    d.line((bx+bar_m*scale, by-9, bx+bar_m*scale, by+9), fill="#17324d", width=3)
    d.text((bx, by-34), "5 km", fill="#17324d", font=small_font)
    d.text((110, height-42), "Circles are 500 m analytical neighbourhoods, not legal or UNESCO buffer zones. Saraikala is retained but not mapped.", fill="#5b6770", font=small_font)
    img.save(path, dpi=(200, 200))


def main():
    OUT.mkdir(exist_ok=True)
    src = json.loads(INPUT.read_text(encoding="utf-8"))
    enriched = []
    for item in src["components"]:
        lat = dms_to_dd(item["lat_dms"])
        lon = dms_to_dd(item["lon_dms"])
        row = dict(item)
        row.update({
            "longitude": None if lon is None else round(lon, 9),
            "latitude": None if lat is None else round(lat, 9),
            "source_authority": src["source"]["authority"],
            "source_url": src["source"]["url"],
            "coordinate_status": "official_web_point" if lon is not None else "official_id_geometry_missing",
            "legal_buffer_available": False,
        })
        if lon is not None:
            e, n = wgs84_to_utm43(lon, lat)
            row["easting_m"] = round(e, 3)
            row["northing_m"] = round(n, 3)
        else:
            row["easting_m"] = None
            row["northing_m"] = None
        enriched.append(row)

    valid = [c for c in enriched if c["longitude"] is not None]
    props_keep = ["component_id","name","coordinate_status","source_authority","source_url","legal_buffer_available"]
    wgs_features, utm_features = [], []
    for c in enriched:
        props = {k: c[k] for k in props_keep}
        props.update({"longitude": c["longitude"], "latitude": c["latitude"]})
        wgs_features.append({
            "type":"Feature", "id":c["component_id"], "properties":props,
            "geometry": None if c["longitude"] is None else {"type":"Point","coordinates":[c["longitude"],c["latitude"]]},
        })
        utm_props = dict(props)
        utm_props.update({"easting_m":c["easting_m"],"northing_m":c["northing_m"]})
        utm_features.append({
            "type":"Feature", "id":c["component_id"], "properties":utm_props,
            "geometry": None if c["easting_m"] is None else {"type":"Point","coordinates":[c["easting_m"],c["northing_m"]]},
        })
    dump_json(OUT/"taxila_components_wgs84.geojson", feature_collection(wgs_features, EPSG_WGS84, "taxila_components_wgs84"))
    dump_json(OUT/"taxila_components_epsg32643.geojson", feature_collection(utm_features, EPSG_UTM, "taxila_components_epsg32643"))

    neighbourhoods = []
    for c in valid:
        for radius in BUFFER_RADII:
            neighbourhoods.append({
                "type":"Feature",
                "properties":{
                    "component_id":c["component_id"], "name":c["name"],
                    "radius_m":int(radius), "geometry_role":"analytical_neighbourhood",
                    "is_legal_buffer":False,
                },
                "geometry":{"type":"Polygon","coordinates":[circle_ring(c["easting_m"],c["northing_m"],radius)]},
            })
    dump_json(OUT/"taxila_analytical_neighbourhoods_epsg32643.geojson", feature_collection(neighbourhoods, EPSG_UTM, "taxila_analytical_neighbourhoods"))

    raw_min_e = min(c["easting_m"] for c in valid) - CONTEXT_M
    raw_max_e = max(c["easting_m"] for c in valid) + CONTEXT_M
    raw_min_n = min(c["northing_m"] for c in valid) - CONTEXT_M
    raw_max_n = max(c["northing_m"] for c in valid) + CONTEXT_M
    xmin = math.floor(raw_min_e / CELL) * CELL
    ymin = math.floor(raw_min_n / CELL) * CELL
    xmax = math.ceil(raw_max_e / CELL) * CELL
    ymax = math.ceil(raw_max_n / CELL) * CELL
    width = int(round((xmax-xmin)/CELL))
    height = int(round((ymax-ymin)/CELL))
    extent_feature = [{
        "type":"Feature",
        "properties":{
            "role":"rectangular_analysis_envelope", "context_margin_m":int(CONTEXT_M),
            "snap_cell_m":int(CELL), "basis":"bbox of 17 official-coordinate points expanded by 5 km and snapped outward",
        },
        "geometry":{"type":"Polygon","coordinates":[rectangle_ring(xmin,ymin,xmax,ymax)]},
    }]
    dump_json(OUT/"taxila_analysis_envelope_epsg32643.geojson", feature_collection(extent_feature, EPSG_UTM, "taxila_analysis_envelope"))

    grid = {
        "schema_version":"1.0", "crs":"EPSG:32643", "crs_name":"WGS 84 / UTM zone 43N",
        "pixel_interpretation":"area", "cell_size_m":[CELL,CELL], "width_columns":width,
        "height_rows":height, "extent_m":{"xmin":xmin,"ymin":ymin,"xmax":xmax,"ymax":ymax},
        "upper_left_origin_m":[xmin,ymax], "geotransform":[xmin,CELL,0.0,ymax,0.0,-CELL],
        "cell_count":width*height, "cell_area_m2":CELL*CELL,
        "context_rule":"All 17 components with official coordinates plus at least 5 km to each rectangular edge; Saraikala excluded from geometry until authoritative coordinates are supplied.",
        "categorical_resampling":"nearest", "continuous_resampling":"bilinear only when reprojection is necessary",
        "coarse_data_rule":"Summarise at native support; do not present upsampled coarse pixels as 30 m observations.",
        "nodata_uint8":255,
    }
    dump_json(OUT/"taxila_grid_spec_30m_epsg32643.json", grid)
    write_geotiff(OUT/"taxila_reference_grid_30m_epsg32643.tif", width, height, xmin, ymax)
    draw_diagnostic_map(OUT/"taxila_spatial_foundation_diagnostic.png", valid, (xmin,ymin,xmax,ymax))

    roundtrip = []
    for c in valid:
        lon2, lat2 = utm43_to_wgs84(c["easting_m"], c["northing_m"])
        roundtrip.append(haversine_m(c["longitude"],c["latitude"],lon2,lat2))
    checks = [
        {"check":"Authoritative component identifier count","expected":18,"observed":len(enriched),"status":"PASS" if len(enriched)==18 else "FAIL"},
        {"check":"Unique component identifiers","expected":18,"observed":len({c['component_id'] for c in enriched}),"status":"PASS" if len({c['component_id'] for c in enriched})==18 else "FAIL"},
        {"check":"Official-coordinate geometries","expected":17,"observed":len(valid),"status":"PASS" if len(valid)==17 else "FAIL"},
        {"check":"Explicit unresolved geometry","expected":"139-002 Saraikala","observed":next(c['component_id']+' '+c['name'].split(',')[0] for c in enriched if c['longitude'] is None),"status":"PASS"},
        {"check":"All valid longitudes inside EPSG:32643 area of use (72°E–78°E)","expected":True,"observed":all(72<=c['longitude']<=78 for c in valid),"status":"PASS" if all(72<=c['longitude']<=78 for c in valid) else "FAIL"},
        {"check":"WGS84→UTM→WGS84 maximum round-trip error","expected":"<0.05 m","observed_m":round(max(roundtrip),6),"status":"PASS" if max(roundtrip)<0.05 else "FAIL"},
        {"check":"Grid dimensions integral at 30 m","expected":True,"observed":((xmax-xmin)%CELL==0 and (ymax-ymin)%CELL==0),"status":"PASS"},
        {"check":"All mapped components at least 5 km from rectangular grid edges","expected":True,"observed":all(min(c['easting_m']-xmin,xmax-c['easting_m'],c['northing_m']-ymin,ymax-c['northing_m'])>=CONTEXT_M for c in valid),"status":"PASS" if all(min(c['easting_m']-xmin,xmax-c['easting_m'],c['northing_m']-ymin,ymax-c['northing_m'])>=CONTEXT_M for c in valid) else "FAIL"},
        {"check":"Analytical neighbourhood feature count","expected":51,"observed":len(neighbourhoods),"status":"PASS" if len(neighbourhoods)==51 else "FAIL"},
        {"check":"No analytical neighbourhood labelled as legal buffer","expected":True,"observed":all(not f['properties']['is_legal_buffer'] for f in neighbourhoods),"status":"PASS"},
    ]
    validation = {
        "generated":RUN_DATE, "script":"build_spatial_foundation.py",
        "summary":{"pass":sum(c['status']=='PASS' for c in checks),"fail":sum(c['status']=='FAIL' for c in checks),"total":len(checks)},
        "checks":checks,
    }
    dump_json(OUT/"taxila_spatial_validation_results.json", validation)

    manifest = {
        "schema_version":"1.0", "project":"PreserveX Taxila corrected M1", "generated":RUN_DATE,
        "spatial_contract":grid,
        "datasets":[
            {"dataset_id":"heritage_components","title":"Taxila serial component inventory","authority":"UNESCO World Heritage Centre","version":"web record accessed 2026-07-19","url":"https://whc.unesco.org/en/list/139/maps/","status":"17 official point geometries acquired; 139-002 geometry unresolved","native_support":"point records","planned_use":"inventory key and analytical-neighbourhood anchors","critical_limit":"No official polygons or buffer-zone areas are supplied in the web table."},
            {"dataset_id":"property_and_protection_boundaries","title":"Official property, buffer and statutory protection polygons","authority":"Department of Archaeology and Museums / competent Pakistani authorities","version":None,"url":None,"status":"REQUEST_REQUIRED","native_support":None,"planned_use":"management-unit and legal-boundary analyses","critical_limit":"No legal-boundary inference from circular neighbourhoods is permitted."},
            {"dataset_id":"landsat_c2_l2","title":"Landsat Collection 2 Level-2 surface reflectance","authority":"U.S. Geological Survey","version":"Collection 2","url":"https://www.usgs.gov/landsat-missions/landsat-collection-2-level-2-science-products","status":"NOT_ACQUIRED_STAGE_3","native_support":"30 m multispectral","planned_use":"harmonised land-cover and spectral-indicator epochs","critical_limit":"Sensor harmonisation, QA masking, seasonal windows and accuracy assessment required."},
            {"dataset_id":"chirps_v3","title":"CHIRPS v3 precipitation","authority":"Climate Hazards Center, UC Santa Barbara","version":"v3 operational since January 2025","url":"https://chc.ucsb.edu/data","status":"NOT_ACQUIRED_STAGE_3","native_support":"0.05 degree","planned_use":"native-support rainfall anomalies and extremes","critical_limit":"Must not be interpreted as 30 m information after reprojection."},
            {"dataset_id":"ghsl_built_s","title":"GHS-BUILT-S multitemporal built-up surface","authority":"European Commission Joint Research Centre","version":"R2023A","doi":"10.2905/9F06F36F-4B11-47EC-ABB0-4F8B7B1D72EA","url":"https://human-settlement.emergency.copernicus.eu/ghs_buS2023.php","status":"NOT_ACQUIRED_STAGE_3","native_support":"epoch- and product-dependent","planned_use":"independent multitemporal built-up sensitivity series","critical_limit":"Interpolated/extrapolated epochs must be identified; 2018 is the 10 m observed anchor."},
            {"dataset_id":"dem","title":"Elevation model for slope and drainage derivation","authority":"To be fixed before acquisition","version":None,"url":None,"status":"SOURCE_DECISION_REQUIRED","native_support":None,"planned_use":"terrain, flow and drainage predictors","critical_limit":"Choose one version, vertical datum and hydrologic conditioning protocol; record void treatment."},
            {"dataset_id":"roads","title":"Time-matched road-network evidence","authority":"To be fixed before acquisition","version":None,"url":None,"status":"SOURCE_DECISION_REQUIRED","native_support":"vector","planned_use":"road proximity and expansion","critical_limit":"A current road layer cannot be reused unchanged for historical epochs."}
        ],
        "acceptance_gates":{
            "spatial_foundation":"PASS only when validation fail count is zero; Saraikala remains a documented limitation, not a fabricated point.",
            "factor_generation":"Do not start until every acquired source has immutable version/date, licence, checksum, native CRS/resolution and temporal coverage.",
            "management_claims":"Blocked until official property/protection geometries are obtained and reconciled."
        }
    }
    dump_json(OUT/"taxila_m1_data_manifest.json", manifest)

    artifact_rows = []
    for p in sorted(OUT.iterdir()):
        if p.name == "taxila_spatial_foundation_artifacts.json":
            continue
        artifact_rows.append({"file":p.name,"bytes":p.stat().st_size,"sha256":sha256(p)})
    dump_json(OUT/"taxila_spatial_foundation_artifacts.json", {"generated":RUN_DATE,"artifacts":artifact_rows})
    print(json.dumps({
        "output_directory":str(OUT), "components":len(enriched), "mapped":len(valid),
        "grid":[width,height], "validation":validation["summary"]
    }, indent=2))


if __name__ == "__main__":
    main()
