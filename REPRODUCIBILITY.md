# Reproducibility protocol

This protocol separates a fast engineering check from the publication-scale stochastic analysis. Run commands from the repository root.

## Environment

Use Python 3.12 and the exact package versions in `requirements-reproduction.txt` for claim-critical reruns:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements-reproduction.txt
```

`requirements.txt` contains compatible ranges for development; it must not be used to certify the locked publication values. The frozen Linux environment is recorded in `data/Taxila_CHIP_Frozen_Evidence_Data/17_reproducibility/software_environment.json`.

## Integrity and engineering checks

```bash
python scripts/validate_repository.py
python scripts/audit_scientific_data.py --output output/data-quality-report.json --quiet
```

The second command requires the scientific stack in `requirements-audit.txt`
or `requirements-reproduction.txt`. It validates the frozen checksum manifest,
declared table grains, unique keys, component coverage, complete 1991–2025 daily
climate sequence, fixed proxy partitions, and common raster grid.

## Recommended execution runner

Use the runner instead of overwriting an earlier executed notebook:

```bash
python scripts/run_reproduction.py --profile validation
python scripts/run_reproduction.py --profile publication
```

Each run receives a unique directory under `output/runs/` unless
`--output-dir` is supplied. The directory contains the executed notebook,
generated tables/figures, checksums, data-quality report and
`execution_receipt.json`. The receipt records the Git revision, notebook hash,
Python/package environment, duration and evidence-lock outcome without storing
machine-specific source paths.

Use [`notebooks/Taxila_Heritage_Observatory_Colab_Kaggle_Launcher.ipynb`](notebooks/Taxila_Heritage_Observatory_Colab_Kaggle_Launcher.ipynb)
for the same workflow on Colab or Kaggle.

To run the reduced notebook profile:

```bash
TAXILA_PROFILE=validation jupyter nbconvert \
  --to notebook --execute notebooks/Taxila_CHIP_Q1_Executable_Analysis.ipynb \
  --output Taxila_CHIP_Q1_Validation_Executed.ipynb
```

On PowerShell, set the variable first:

```powershell
$env:TAXILA_PROFILE = 'validation'
jupyter nbconvert --to notebook --execute notebooks\Taxila_CHIP_Q1_Executable_Analysis.ipynb --output Taxila_CHIP_Q1_Validation_Executed.ipynb
```

The validation profile uses smaller stochastic draws and checks pipeline integrity. It is not publication evidence. The runner preserves its receipt separately from publication-scale runs.

## Publication profile

```bash
TAXILA_PROFILE=publication jupyter nbconvert \
  --to notebook --execute notebooks/Taxila_CHIP_Q1_Executable_Analysis.ipynb \
  --output Taxila_CHIP_Q1_Publication_Executed.ipynb
```

The publication profile uses seed 311, 50,000 Dirichlet weight draws, 2,000 spatial-block draws per block size, 2,000 point-displacement draws per radius, and 500 spatial states crossed with 10 decision settings. Generated outputs are written below the notebook and ignored by Git.

## Evidence-lock decision rule

Inspect `Taxila_CHIP_Q1_outputs/validation/headline_evidence_lock.csv`. A run may be described as a clean publication reproduction only when every applicable row passes. Do not infer cross-platform bitwise reproducibility from a fixed random seed.

The authoritative stored proxy targets are macro-F1 `0.830795`, agreement `0.833095`, and ECE `0.014280`. The 2 September 2026 exact-version Windows run produced `0.830072`, `0.828080`, and `0.015117`, matching the executed V8 notebook but failing the same three locks. See `docs/audit/SCIENTIFIC_REPOSITORY_AUDIT_2026-09-02.md` before citing regenerated metrics.

## Manuscript and figure builds

The journal-neutral manuscript can be compiled with `manuscript/compile.sh` in a TeX environment containing `latexmk`, `pdflatex`, and BibTeX. Figure 1 can be regenerated with the QGIS script and frozen source bundle documented in `manuscript/figures/source/figure_01/README.md`.

The repository LaTeX is not the exact editable source of the supplied 15-page main and 18-page supplementary submission PDFs. Version the final submission source before archival release.

## Reproducibility boundary

The clean notebook and frozen evidence package cover the principal reported workflow. The older standalone package under `experiments/integrated/` preserves scientifically relevant tables and figures but currently references raw/derived inputs that are absent from its self-contained directory. Do not describe that package as independently rerunnable until those inputs or a documented canonical-data fallback are supplied.
