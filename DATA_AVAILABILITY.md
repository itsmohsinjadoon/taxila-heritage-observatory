# Data availability and reproducibility boundary

## Included in this public archive

- Frozen five-epoch Landsat-derived index, pressure, land-cover, and support rasters on the declared 30 m grid.
- Taxila component points, analytical neighbourhoods, and derived field-inspection-priority vectors.
- Open-Meteo ERA5-Seamless and NASA POWER climate records used by the study.
- SRTM elevation input used for the terrain and hydrology analysis.
- Derived feature tables, model summaries, uncertainty statistics, figures, and validation records.
- Acquisition, preprocessing, analysis, and validation scripts.

## Not included or not independently verified

- Every original third-party Landsat and WorldCover payload.
- Official UNESCO property polygons or legal buffer boundaries for component-level analysis.
- A verified geometry for Saraikala (139-002).
- Complete, independent monument-condition labels.
- Local weather-station validation, field-calibrated drainage measurements, or a harmonised multi-hazard event inventory.

## Permitted interpretation

The package supports reproduction of relative landscape pressure, terrain/hydrological susceptibility, climate context, and relative field-inspection priority. It does not support claims of confirmed damage, deterioration probability, causal climate effects, legal conservation boundaries, future loss, or universal transfer accuracy.

The authoritative file-level inventory, checksums, provider metadata, and data dictionary are under [`data/Taxila_CHIP_Frozen_Evidence_Data/`](data/Taxila_CHIP_Frozen_Evidence_Data/).

## Reacquiring omitted upstream payloads

Large or licence-controlled upstream satellite payloads are not duplicated in Git. Reacquisition and provenance material is versioned instead:

- Landsat discovery and preprocessing: [`discover_landsat_scenes.py`](data/Taxila_CHIP_Frozen_Evidence_Data/03_download_scripts/discover_landsat_scenes.py) and [`acquire_preprocess_landsat.py`](data/Taxila_CHIP_Frozen_Evidence_Data/03_download_scripts/acquire_preprocess_landsat.py).
- Open-Meteo acquisition: [`acquire_open_meteo.py`](data/Taxila_CHIP_Frozen_Evidence_Data/03_download_scripts/acquire_open_meteo.py), with the exact request manifest under `01_sources_and_manifests/`.
- Provider identifiers, URLs, coverage, resolution, licensing notes and analytical roles: [`source_manifest.csv`](data/Taxila_CHIP_Frozen_Evidence_Data/01_sources_and_manifests/source_manifest.csv).
- Landsat item/date selection: [`retained_landsat_scene_dates.csv`](data/Taxila_CHIP_Frozen_Evidence_Data/13_tables/retained_landsat_scene_dates.csv).
- File inventory and integrity: [`MANIFEST.csv`](data/Taxila_CHIP_Frozen_Evidence_Data/MANIFEST.csv) and [`SHA256SUMS.txt`](data/Taxila_CHIP_Frozen_Evidence_Data/SHA256SUMS.txt).

Upstream services and catalogues can change. Preserve provider item identifiers and compare the regenerated files with the recorded grids, scene list and checksums before substituting them for frozen study inputs. Do not commit raw archives or any single file approaching GitHub's 100 MiB limit; use an archival release, DOI-backed repository or Git LFS only after confirming redistribution rights and author approval.

## Known standalone-package gap

The principal clean notebook runs from the frozen evidence package. The older `experiments/integrated/` snapshot retains scientifically relevant results but its source script refers to absent raw/derived arrays, including an E2019 six-band reflectance array. It is preserved as an audited experiment snapshot, not represented as an independently complete source-to-result bundle. See the dated scientific audit before attempting that rerun.
