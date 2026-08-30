# Technical handoff for the later paper-writing stage

## Executed

The frozen Landsat endpoint and proxy baseline was reproduced in an isolated output directory. Open-Meteo ERA5-Seamless 1991–2025 daily data were acquired for the four unique returned weather cells covering the 17 mapped components, quality controlled, compared with NASA POWER, aggregated annually and seasonally, and matched to every retained Landsat scene date at 7, 30, 90, 180 and 365 day windows. Terrain/hydrological susceptibility, integrated ranking, 250/500/1000 m scale sensitivity, redundancy, ablation, Monte Carlo weighting, spatial-block rank uncertainty and a stricter buffered proxy-model comparison were executed.

## Verified results available for later writing

- Common endpoint support: 95.74%.
- At least two adverse endpoint criteria: 16.93%.
- All major estimates, trend slopes, product-comparison metrics and model intervals are in machine-readable CSV files.
- Primary buffered proxy model: MLP sensitivity; macro-F1 0.831, CI 0.700–0.860.
- The earlier “2024 unusually wet” interpretation is not reproduced across Open-Meteo 30-, 90- and 365-day scene-date windows; use the discrepancy record before drafting any climate interpretation.
- The fixed 500 m score ranks Giri first, while the 2,000-draw spatial-block analysis gives Bhallar median rank 1 and Giri median rank 2; rankings must be reported with their intervals.

## Not available or not defensible

No station validation, complete field-condition labels, M3 heritage-condition model, official property polygons, Saraikala geometry or causal weather-spectral inference was available. Optional hazards and future projections were not added because they were not necessary to the central experiment and lacked harmonised validation in this run.

## Writing rule

Use only the claim-evidence matrix and numerical files in this run. Preserve the distinctions between pressure, exposure, susceptibility, field-inspection priority, proxy agreement and validated damage.
