#!/usr/bin/env python3
"""Deterministic SMAA, rank-variance and inspection-budget analysis for CHIP.

The joint spatial-decision simulation records, for every draw, the sampled
landscape weight ``w``, the terrain formulation and the resulting component
score.  Because the priority score is exactly affine in ``w``

    P_i(s, m, w) = w * L_i(s) + (1 - w) * T_i(s, m),

the latent landscape term ``L`` and the three terrain terms ``T`` can be
recovered exactly from the recorded draws by least squares (the design is
noiseless; residuals are at machine precision).  Recovering them converts the
500-draw Monte Carlo into a *balanced full-factorial* design over

    spatial states  x  terrain formulations  x  a uniform grid of w,

from which the following are computed without further simulation error:

1. Rank-acceptability indices b_i(k) for every rank k.
2. SMAA central weight vectors  w_i^c = E[w | rank_i = 1]  and the terrain
   formulation distribution conditional on first rank.
3. Confidence factors  P(rank_i = 1 | w = w_i^c)  over spatial states.
4. A two-factor variance decomposition of each component's rank into
   spatial-support, decision-preference and interaction contributions.
5. An inspection-budget curve: the expected number of a scenario's three
   highest-priority components missed by a fixed inspection set of size k,
   and the probability that such a set covers all three.

Usage
-----
    python scripts/build_smaa_decision_analysis.py \
        --draws experiments/reproduction/2026-09-06-windows/tables/joint_uncertainty_component_draws.csv \
        --outdir experiments/decision_analysis/2026-09-18
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

TERRAIN_MODELS = ["equal_factors", "correlation_adjusted", "reduced_slope_drainage"]
WEIGHT_STEP = 0.005
TOP_SET = 3
RESIDUAL_TOLERANCE = 1e-9


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def recover_score_geometry(draws: pd.DataFrame):
    """Solve P = w*L + (1-w)*T_m exactly for each (spatial state, component)."""
    midx = {m: i for i, m in enumerate(TERRAIN_MODELS)}
    draws = draws.assign(mi=draws["terrain_model"].map(midx))
    if draws["mi"].isna().any():
        raise ValueError("unrecognised terrain_model value in draws")

    records = []
    for (state, cid), grp in draws.groupby(["spatial_state_id", "component_id"], sort=False):
        w = grp["landscape_weight"].to_numpy()
        mi = grp["mi"].to_numpy(dtype=int)
        y = grp["score"].to_numpy()
        design = np.zeros((len(grp), 1 + len(TERRAIN_MODELS)))
        design[:, 0] = w
        design[np.arange(len(grp)), 1 + mi] = 1.0 - w
        sol, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
        residual = float(np.abs(design @ sol - y).max())
        records.append(
            {
                "state": state,
                "component_id": cid,
                "design_rank": int(rank),
                "n_models": int(np.unique(mi).size),
                "max_residual": residual,
                "L": sol[0],
                **{f"T_{m}": sol[1 + i] for m, i in midx.items()},
            }
        )
    geom = pd.DataFrame(records)
    if geom["max_residual"].max() > RESIDUAL_TOLERANCE:
        raise AssertionError(
            f"score is not affine in w (max residual {geom['max_residual'].max():.3e})"
        )
    return geom


def build_design(geom: pd.DataFrame):
    """Keep only spatial states in which all components and all terrain
    formulations are identified, then evaluate the full factorial."""
    usable = geom[(geom["design_rank"] == 1 + len(TERRAIN_MODELS))
                  & (geom["n_models"] == len(TERRAIN_MODELS))]
    counts = usable.groupby("state").size()
    n_components = int(geom["component_id"].nunique())
    states = sorted(counts[counts == n_components].index)
    components = sorted(geom["component_id"].unique())

    piv = usable.set_index(["state", "component_id"])
    L = np.array([[piv.loc[(s, c), "L"] for c in components] for s in states])
    T = np.stack(
        [np.array([[piv.loc[(s, c), f"T_{m}"] for c in components] for s in states])
         for m in TERRAIN_MODELS],
        axis=1,
    )

    wgrid = np.round(np.arange(0.0, 1.0 + WEIGHT_STEP / 2, WEIGHT_STEP), 6)
    ranks = np.empty((wgrid.size, len(states), len(TERRAIN_MODELS), len(components)), dtype=np.int8)
    for j, w in enumerate(wgrid):
        score = w * L[:, None, :] + (1.0 - w) * T
        order = np.argsort(-score, axis=-1, kind="stable")
        rank = np.empty_like(order)
        np.put_along_axis(rank, order, np.arange(1, len(components) + 1)[None, None, :], axis=-1)
        ranks[j] = rank.astype(np.int8)
    return components, states, wgrid, ranks


def smaa_table(components, names, wgrid, ranks) -> pd.DataFrame:
    n_models = ranks.shape[2]
    wfull = np.broadcast_to(wgrid[:, None, None], ranks.shape[:3])
    mfull = np.broadcast_to(np.arange(n_models)[None, None, :], ranks.shape[:3])
    rows = []
    for ci, cid in enumerate(components):
        r = ranks[..., ci]
        first = r == 1
        n_first = int(first.sum())
        if n_first:
            central = float(wfull[first].mean())
            dist = np.bincount(mfull[first], minlength=n_models) / n_first
            j = int(np.argmin(np.abs(wgrid - central)))
            confidence = float((ranks[j, :, :, ci] == 1).mean())
        else:
            central, confidence = np.nan, 0.0
            dist = np.zeros(n_models)
        row = {
            "component_id": cid,
            "component_name": names[cid],
            "acceptability_rank1": float((r == 1).mean()),
            "acceptability_top3": float((r <= 3).mean()),
            "acceptability_top5": float((r <= 5).mean()),
            "median_rank": float(np.median(r)),
            "central_landscape_weight": central,
            "confidence_factor": confidence,
        }
        row.update({f"first_rank_share_{m}": float(dist[i]) for i, m in enumerate(TERRAIN_MODELS)})
        rows.append(row)
    return pd.DataFrame(rows).sort_values("acceptability_rank1", ascending=False)


def variance_decomposition(components, names, ranks) -> pd.DataFrame:
    n_w, n_s, n_m, _ = ranks.shape
    rows = []
    for ci, cid in enumerate(components):
        # axes -> (state, weight, terrain model); decision factor = weight x model
        r = np.transpose(ranks[..., ci].astype(np.float64), (1, 0, 2))
        flat = r.reshape(n_s, n_w * n_m)
        mu = flat.mean()
        ss_total = float(((flat - mu) ** 2).sum())
        ss_spatial = float(flat.shape[1] * ((flat.mean(axis=1) - mu) ** 2).sum())
        ss_decision = float(flat.shape[0] * ((flat.mean(axis=0) - mu) ** 2).sum())
        ss_weight = float(n_s * n_m * ((r.mean(axis=(0, 2)) - mu) ** 2).sum())
        ss_model = float(n_s * n_w * ((r.mean(axis=(0, 1)) - mu) ** 2).sum())
        rows.append(
            {
                "component_id": cid,
                "component_name": names[cid],
                "rank_variance": ss_total / flat.size,
                "fraction_spatial_support": ss_spatial / ss_total,
                "fraction_decision": ss_decision / ss_total,
                "fraction_landscape_weight": ss_weight / ss_total,
                "fraction_terrain_formulation": ss_model / ss_total,
                "fraction_interaction": (ss_total - ss_spatial - ss_decision) / ss_total,
            }
        )
    return pd.DataFrame(rows).sort_values("rank_variance", ascending=False)


def budget_curve(components, names, ranks, priority_order) -> pd.DataFrame:
    in_top = ranks <= TOP_SET
    covered = np.zeros(ranks.shape[:3], dtype=np.int16)
    rows = []
    previous_full = 0.0
    for k, ci in enumerate(priority_order, start=1):
        covered += in_top[..., ci]
        missed = TOP_SET - covered
        full = float((missed == 0).mean())
        rows.append(
            {
                "inspection_budget_k": k,
                "component_added": names[components[ci]],
                "expected_top3_missed": float(missed.mean()),
                "probability_full_coverage": full,
                "marginal_coverage_gain": full - previous_full,
            }
        )
        previous_full = full
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--draws", required=True, type=Path)
    ap.add_argument("--outdir", required=True, type=Path)
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    draws = pd.read_csv(args.draws)
    names = draws.drop_duplicates("component_id").set_index("component_id")["component_name"].to_dict()

    geom = recover_score_geometry(draws)
    components, states, wgrid, ranks = build_design(geom)

    smaa = smaa_table(components, names, wgrid, ranks)
    vdec = variance_decomposition(components, names, ranks)
    order = [components.index(cid) for cid in smaa.sort_values("acceptability_top3", ascending=False)["component_id"]]
    budget = budget_curve(components, names, ranks, order)

    outputs = {
        "smaa_acceptability_central_weights.csv": smaa,
        "rank_variance_decomposition.csv": vdec,
        "inspection_budget_curve.csv": budget,
    }
    for fname, frame in outputs.items():
        frame.to_csv(args.outdir / fname, index=False)

    weighted = lambda col: float((vdec[col] * vdec["rank_variance"]).sum() / vdec["rank_variance"].sum())
    receipt = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": Path(__file__).name,
        "input_file": str(args.draws),
        "input_sha256": sha256(args.draws),
        "recorded_draws": int(len(draws)),
        "spatial_states_recorded": int(draws["spatial_state_id"].nunique()),
        "spatial_states_fully_identified": len(states),
        "components": len(components),
        "terrain_formulations": TERRAIN_MODELS,
        "weight_grid_step": WEIGHT_STEP,
        "weight_grid_points": int(wgrid.size),
        "full_factorial_scenarios": int(ranks[..., 0].size),
        "max_affine_residual": float(geom["max_residual"].max()),
        "design_wide_variance_shares": {
            "spatial_support": weighted("fraction_spatial_support"),
            "decision": weighted("fraction_decision"),
            "landscape_weight": weighted("fraction_landscape_weight"),
            "terrain_formulation": weighted("fraction_terrain_formulation"),
            "interaction": weighted("fraction_interaction"),
        },
        "outputs": {f: sha256(args.outdir / f) for f in outputs},
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "platform": platform.platform(),
        },
        "scope": (
            "Conditional sensitivity distributions over the declared spatial and decision "
            "designs. Not posterior probabilities of deterioration and not a substitute for "
            "monument-condition assessment."
        ),
    }
    with open(args.outdir / "execution_receipt.json", "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2)
    print(json.dumps(receipt["design_wide_variance_shares"], indent=2))
    print(f"wrote {len(outputs) + 1} files to {args.outdir}")


if __name__ == "__main__":
    main()
