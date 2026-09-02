# Figure 1 source and provenance

This directory documents the canonical, author-approved Figure 1 and a separate open-data audit variant. The canonical visual is used by `figures/main/figure_01_study_area_context_map.pdf` without changes to its imagery, contrast, labels, buffers or layout.

## Canonical manuscript figure

- `archive/Taxila_Figure1_author_approved_original_180dpi.png` is the lossless archival render approved for the manuscript.
- `restore_author_approved_figure1.py` verifies the archive checksum and embeds it without resampling in a deterministic 260 x 175 mm PDF.
- The 1,843 x 1,240 pixel archive provides approximately 300 dpi at its manuscript placement width.
- The manuscript caption supplies the basemap attribution and states the analytical boundary explicitly.

Rebuild the canonical figure from the repository root:

```bash
python manuscript/figures/source/figure_01/restore_author_approved_figure1.py
```

## Scientific content

- The documentary inventory retains 18 official components; 17 records with published coordinates are mapped.
- Saraikala (139-002) remains unresolved and is not silently geocoded.
- Cyan circles show the primary 500 m analytical sampling neighbourhoods centred on official component points.
- Small display-only label offsets do not change analytical coordinates or supports.
- Esri World Imagery is contextual cartography only; it is not used in Landsat, terrain, climate or CHIP calculations.
- N-125 and Taxila Museum provide orientation from the frozen OpenStreetMap snapshot.

The circles are not official property polygons, statutory protection zones or UNESCO buffer boundaries.

## Non-canonical open-data audit variant

`generate_open_data_variant_qgis.py` and the files in `data/` rebuild an alternative figure with a 10 m Sentinel-2 L2A display raster and open administrative boundaries. This variant is retained for provenance and reproducibility review but is not the manuscript Figure 1. Its outputs are written to the ignored `generated/` directory.

## SHA-256 checksums

| File | SHA-256 |
| --- | --- |
| `archive/Taxila_Figure1_author_approved_original_180dpi.png` | `ffb87ca7a17fc5cd283a7058b419fbe55ee08dfa736ff0c19468abfb34c16c22` |
| `figures/main/figure_01_study_area_context_map.pdf` | `8ee7e5c43a47e877e3af8f69d7b9d9b7eaf213c19bb4c55cbdea8bd0d2c775a1` |
| `data/Taxila_UNESCO_Master.gpkg` | `13bd4c4a53b61d8a7557c1b9a18ba08a8d26181d4d4e437f9a6c47c42ce545ff` |
| `data/osm_source_snapshot.json` | `5fcf7e819e77731f189bfbec5e15221951e653a285a2e25852e78b537872da73` |
| `data/Taxila_Sentinel2_20241026_RGB_8bit.tif` | `b5bb42028c5140caba22d033dd23ca93efe18efdd1357640ccecc8a0cf3162ad` |

## Attribution

- Canonical contextual basemap: Esri World Imagery; sources credited as Esri, Maxar, Earthstar Geographics and the GIS User Community.
- Road and museum data © OpenStreetMap contributors, ODbL: <https://www.openstreetmap.org/copyright>.
- The open-data audit variant contains modified Copernicus Sentinel data (2024), Natural Earth public-domain data and geoBoundaries CC BY 4.0 data.
