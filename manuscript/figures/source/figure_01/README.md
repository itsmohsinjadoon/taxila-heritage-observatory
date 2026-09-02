# Figure 1 source and provenance

This directory is the auditable source package for `figures/main/figure_01_study_area_context_map.pdf`. The final map was regenerated on 2026-09-02 with QGIS 3.44.13 and visually inspected after independent PDF rendering.

## Scientific content

- 18 official documentary inventory records are retained; 17 records with published coordinates are mapped.
- Saraikala (139-002) remains unresolved and is not silently geocoded.
- Cyan circles are 500 m analytical sampling neighbourhoods centred on the true official coordinates.
- Small display-only label offsets do not change analytical coordinates or buffers.
- Panel (c) uses a 10 m Sentinel-2 Collection 1 Level-2A true-colour composite from 26 October 2024 (tiles T43SCT and T43SBT).
- N-125 and Taxila Museum are frozen from the included OpenStreetMap snapshot.
- Locator boundaries use Natural Earth and geoBoundaries.

The map does not show official property polygons, legal protection zones or UNESCO buffer boundaries.

## Regeneration

Run `generate_figure_01_qgis.py` with QGIS 3.44 LTR or later. The script uses only repository-relative inputs in `data/`, rebuilds the GeoPackage and editable QGIS project, and writes exports to `generated/`. It does not query live services.

On Windows with the standard QGIS LTR installation:

```powershell
$env:TAXILA_FIGURE1_ROOT = (Resolve-Path "manuscript\figures\source\figure_01").Path
& "C:\Program Files\QGIS 3.44.13\bin\qgis-ltr-bin.exe" --nologo --noversioncheck --code "$env:TAXILA_FIGURE1_ROOT\generate_figure_01_qgis.py"
```

The manuscript-facing PDF is copied from `generated/Taxila_Figure1_Final_Cyan.pdf` after visual QA. `caption.txt`, `metadata.txt` and `validation.txt` record the approved caption, source description and checks.

## SHA-256 checksums

| File | SHA-256 |
| --- | --- |
| `figures/main/figure_01_study_area_context_map.pdf` | `c78f4780494a109727b7497d300183079a4e938bef34d662231e7c2ceb4ca36e` |
| `data/Taxila_Sentinel2_20241026_RGB_8bit.tif` | `b5bb42028c5140caba22d033dd23ca93efe18efdd1357640ccecc8a0cf3162ad` |
| `data/Taxila_UNESCO_Master.gpkg` | `13bd4c4a53b61d8a7557c1b9a18ba08a8d26181d4d4e437f9a6c47c42ce545ff` |
| `data/osm_source_snapshot.json` | `5fcf7e819e77731f189bfbec5e15221951e653a285a2e25852e78b537872da73` |
| `data/natural_earth_50m_admin_0_countries.geojson` | `3e458fc036ad0a66411f2c1e6cac49c5d7bfb81cb1123bc513b22511a2b7fdeb` |
| `data/geoboundaries_PAK_ADM1_simplified.geojson` | `c7ff4e70bcf740cfba47b871a7c2b2b2b243b59e4c0656e6e1bc2a64e295d93a` |
| `data/geoboundaries_PAK_ADM2_simplified.geojson` | `f274cfc377b3b570b6fd620c2911b5e4acd14460f9cb48551747f1d698566f2e` |

## Attribution

- Contains modified Copernicus Sentinel data (2024).
- Road and museum data © OpenStreetMap contributors, ODbL: <https://www.openstreetmap.org/copyright>.
- Natural Earth data are public domain.
- geoBoundaries data are CC BY 4.0; cite Runfola et al. (2020), <https://doi.org/10.1371/journal.pone.0231866>.
