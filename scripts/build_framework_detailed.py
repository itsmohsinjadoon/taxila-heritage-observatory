#!/usr/bin/env python3
"""Figure 2: the CHIP workflow, drawn from the study's own data.

An earlier revision drew this figure as a grid of labelled text boxes. That
carried the pipeline in prose rather than in graphics, and it advertised a
land-cover classification benchmark that is out of scope for the article. This
version renders each stage of the workflow as the actual data product that
stage produces, so the figure is a visual roadmap rather than a table:

    01 landscape evidence     E2024 relative landscape pressure raster
    02 adverse convergence    count of adverse endpoint criteria per cell
    03 oriented percentiles   landscape-pressure distribution and its
                              empirical cumulative transform
    04 rank uncertainty       median component rank and 95% interval
    05 inspection set         component priorities in map space

Thumbnails are deliberately small: Figures 3, 4 and 7 present the pressure
epochs, the convergence surface and the priority map at full size, and this
figure signposts them rather than competing with them.

Usage:
    python scripts/build_framework_figure.py
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "Taxila_CHIP_Frozen_Evidence_Data"
OUT = ROOT / "manuscript" / "figures" / "main"
STEM = "figure_02_chip_framework"

INK, ACCENT, MUTED, GRID = "#203648", "#A63603", "#8C99A2", "#C7D0D6"
CORE = {
    "Giri complex of monuments",
    "Giri Mosque and tombs",
    "Jaulian stupa and monastery",
}


def load_raster(name, spec):
    """Read a frozen float32 raster and mask its nodata value."""
    arr = np.fromfile(DATA / "05_processed_rasters" / name, dtype="<f4")
    arr = arr.reshape(spec["height"], spec["width"]).astype(float)
    arr[arr == spec["nodata"]] = np.nan
    return arr


def frame(ax):
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
        spine.set_linewidth(0.7)


def stage(ax, number, label):
    ax.set_title(f"{number}  {label}", fontsize=7.4, color=INK, pad=3.5)


def main():
    spec = json.loads((DATA / "05_processed_rasters" / "derived_raster_spec.json").read_text())
    pressure = load_raster("E2024_relative_landscape_pressure.f32", spec)
    convergence = load_raster("E2004_E2024_spectral_convergence.f32", spec)
    aspect = spec["height"] / spec["width"]

    scores = pd.read_csv(
        DATA / "13_tables" / "baseline_reproduction" / "component_epoch_integrated_scores.csv"
    )
    e2024 = scores[(scores.radius_m == 500) & (scores.epoch_id == "E2024")]

    features = json.loads(
        (DATA / "06_processed_vectors"
         / "taxila_integrated_field_inspection_priority_wgs84.geojson").read_text(encoding="utf-8")
    )["features"]
    props = pd.DataFrame([f["properties"] for f in features])
    mapped = props[props.local_priority_score_500m.notna()].copy()
    ranked = mapped.sort_values("bootstrap_rank_median").reset_index(drop=True)
    n = len(ranked)
    is_core = mapped.name.isin(CORE)
    sizes = 22 + 130 * (mapped.local_priority_score_500m - mapped.local_priority_score_500m.min())

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "pdf.fonttype": 42, "svg.fonttype": "none",
        "axes.labelcolor": INK, "text.color": INK,
    })
    fig = plt.figure(figsize=(7.2, 2.25))
    gs = GridSpec(1, 5, figure=fig, wspace=0.42, left=0.012, right=0.988, top=0.74, bottom=0.16)

    ax1 = fig.add_subplot(gs[0])
    lo, hi = np.nanpercentile(pressure, [2, 98])
    ax1.imshow(pressure, cmap="YlOrBr", vmin=lo, vmax=hi, interpolation="nearest")
    frame(ax1)
    stage(ax1, "01", "Landscape evidence")

    ax2 = fig.add_subplot(gs[1])
    ax2.imshow(
        convergence,
        cmap=ListedColormap(["#EEF2F4", "#FDD9A8", "#F08C4B", ACCENT]),
        norm=BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], 4),
        interpolation="nearest",
    )
    frame(ax2)
    stage(ax2, "02", "Adverse convergence")

    ax3 = fig.add_subplot(gs[2])
    raw = e2024["landscape_pressure_score"].dropna().values
    ax3.hist(raw, bins=9, color="#C9D3DA", edgecolor="white", linewidth=0.6)
    twin = ax3.twinx()
    ordered = np.sort(raw)
    twin.plot(ordered, np.linspace(0, 1, len(ordered)), color=ACCENT, lw=1.6)
    twin.set_yticks([])
    for spine in twin.spines.values():
        spine.set_visible(False)
    frame(ax3)
    stage(ax3, "03", "Oriented percentiles")

    ax4 = fig.add_subplot(gs[3])
    for i, row in ranked.iterrows():
        y = n - 1 - i
        core = row["name"] in CORE
        ax4.plot(
            [row.bootstrap_rank_ci_low_95, row.bootstrap_rank_ci_high_95], [y, y],
            color=ACCENT if core else "#B4BFC7", lw=1.9 if core else 1.1,
            solid_capstyle="round",
        )
        ax4.plot(row.bootstrap_rank_median, y, "o", ms=2.9 if core else 2.0,
                 color=ACCENT if core else MUTED)
    ax4.set_xlim(0.3, 18.7)
    ax4.set_ylim(-1, n)
    frame(ax4)
    stage(ax4, "04", "Rank uncertainty")

    ax5 = fig.add_subplot(gs[4])
    ax5.scatter(mapped.longitude, mapped.latitude, c=mapped.local_priority_score_500m,
                s=sizes * 0.55, cmap="YlOrBr", edgecolor="#4A5A64", linewidth=0.35, zorder=3)
    ax5.scatter(mapped[is_core].longitude, mapped[is_core].latitude, s=sizes[is_core] * 1.9,
                facecolors="none", edgecolor=ACCENT, linewidth=1.0, zorder=4)
    ax5.margins(0.20)
    frame(ax5)
    stage(ax5, "05", "Inspection set")

    for ax in (ax1, ax2, ax3, ax4, ax5):
        ax.set_box_aspect(aspect)
    fig.canvas.draw()
    for left, right in [(ax1, ax2), (ax2, ax3), (ax3, ax4), (ax4, ax5)]:
        a, b = left.get_position(), right.get_position()
        fig.patches.append(FancyArrowPatch(
            (a.x1 + 0.006, (a.y0 + a.y1) / 2), (b.x0 - 0.006, (b.y0 + b.y1) / 2),
            transform=fig.transFigure, arrowstyle="-|>", mutation_scale=7, lw=0.8, color=MUTED))

    fig.text(
        0.012, 0.045,
        "Circled: the three components that persist across spatial states and decision "
        "weightings.  One of the eighteen inscribed components cannot be scored — its "
        "coordinate is unresolved.",
        fontsize=6.1, color=MUTED,
    )

    for ext in ("pdf", "png", "svg"):
        fig.savefig(OUT / f"{STEM}.{ext}", dpi=400, bbox_inches="tight")

    renderer = fig.canvas.get_renderer()
    boxes = [t.get_window_extent(renderer) for t in fig.findobj(mpl.text.Text)
             if t.get_text().strip() and t.get_visible()]
    clashes = sum(1 for i, a in enumerate(boxes) for b in boxes[i + 1:] if a.overlaps(b))
    print(f"wrote {STEM}.[pdf|png|svg] to {OUT}  (text overlaps: {clashes})")


if __name__ == "__main__":
    main()
