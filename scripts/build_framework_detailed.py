#!/usr/bin/env python3
"""Figure 2: the CHIP evidence chain, rendered from the study's own rasters.

Five bands, top to bottom:

    A  observation inputs   Sentinel-2 true colour and the three Landsat
                            spectral indices that enter the score
    B  climate input        daily mean temperature as a year x day-of-year
                            raster, and the annual precipitation trend
    C  mathematics          the transforms that turn those observations into a
                            component priority
    D  derived rasters      relative landscape pressure at five epochs and the
                            adverse-convergence surface
    E  decision output      rank uncertainty, inspection priorities and the
                            budget-coverage curve

Band identity of the `*_oli_like_indices.tif` stack is not documented in the
frozen package, so it is verified at run time against the tabulated component
medians in component_epoch_multiscale_landsat.csv: the script asserts that each
band's raster median falls closest to the component-median range of the index
it is labelled with, and raises if it does not.

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
from PIL import Image
from scipy.stats import theilslopes

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "Taxila_CHIP_Frozen_Evidence_Data"
RAST = DATA / "05_processed_rasters"
OUT = ROOT / "manuscript" / "figures" / "main"
STEM = "figure_02_chip_framework"

INK, ACCENT, MUTED, GRID = "#203648", "#A63603", "#8C99A2", "#C7D0D6"
CORE = {"Giri complex of monuments", "Giri Mosque and tombs", "Jaulian stupa and monastery"}
SHORT = {"Giri complex of monuments": "Giri complex",
         "Giri Mosque and tombs": "Giri Mosque/tombs",
         "Jaulian stupa and monastery": "Jaulian"}
EPOCHS = ["E2004", "E2009", "E2014", "E2019", "E2024"]


def read_f32(name, spec):
    arr = np.fromfile(RAST / name, dtype="<f4").reshape(spec["height"], spec["width"]).astype(float)
    arr[arr == spec["nodata"]] = np.nan
    return arr


def spectral_indices(reference):
    """Return NDVI, NDBI and MNDWI, verified against tabulated component medians."""
    import tifffile
    stack = tifffile.imread(RAST / "E2024_oli_like_indices.tif")
    stack = np.where(stack == -9999, np.nan, stack.astype(np.float32))
    ranges = {k: (reference[f"{k}_median"].min(), reference[f"{k}_median"].max())
              for k in ("ndvi", "ndbi", "mndwi")}
    for band, name in enumerate(("ndvi", "ndbi", "mndwi")):
        median = float(np.nanmedian(stack[..., band]))
        nearest = min(ranges, key=lambda k: abs(median - np.mean(ranges[k])))
        if nearest != name:
            raise AssertionError(
                f"band {band} median {median:.3f} matches '{nearest}', not '{name}' — "
                "band order in the indices stack has changed"
            )
    return stack[..., 0], stack[..., 1], stack[..., 2]


def frame(ax, colour=GRID):
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor(colour)
        spine.set_linewidth(0.7)


def despine(ax, keep=("left", "bottom")):
    for name, spine in ax.spines.items():
        spine.set_visible(name in keep)


def main():
    spec = json.loads((RAST / "derived_raster_spec.json").read_text())
    pressure = {e: read_f32(f"{e}_relative_landscape_pressure.f32", spec) for e in EPOCHS}
    convergence = read_f32("E2004_E2024_spectral_convergence.f32", spec)

    landsat = pd.read_csv(DATA / "13_tables" / "baseline_reproduction"
                          / "component_epoch_multiscale_landsat.csv")
    reference = landsat[(landsat.radius_m == 500) & (landsat.epoch_id == "E2024")]
    ndvi, ndbi, mndwi = spectral_indices(reference)

    scene = Image.open(ROOT / "manuscript" / "figures" / "source" / "figure_01" / "data"
                       / "Taxila_Sentinel2_20241026_RGB_8bit.tif")
    scene.thumbnail((700, 700))
    scene = np.asarray(scene)

    weather = pd.read_csv(DATA / "04_cleaned_data" / "open_meteo_era5_seamless_site_daily.csv",
                          parse_dates=["date"])
    weather["year"] = weather.date.dt.year
    weather["doy"] = weather.date.dt.dayofyear
    heat = weather.pivot_table(index="year", columns="doy",
                               values="temperature_2m_mean", aggfunc="mean")
    annual = weather.groupby("year").agg(precip=("precipitation_sum", "sum"))
    slope, intercept = theilslopes(annual.precip.values, annual.index.values)[:2]

    features = json.loads((DATA / "06_processed_vectors"
                           / "taxila_integrated_field_inspection_priority_wgs84.geojson"
                           ).read_text(encoding="utf-8"))["features"]
    props = pd.DataFrame([f["properties"] for f in features])
    mapped = props[props.local_priority_score_500m.notna()].copy()
    ranked = mapped.sort_values("bootstrap_rank_median").reset_index(drop=True)
    n = len(ranked)
    is_core = mapped.name.isin(CORE)
    sizes = 22 + 130 * (mapped.local_priority_score_500m - mapped.local_priority_score_500m.min())
    budget = pd.read_csv(ROOT / "experiments" / "decision_analysis" / "2026-09-18"
                         / "inspection_budget_curve.csv")

    plt.rcParams.update({"font.family": "DejaVu Sans", "pdf.fonttype": 42,
                         "svg.fonttype": "none", "text.color": INK,
                         "axes.labelcolor": INK, "axes.edgecolor": "#5A6B76"})
    fig = plt.figure(figsize=(7.2, 9.6))
    gs = GridSpec(5, 12, figure=fig, height_ratios=[1.22, 0.98, 0.74, 0.88, 1.18],
                  hspace=0.80, wspace=0.75, left=0.055, right=0.965, top=0.935, bottom=0.045)

    # ---- A  observation inputs -------------------------------------------------
    ax_scene = fig.add_subplot(gs[0, 0:3])
    ax_scene.imshow(scene)
    frame(ax_scene)
    ax_scene.set_title("Sentinel-2 true colour\n2024-10-26", fontsize=6.5, pad=3)
    row_a = [ax_scene]
    for k, (arr, name, cmap, span) in enumerate([
            (ndvi, "NDVI", "RdYlGn", (-0.2, 0.8)),
            (ndbi, "NDBI", "PuOr_r", (-0.4, 0.4)),
            (mndwi, "MNDWI", "BrBG", (-0.7, 0.3))]):
        ax = fig.add_subplot(gs[0, 3 + 3 * k:6 + 3 * k])
        im = ax.imshow(arr, cmap=cmap, vmin=span[0], vmax=span[1], interpolation="nearest")
        frame(ax)
        ax.set_title(f"{name}\nE2024 masked median", fontsize=6.5, pad=3)
        bar = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.025, aspect=11)
        bar.ax.tick_params(labelsize=5)
        bar.outline.set_linewidth(0.4)
        row_a.append(ax)

    # ---- B  climate input ------------------------------------------------------
    ax_heat = fig.add_subplot(gs[1, 0:7])
    im = ax_heat.imshow(heat.values, aspect="auto", cmap="magma", interpolation="nearest",
                        extent=[1, 366, heat.index.max() + 0.5, heat.index.min() - 0.5])
    ax_heat.set_xlabel("day of year", fontsize=6, labelpad=1.5)
    ax_heat.set_ylabel("year", fontsize=6, labelpad=4)
    ax_heat.set_xticks([1, 91, 182, 274, 366])
    ax_heat.set_yticks([1995, 2005, 2015, 2025])
    ax_heat.tick_params(labelsize=5.6)
    ax_heat.set_title("Daily mean temperature, 1991–2025 (regional four-cell mean)",
                      fontsize=6.6, pad=3)
    bar = fig.colorbar(im, ax=ax_heat, fraction=0.028, pad=0.015, aspect=12)
    bar.ax.tick_params(labelsize=5)
    bar.set_label("°C", fontsize=5.5)
    bar.outline.set_linewidth(0.4)

    ax_precip = fig.add_subplot(gs[1, 8:12])
    ax_precip.plot(annual.index, annual.precip, color=MUTED, lw=0.9, marker="o", ms=2.2)
    years = np.asarray(annual.index)
    ax_precip.plot(years, intercept + slope * years, color=ACCENT, lw=1.5)
    ax_precip.set_title(f"Annual precipitation\nTheil–Sen {slope:+.2f} mm yr$^{{-1}}$",
                        fontsize=6.5, pad=3)
    ax_precip.set_ylabel("mm", fontsize=6, labelpad=1)
    ax_precip.set_xticks([1995, 2010, 2025])
    ax_precip.tick_params(labelsize=5.6)
    despine(ax_precip)

    # ---- C  mathematics --------------------------------------------------------
    ax_math = fig.add_subplot(gs[2, 0:12])
    ax_math.axis("off")
    ax_math.add_patch(mpl.patches.FancyBboxPatch(
        (0, 0), 1, 1, boxstyle="round,pad=0.006,rounding_size=0.015",
        transform=ax_math.transAxes, fc="#F4F7F9", ec=GRID, lw=0.7, zorder=0))
    equations = [
        (r"$z_f(i)=\hat{F}_f\left(x_f(i)\right)\in[0,1]$",
         "oriented percentile of factor $f$"),
        (r"$L=\frac{1}{4}z_N+\frac{1}{4}z_B+\frac{1}{2}z_W$,"
         r"$\ \ \ T=\frac{1}{3}\left(z_S+z_H+z_D\right)$",
         "landscape and terrain domains"),
        (r"$P_i(w)=w\,L_i+(1-w)\,T_i$,$\ \ \ $reference $w=0.5$",
         "hierarchical priority score"),
        (r"$C(c)=\mathbf{1}[\Delta\mathrm{NDVI}\leq q_{20}]"
         r"+\mathbf{1}[\Delta\mathrm{MNDWI}\leq q_{20}]"
         r"+\mathbf{1}[\Delta\mathrm{NDBI}\geq q_{80}]$",
         "adverse convergence count per cell"),
        (r"$P_i(s,m,w)=w\,L_i(s)+(1-w)\,T_i(s,m)$",
         "affine in $w$ — latent terms recoverable exactly"),
    ]
    for k, (expression, gloss) in enumerate(equations):
        y = 0.885 - k * 0.192
        ax_math.text(0.022, y, expression, fontsize=7.1, color=INK, va="center",
                     transform=ax_math.transAxes)
        ax_math.text(0.982, y, gloss, fontsize=5.8, color=MUTED, va="center", ha="right",
                     transform=ax_math.transAxes)

    # ---- D  derived rasters ----------------------------------------------------
    low, high = np.nanpercentile(pressure["E2024"], [2, 98])
    row_d = []
    for k, epoch in enumerate(EPOCHS):
        ax = fig.add_subplot(gs[3, 2 * k:2 * k + 2])
        ax.imshow(pressure[epoch], cmap="YlOrBr", vmin=low, vmax=high, interpolation="nearest")
        frame(ax)
        ax.set_title(epoch[1:], fontsize=6.3, pad=2)
        if k == 0:
            ax.set_ylabel("relative\nlandscape pressure", fontsize=5.7, labelpad=2)
        row_d.append(ax)
    ax_conv = fig.add_subplot(gs[3, 10:12])
    ax_conv.imshow(convergence, cmap=ListedColormap(["#EEF2F4", "#FDD9A8", "#F08C4B", ACCENT]),
                   norm=BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], 4), interpolation="nearest")
    frame(ax_conv, ACCENT)
    ax_conv.set_title("convergence\n$C\\geq2$: 16.93%", fontsize=6.3, pad=2, color=ACCENT)
    row_d.append(ax_conv)

    # ---- E  decision output ----------------------------------------------------
    ax_rank = fig.add_subplot(gs[4, 0:5])
    for i, row in ranked.iterrows():
        y = n - 1 - i
        core = row["name"] in CORE
        ax_rank.plot([row.bootstrap_rank_ci_low_95, row.bootstrap_rank_ci_high_95], [y, y],
                     color=ACCENT if core else "#B4BFC7", lw=1.9 if core else 1.0,
                     solid_capstyle="round")
        ax_rank.plot(row.bootstrap_rank_median, y, "o", ms=2.9 if core else 1.9,
                     color=ACCENT if core else MUTED)
        if core:
            # the three core rows are adjacent, so their labels are staggered
            # vertically; at this row pitch a common offset makes them touch
            nudge = {0: 4.2, 1: 0.0, 2: -4.2}[len([c for c in ranked["name"][:i] if c in CORE])]
            ax_rank.annotate(SHORT[row["name"]],
                             (row.bootstrap_rank_ci_high_95, y), textcoords="offset points",
                             xytext=(4, nudge), va="center", fontsize=5.6, color=ACCENT)
    ax_rank.set_xlim(0.3, 18.7)
    ax_rank.set_ylim(-1, n)
    ax_rank.set_yticks([])
    ax_rank.tick_params(labelsize=5.6)
    ax_rank.set_xlabel("component rank (1 = highest)", fontsize=6, labelpad=1)
    ax_rank.set_title("Rank uncertainty across spatial states", fontsize=6.6, pad=3)
    despine(ax_rank, keep=("bottom",))

    ax_map = fig.add_subplot(gs[4, 5:8])
    ax_map.scatter(mapped.longitude, mapped.latitude, c=mapped.local_priority_score_500m,
                   s=sizes * 0.5, cmap="YlOrBr", edgecolor="#4A5A64", linewidth=0.35, zorder=3)
    ax_map.scatter(mapped[is_core].longitude, mapped[is_core].latitude, s=sizes[is_core] * 1.8,
                   facecolors="none", edgecolor=ACCENT, linewidth=1.0, zorder=4)
    frame(ax_map)
    ax_map.margins(0.18)
    ax_map.set_title("Inspection priorities\n(core tier circled)", fontsize=6.6, pad=3)

    ax_budget = fig.add_subplot(gs[4, 8:12])
    ax_budget.plot(budget.inspection_budget_k, 100 * budget.probability_full_coverage,
                   color=ACCENT, lw=1.5, marker="o", ms=2.6)
    for x, y, label, dx, dy, colour in [(3, 17.9, "3 sites\n17.9%", 7, -17, INK),
                                        (4, 51.8, "4 sites\n51.8%", 2, 7, ACCENT)]:
        ax_budget.annotate(label, (x, y), textcoords="offset points", xytext=(dx, dy),
                           fontsize=5.6, color=colour)
    ax_budget.set_xlim(0.5, 10.5)
    ax_budget.set_ylim(-6, 108)
    ax_budget.set_xlabel("components inspected", fontsize=6, labelpad=1)
    ax_budget.set_ylabel("full coverage (%)", fontsize=6, labelpad=1)
    ax_budget.tick_params(labelsize=5.6)
    ax_budget.set_title("Inspection-budget coverage", fontsize=6.6, pad=3)
    despine(ax_budget)

    # ---- band headers, placed above each row once the layout is final ----------
    fig.canvas.draw()
    bands = [("A   OBSERVATION INPUTS", row_a),
             ("B   CLIMATE INPUT", [ax_heat, ax_precip]),
             ("C   MATHEMATICS", [ax_math]),
             ("D   DERIVED RASTERS", row_d),
             ("E   DECISION OUTPUT", [ax_rank, ax_map, ax_budget])]
    for label, axes in bands:
        top = max(a.get_position().y1 for a in axes)
        offset = 0.030 if label.startswith(("A", "B", "E")) else (0.024 if label.startswith("D") else 0.012)
        fig.text(0.055, top + offset, label, fontsize=7.5, fontweight="bold",
                 color=INK, va="baseline")

    for ext in ("pdf", "png", "svg"):
        fig.savefig(OUT / f"{STEM}.{ext}", dpi=330, bbox_inches="tight")

    renderer = fig.canvas.get_renderer()
    boxes = [(t, t.get_window_extent(renderer)) for t in fig.findobj(mpl.text.Text)
             if t.get_text().strip() and t.get_visible()]
    ticks = {ax: set(ax.get_xticklabels(which="both") + ax.get_yticklabels(which="both"))
             for ax in fig.axes}
    clashes = [(a.get_text()[:28], b.get_text()[:28])
               for i, (a, ba) in enumerate(boxes) for b, bb in boxes[i + 1:]
               if ba.overlaps(bb) and not (a in ticks.get(a.axes, set())
                                           and b in ticks.get(b.axes, set()))]
    print(f"wrote {STEM}.[pdf|png|svg]  (text overlaps: {len(clashes)})")
    for pair in clashes[:10]:
        print("   overlap:", pair)


if __name__ == "__main__":
    main()
