#!/usr/bin/env python3
"""Uncertainty statistics added at the 2026-09-18 revision.

Three quantities that the earlier manuscript generations reported as bare point
estimates are given explicit uncertainty or an interpretable reference here:

1. Rank concordance.  Every alternative aggregation rule and single-factor
   ablation is compared with the published hierarchical ranking on n = 17
   components.  A point Spearman rho on 17 units carries substantial sampling
   error, so a 95% Bonett-Wright interval is attached to each comparison.  All
   eight computed aggregation baselines are included, not only the four that
   earlier generations reported.

2. Scenario tier frequencies.  Inspection tiers are assigned by thresholding
   top-3 and top-5 frequencies over 27 structural scenarios.  Exact
   Clopper-Pearson intervals show which tier boundaries the 27 scenarios
   actually resolve.  The scenarios are a designed grid rather than a random
   sample, so the interval is a calibrated heuristic for the resolving power of
   27 comparisons, not a sampling statement about a scenario population.

3. Spectral convergence.  The three adverse endpoint criteria are defined at the
   20th, 20th and 80th empirical percentiles of the same common-support cell
   set, so each marginal rate is exactly 0.2 by construction and the
   co-occurrence rates expected under independence follow analytically.  The
   observed rates are reported against that reference.

Usage
-----
    python scripts/build_revision_statistics.py \
        --repo . --outdir experiments/revision_statistics/2026-09-18
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_dist
from scipy.stats import norm

N_COMPONENTS = 17
N_SCENARIOS = 27
MARGINAL_RATE = 0.2
CONVERGENCE_F32 = "data/Taxila_CHIP_Frozen_Evidence_Data/05_processed_rasters/E2004_E2024_spectral_convergence.f32"
BASELINES = "experiments/reproduction/2026-09-06-windows/tables/baseline_comparison_summary.csv"
ABLATIONS = "experiments/reproduction/2026-09-06-windows/tables/ablation_summary.csv"
SCENARIOS = "experiments/reproduction/2026-09-06-windows/tables/structural_scenario_stability.csv"

# Comparisons that appeared in the main text of the 2026-09-06 manuscript.
REPORTED_2026_09_06 = {
    "Hierarchical reference", "Full hierarchy", "Ungrouped equal-factor mean",
    "Landscape only", "Terrain only", "Without NDVI", "Without NDBI",
    "Without MNDWI", "Without slope", "Without drainage",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def spearman_interval(rho: float, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Bonett-Wright interval for Spearman's rho."""
    if not np.isfinite(rho):
        return (np.nan, np.nan)
    r = float(np.clip(rho, -0.999999, 0.999999))
    se = np.sqrt((1.0 + r * r / 2.0) / (n - 3))
    z = norm.ppf(1.0 - alpha / 2.0)
    return float(np.tanh(np.arctanh(r) - z * se)), float(np.tanh(np.arctanh(r) + z * se))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    low = 0.0 if k == 0 else float(beta_dist.ppf(alpha / 2, k, n - k + 1))
    high = 1.0 if k == n else float(beta_dist.ppf(1 - alpha / 2, k + 1, n - k))
    return low, high


def concordance_table(repo: Path) -> pd.DataFrame:
    rows = []
    for path, family, key in [(repo / BASELINES, "aggregation rule", "baseline"),
                              (repo / ABLATIONS, "single-factor ablation", "scenario")]:
        frame = pd.read_csv(path)
        seen = {row["comparison"] for row in rows}
        for _, r in frame.iterrows():
            label = str(r[key])
            if label == "Full hierarchy":
                label = "Hierarchical reference"
            if label in seen:
                continue  # domain-only rows appear in both source tables
            rho = float(r["spearman_rho_with_reference"])
            low, high = spearman_interval(rho, N_COMPONENTS)
            rows.append(
                {
                    "family": family,
                    "comparison": label,
                    "spearman_rho": rho,
                    "rho_ci_low_95": low,
                    "rho_ci_high_95": high,
                    "interval_excludes_zero": bool(low > 0 or high < 0),
                    "kendall_tau": float(r["kendall_tau_with_reference"]),
                    "top5_overlap": int(r["top5_overlap"]),
                    "max_rank_shift": float(r["maximum_absolute_rank_shift"]),
                    "first_ranked_component": str(r["rank_1_component"]),
                    "reported_in_2026_09_06_main_text": label in REPORTED_2026_09_06,
                }
            )
    return pd.DataFrame(rows)


def tier_table(repo: Path) -> pd.DataFrame:
    frame = pd.read_csv(repo / SCENARIOS)
    rows = []
    for _, r in frame.iterrows():
        k3 = int(round(float(r["top3_frequency"]) * N_SCENARIOS))
        k5 = int(round(float(r["top5_frequency"]) * N_SCENARIOS))
        lo3, hi3 = clopper_pearson(k3, N_SCENARIOS)
        lo5, hi5 = clopper_pearson(k5, N_SCENARIOS)
        rows.append(
            {
                "component_id": r["component_id"],
                "component_name": r["component_name"],
                "n_scenarios": N_SCENARIOS,
                "top3_count": k3,
                "top3_frequency": k3 / N_SCENARIOS,
                "top3_ci_low_95": lo3,
                "top3_ci_high_95": hi3,
                "top5_count": k5,
                "top5_frequency": k5 / N_SCENARIOS,
                "top5_ci_low_95": lo5,
                "top5_ci_high_95": hi5,
                "top5_interval_spans_half": bool(lo5 < 0.5 < hi5),
                "inspection_tier": r["inspection_tier"],
            }
        )
    return pd.DataFrame(rows)


def convergence_table(repo: Path) -> pd.DataFrame:
    values = np.fromfile(repo / CONVERGENCE_F32, dtype="<f4")
    valid = values[~np.isnan(values)]
    n_valid = int(valid.size)
    rows = []
    for h in (1, 2, 3):
        observed = float((valid >= h).mean())
        expected = float(sum(comb(3, j) * MARGINAL_RATE ** j * (1 - MARGINAL_RATE) ** (3 - j)
                             for j in range(h, 4)))
        rows.append(
            {
                "criteria_met_at_least": h,
                "cells": int((valid >= h).sum()),
                "observed_share": observed,
                "expected_share_under_independence": expected,
                "ratio_observed_to_expected": observed / expected,
            }
        )
    frame = pd.DataFrame(rows)
    frame.insert(0, "common_support_cells", n_valid)
    frame.insert(1, "grid_cells_total", int(values.size))
    # each marginal is exactly 0.2 by construction; verify before reporting
    realised = float(valid.sum() / (3 * n_valid))
    if abs(realised - MARGINAL_RATE) > 1e-6:
        raise AssertionError(f"marginal rate is {realised:.6f}, expected {MARGINAL_RATE}")
    return frame


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--outdir", type=Path, required=True)
    args = ap.parse_args()
    outdir = args.outdir if args.outdir.is_absolute() else args.repo / args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    outputs = {
        "baseline_ablation_concordance_with_ci.csv": concordance_table(args.repo),
        "tier_frequency_clopper_pearson.csv": tier_table(args.repo),
        "spectral_convergence_independence_benchmark.csv": convergence_table(args.repo),
    }
    for name, frame in outputs.items():
        frame.to_csv(outdir / name, index=False)

    conc = outputs["baseline_ablation_concordance_with_ci.csv"]
    receipt = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": Path(__file__).name,
        "n_components_for_rho": N_COMPONENTS,
        "n_structural_scenarios": N_SCENARIOS,
        "comparisons_total": int(len(conc)),
        "comparisons_absent_from_2026_09_06_main_text": int((~conc["reported_in_2026_09_06_main_text"]).sum()),
        "comparisons_with_interval_spanning_zero": int((~conc["interval_excludes_zero"]).sum()),
        "outputs": {name: sha256(outdir / name) for name in outputs},
    }
    with open(outdir / "execution_receipt.json", "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
