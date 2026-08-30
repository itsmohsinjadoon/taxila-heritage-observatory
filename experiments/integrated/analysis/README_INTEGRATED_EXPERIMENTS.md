# Taxila PreserveX integrated experiments

This bundle reproduces the standalone **Experiments, Results and Discussion**
section for the 2004–2024 Taxila study. It contains the executed analysis code,
22 result tables, nine publication figures, external forcing data, validation
records, the formula-audited workbook and the rendered/verified DOCX section.

## Scientific scope

The pipeline executes six experiment families:

1. Exact reproduction of the accepted Landsat endpoint screen.
2. NASA POWER climate extremes matched to five three-year satellite windows.
3. Terrain and drainage-related susceptibility from a one-arc-second elevation tile.
4. Five-model spatially blocked land-cover proxy comparison with 2,000 block bootstraps.
5. Hierarchically weighted landscape, terrain and climate integration.
6. Scale, factor-ablation and 50,000-draw weight-sensitivity analysis.

The integrated score is a **relative field-inspection priority**. It is not a
monument-damage probability and has not been calibrated against a complete
heritage-condition outcome. Model scores are agreement with a
WorldCover-consensus proxy under spatial blocking, not independent
human-reference accuracy.

## Primary code

- `extract_geotiff_raw.mjs` extracts Landsat indices, reflectance and mapped
  land-cover rasters from the frozen source bundles.
- `run_integrated_experiments.py` executes all numerical experiments, writes
  tables and figures, and performs the analytical validation gates.
- `build_results_workbook.mjs` constructs the formula-audited XLSX companion
  with `@oai/artifact-tool`.
- `build_experiments_results_discussion.py` creates the standalone manuscript
  section with exact table geometry, alt text and publication figures.

## Re-execution order

Run the extraction script after placing the frozen GeoTIFF inputs in the paths
recorded by `raw_manifest.json`, then execute:

```bash
NODE_PATH="$CODEX_PRIMARY_RUNTIME_NODE_MODULES" \
  "$CODEX_PRIMARY_RUNTIME_NODE" extract_geotiff_raw.mjs

MPLCONFIGDIR=/tmp/mpl_taxila \
  "$CODEX_PRIMARY_RUNTIME_PYTHON" run_integrated_experiments.py

"$CODEX_PRIMARY_RUNTIME_PYTHON" build_experiments_results_discussion.py
```

The workbook builder requires a writable temporary directory containing a
`node_modules` symlink to `$CODEX_PRIMARY_RUNTIME_NODE_MODULES`; its source
code is included for exact inspection.

## Headline executed results

- Common 2004–2024 endpoint support: 386,280 cells (95.74%).
- Cells meeting at least two adverse spectral criteria: 16.93%.
- Cells meeting all three adverse spectral criteria: 1.42%.
- Highest matched climate-extreme score: 2024 (0.526), dominated by wet anomalies.
- Highest hierarchical 2024 local priority at 500 m: Giri complex (0.591).
- Largest spectral-convergence share at 500 m: Bhallar (31.95%).
- Best proxy point macro-F1: neural MLP (0.887), statistically indistinguishable
  from tree ensembles under whole-block resampling.
- Analytical validation gates: 20/20 passed.

## Audit notes

NDVI- and NDBI-derived pressures had Spearman correlation 0.972. The final
analysis groups them into one surface-cover subdomain before balancing that
subdomain against MNDWI. Mapped built-up and bare shares are comparison
variables only and do not enter the primary composite.

All randomness uses a fixed seed. Source hashes and the exact frozen-bundle
hashes are recorded in `SOURCE_DATA_MANIFEST.md`.
