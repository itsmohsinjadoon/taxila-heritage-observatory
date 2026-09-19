# Superseded proxy-model selection record

`SUPERSEDED_enhanced_spatially_buffered_proxy_model_comparison.csv` is retained for
audit only. It records an **earlier inner cross-validation protocol** for the
land-cover proxy benchmark, under which the multilayer perceptron was
development-selected (inner macro-F1 0.871) and reported an outer macro-F1 of
0.830795 on the 12,094 / 4,467 / 4,188 split.

That protocol was revised because its inner folds did not exclude block rows
adjacent to each validation band and therefore understated spatial leakage. The
revised protocol uses three contiguous inner validation bands, each excluding an
adjacent block row from training.

**Authoritative result under the revised protocol** (used throughout the
manuscript and supplement):

| Quantity | Value | Source |
|---|---|---|
| Development-selected family | random forest | `experiments/spatial_extension/2026-09-06-windows/model_comparison.csv` |
| Inner development macro-F1 | 0.695 | same |
| Outer-stripe macro-F1 | 0.821433 (95% block-bootstrap 0.691099-0.835178) | same |
| Overall agreement | 0.812798 | same |
| Log loss / Brier / ECE | 0.497687 / 0.268923 / 0.014311 | same |

The change is disclosed in the supplement (Superseded proxy-model selection
protocol). No manuscript claim relies on the superseded file. Do not cite it as a
current result.
