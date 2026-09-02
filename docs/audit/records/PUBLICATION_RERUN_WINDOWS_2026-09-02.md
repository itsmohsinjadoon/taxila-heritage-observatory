# Publication-profile rerun record — Windows, 2 September 2026

## Environment

- OS: Windows 11 (`Windows-11-10.0.26200-SP0`)
- Python: 3.12.13
- Seed: 311
- Profile: `publication`
- Analysis CRS: EPSG:32643
- Grid: 616 × 655 cells at 30 m
- NumPy 2.3.5; pandas 2.2.3; SciPy 1.17.0; scikit-learn 1.8.0; Matplotlib 3.10.8; seaborn 0.13.2; joblib 1.5.3
- Thread limits applied at launch: `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`

The versions match the claim-critical package versions recorded by the frozen Linux publication environment.

## Publication-scale configuration

- Dirichlet weight draws: 50,000
- Spatial-block draws per block size: 2,000
- Point-displacement draws per radius: 2,000
- Joint spatial states: 500
- Decision draws per spatial state: 10
- Climate draws: 2,000
- Proxy bootstrap draws: 2,000
- Proxy models refitted: yes

## Outcome

- Applicable headline evidence locks: 27
- Passed: 24
- Failed: 3

| Failed lock | Observed | Stored target | Absolute difference | Tolerance |
| --- | ---: | ---: | ---: | ---: |
| Primary proxy macro-F1 | 0.8300721661 | 0.830795 | 0.0007228339 | 0.000005 |
| Primary proxy overall agreement | 0.8280802292 | 0.833095 | 0.0050147708 | 0.000005 |
| Primary proxy top-label ECE | 0.0151165449 | 0.014280 | 0.0008365449 | 0.000005 |

Primary MLP block-bootstrap macro-F1 95% interval: 0.701423–0.850954. The audit fixed the class target at all six classes for every resample, matching the stated method and the supplied PDFs after rounding. The WorldCover-derived endpoint is a proxy agreement benchmark, not independent heritage-condition accuracy.

## Audit-object hashes

The full generated outputs and executed notebook are retained outside Git history in the dated local audit workspace.

| Audit object | SHA-256 |
| --- | --- |
| Executed notebook | `6BC126868514A6EE30EEDE8C0E3719D01A846CEF94C109B6536A183050C9E0AD` |
| `validation/headline_evidence_lock.csv` | `E7AACD5FCE8369DB63C37396F3D288C68F03FD9608C4F05B715D38B04D0D0D2C` |
| `tables/proxy_model_comparison.csv` | `CFAC62EE9AAB677EB8C55E26BA37B6196CD0ACAAAE66C22AD29C692362C1B78E` |
| Generated-output checksum manifest | `1E7630AC49E06663858D6270D14D971F6459FFDC3A819BA3BEF39E4B993C2955` |

## Interpretation

This exact-version Windows run reproduces the later V8 point metrics and, after the fixed-six-class bootstrap correction, the manuscript's rounded MLP interval. It does not reproduce the three frozen Linux proxy targets. All deterministic, raster, component-score, climate-table, rank, and joint-uncertainty locks pass. The result supports a platform/run-generation-sensitive proxy-refit diagnosis and does not support the statement that every headline lock passed.
