# Taxila Heritage Observatory

A reproducible geospatial evidence framework for **climate-contextual
landscape-pressure screening and sensitivity-aware field-inspection
prioritisation across the Taxila World Heritage property, Pakistan**.

This repository consolidates the executable analysis, frozen evidence package, experiments, results, publication figures, source-traceability records, and LaTeX manuscript prepared for submission to the *Journal of Cultural Heritage*.

> **Research status (24 September 2026):** the Journal of Cultural Heritage article and separate title page have been revised. The main Overleaf article compiles to 22 pages with 8 figures and 2 tables; the title page records author contributions, no specific grant funding, no competing interests, and ChatGPT use for English wording only. The study supports relative inspection prioritisation, not independently validated monument-condition prediction. Historical reproducibility findings remain documented in the [6 September audit](docs/audit/RESEARCH_REVISION_2026-09-06.md).

![Taxila study area, mapped UNESCO components, and 500 m analytical neighbourhoods](docs/assets/figure_01_taxila_study_area_preview.png)

*Author-approved study-area cartography showing the frozen UNESCO inventory and primary 500 m analytical neighbourhoods. Esri World Imagery provides contextual display only and is not an analytical input; road and museum features are from OpenStreetMap. The circles are sampling supports, not legal or UNESCO buffer boundaries.*

## Current manuscript emphasis

The current JCH article contains 8 figures and 2 tables. Figure 2 is the raster-inclusive CHIP evidence-chain diagram; the exact decision-weight analysis reports leadership intervals and checks them against recorded Monte Carlo results. Earlier mathematical development is preserved in the [6 September audit](docs/audit/MATHEMATICAL_REVISION_2026-09-06.md).

## What the study does

The Climate-contextual Heritage Inspection Prioritisation (CHIP) framework integrates:

- five Landsat epochs from 2004–2024;
- terrain and drainage-related susceptibility derived from SRTM elevation data;
- Open-Meteo ERA5-Seamless and NASA POWER climate context for 1991–2025;
- multiscale component analysis at 250, 500, and 1000 m;
- spatial blocking, ablation, threshold, harmonisation, scale, and weight-sensitivity analyses; and
- a WorldCover-derived proxy-model benchmark.

The output is a **relative field-inspection priority**, not a monument-damage probability, confirmed deterioration map, legal conservation boundary, or causal climate-impact estimate. See [scientific boundaries](data/Taxila_CHIP_Frozen_Evidence_Data/q1_revision/missing_evidence_and_boundaries.md).

## Repository map

| Path | Contents |
| --- | --- |
| [`notebooks/`](notebooks/) | Canonical executable analysis plus a minimal Colab/Kaggle launcher |
| [`data/Taxila_CHIP_Frozen_Evidence_Data/`](data/Taxila_CHIP_Frozen_Evidence_Data/) | Frozen inputs, processed rasters/vectors, tables, statistics, configurations, validation records, and acquisition scripts |
| [`experiments/integrated/`](experiments/integrated/) | Standalone experiment code, 22 result tables, nine figures, validation records, and reproducible deliverable builders |
| [`manuscript/`](manuscript/) | Modular LaTeX manuscript, Supplementary Information, figures, tables, bibliography, and claim/evidence traceability |
| [`docs/audit/`](docs/audit/) | Manuscript QA, Q1 review-response matrix, and revision history |
| [`scripts/`](scripts/) | Reproduction runner, scientific data audit, and repository validation |

The exact environment, two execution profiles, evidence-lock rule, and known rerun boundary are documented in [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

## Current revision entry points

- [Revised main paper](manuscript/main.tex) and [supplement](manuscript/supplementary/supplementary_information.tex).
- [Executed Google Colab notebook](https://colab.research.google.com/drive/1_-gwyfIhY3L1pYl3VSb3xihCd5TwM2HI) (account permissions apply).
- [Clean self-contained notebook](notebooks/Taxila_Spatial_Benchmark_Extension.ipynb), [Colab evidence](experiments/spatial_extension/2026-09-06-colab), [Windows evidence](experiments/spatial_extension/2026-09-06-windows) and [platform comparison](experiments/spatial_extension/cross_platform_comparison.csv).
- [Corrected full reproduction](experiments/reproduction/2026-09-06-windows) and [71-check revision validation](docs/audit/REVISION_VALIDATION_2026-09-06.json).

## Quick start

### 1. Create the Python environment

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements-reproduction.txt
```

`requirements-reproduction.txt` preserves the claim-critical versions used by the frozen run. `requirements.txt` remains a compatible-range environment for development. The original Linux environment is recorded in [`software_environment.json`](data/Taxila_CHIP_Frozen_Evidence_Data/17_reproducibility/software_environment.json), and the random seed is **311**.

### 2. Run the reproducible pipeline

The recommended entry point creates a unique run directory, an executed notebook,
an output manifest, a data-quality report, and a machine-readable execution
receipt:

```bash
python scripts/run_reproduction.py --profile validation
```

Use `--profile publication` for the claim-critical stochastic rerun. A
publication run is not a clean reproduction unless its receipt reports every
applicable headline evidence lock as passing.

You can also open the canonical notebook directly:

Open [`Taxila_CHIP_Q1_Executable_Analysis.ipynb`](notebooks/Taxila_CHIP_Q1_Executable_Analysis.ipynb) from the repository root and choose **Run All**. The notebook automatically detects `data/Taxila_CHIP_Frozen_Evidence_Data/`. It also supports Colab and Kaggle layouts.

For a quick engineering check, set `TAXILA_PROFILE=validation`. Use `TAXILA_PROFILE=publication` for the full stochastic analysis: 50,000 Dirichlet weight draws, 2,000 spatial-block draws per block size, 2,000 point-displacement draws per radius, and 500 spatial states crossed with 10 decision settings. The notebook writes to `Taxila_CHIP_Q1_outputs/`, which is ignored by Git.

For Colab or Kaggle, open
[`Taxila_Heritage_Observatory_Colab_Kaggle_Launcher.ipynb`](notebooks/Taxila_Heritage_Observatory_Colab_Kaggle_Launcher.ipynb).
It installs the pinned environment, invokes the same runner, and preserves the
same receipt. Never paste a GitHub token into a notebook cell; upload a private
checkout/ZIP or use the platform's protected secret mechanism.

The repository was renamed to **Taxila Heritage Observatory** on 3 September
2026. Historical run IDs and bundle names embedded in checksum-locked evidence
are retained only for provenance; see
[`docs/BRANDING_AND_LINEAGE.md`](docs/BRANDING_AND_LINEAGE.md).

### 3. Validate the repository

```bash
python scripts/validate_repository.py
python scripts/audit_scientific_data.py --output output/data-quality-report.json --quiet
```

The structural validator is dependency-free. The scientific audit verifies the
157-file frozen checksum manifest, analytical grains and keys, temporal
coverage, proxy partitions, and alignment of all 21 GeoTIFFs.

### 4. Compile the manuscript

```bash
cd manuscript
chmod +x compile.sh
./compile.sh
```

Compiled PDFs are written to `manuscript/output/` and intentionally ignored by Git. GitHub Actions also compiles the manuscript and makes the PDFs available as temporary workflow artifacts.

## Recorded headline results

- Common 2004–2024 endpoint support: **386,280 cells (95.74%)**.
- Cells meeting at least two adverse spectral criteria: **16.93%**; all three: **1.42%**.
- Highest hierarchical 2024 local priority at 500 m: **Giri complex (0.591)**.
- The development-selected geographically buffered MLP achieved held-out macro-F1 **0.831** (95% block-bootstrap CI 0.700–0.860) on 4,188 samples.
- The clean notebook's deterministic and frozen-table checks pass in the validation profile. Full proxy-model refitting is environment-sensitive and must be compared with the pinned evidence lock before reporting a clean publication reproduction; see the dated scientific audit in [`docs/audit/`](docs/audit/).

The proxy split is derived from spatial block columns; the checksum-locked feature
table's older `partition` field is deliberately ignored. See the
[`proxy split contract`](docs/audit/PROXY_SPLIT_CONTRACT.md).

These values are tied to the frozen evidence and validation records; they should not be generalized beyond the documented study design.

## Manuscript and submission status

The current anonymized JCH article compiles in Overleaf to 22 pages with 0 errors and 0 warnings. Its source-based count is 4,837 words excluding tables and references. It contains 8 figures and 2 tables; the separate title page compiles to 2 pages with 0 errors and 0 warnings. Historical page and figure counts in [repository verification](docs/audit/REPOSITORY_VERIFICATION.md) describe an earlier manuscript version.

Before submission, check reviewer conflicts, the final acknowledgements, figure-source attribution, and the exact repository snapshot used for the reported results. No repository release or DOI has been assigned. The separate [title page](manuscript/title_page.tex) contains author and declaration details; it must be excluded from the anonymized review manuscript.

## Data and licensing

Third-party datasets retain their original provider terms. This repository does not grant a blanket licence over those materials. Provider attribution, source manifests, and limitations are documented in [`LICENSES_AND_ATTRIBUTION.md`](manuscript/LICENSES_AND_ATTRIBUTION.md), [`DATA_AVAILABILITY.md`](DATA_AVAILABILITY.md), and the frozen evidence manifests.

## Citation

Citation metadata are provided in [`CITATION.cff`](CITATION.cff). Replace the pre-submission version and repository identifier when a permanent public release or DOI is created.
