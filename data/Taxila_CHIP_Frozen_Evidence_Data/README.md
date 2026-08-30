# Taxila CHIP frozen evidence data

This curated data companion supports the publication-profile Jupyter notebook for the Climate-contextual Heritage Inspection Prioritisation (CHIP) framework.

## Included

- Frozen five-epoch Landsat index, pressure, land-cover and support rasters on the declared 30 m grid.
- Seventeen mapped Taxila component points, analytical circles and derived priority vectors.
- Daily and aggregated Open-Meteo ERA5-Seamless and NASA POWER climate evidence for 1991–2025.
- N33E072 elevation input and the component-level terrain/hydrology tables needed to reproduce the susceptibility analysis.
- Component/epoch tables, spatial-block uncertainty summaries, model features, validation records and original analysis scripts.
- Reviewer-requested Q1 sensitivity tables.
- Natural Earth 1:10m Admin 0 Countries, Pakistan point-of-view v5.1.1, subset to the regional map frame.

## Scientific boundary

The package supports relative landscape-pressure, terrain-susceptibility and field-inspection-priority analysis. It does not contain independent monument-condition labels, official property polygons, a verified geometry for Saraikala (139-002), local weather-station validation or every original third-party Landsat/WorldCover payload. It must not be used to claim confirmed damage, deterioration probability, causal climate effects, legal conservation boundaries or universal transfer accuracy.

## Notebook use

Keep this directory beside `Taxila_CHIP_Q1_Executable_Analysis.ipynb`, or zip it as `Taxila_CHIP_Frozen_Evidence_Data.zip` and place the zip beside the notebook. The notebook auto-detects both layouts in Colab, Kaggle and a local Jupyter environment.

The default publication profile uses seed 311, 50,000 Dirichlet weight draws, 2,000 spatial-block draws per block size, 2,000 point-displacement draws per radius, 500 spatial states crossed with 10 decision settings, and the geographically buffered proxy-label model comparison.

## Cartographic source

The Pakistan locator uses Natural Earth 1:10m Admin 0 Countries — Pakistan point-of-view, version 5.1.1. It is cartographic context only and is unrelated to the unavailable official UNESCO property polygons.
