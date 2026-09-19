# Revision report — Taxila CHIP manuscript, 2026-09-19

Target venue: *Journal of Cultural Heritage* (Elsevier).
Branch: `revision/jch-2026-09-18`. Baseline: the 2026-09-06 "mathematical" state.
Submission snapshot: `submission-snapshots/JCH_2026-09-19_decision_analysis/`
(85 files, SHA-256 manifest verified).

---

## 1. What changed, and why

The 2026-09-06 manuscript was computationally sound — every headline number
re-derived from the frozen inputs, and all data checksums verified — but it had
four problems that would have cost it a single-round acceptance: selectively
reported sensitivity analyses, a traceability package that contradicted the
manuscript's own headline model result, no uncertainty on any rank statistic, and
a scope mismatch with a conservation readership. This revision fixes all four and
adds a substantive new analysis and an external validation.

### 1.1 New science

**Exact affine reconstruction of the joint design.** The priority score is affine
in the sampled landscape weight, so the latent landscape and terrain terms are
identified by the recorded draws themselves. Solving that system per spatial
state recovers them to machine precision (maximum residual
6.6 × 10⁻¹⁵) and converts the 5,000-draw Monte Carlo into a balanced
280,998-scenario factorial over 466 of the 500 recorded states — at no additional
computational cost and with no new data. The reconstruction reproduces the
published Monte Carlo (Giri top-three acceptability 0.7333 against 0.7324), which
is an independent replication of the original simulation as well as a new
analysis.

Three results follow that the original frequency summaries could not express:

| Quantity | Result |
|---|---|
| Confidence factors | No component exceeds 0.42; the best-supported component still loses the lead in most spatial states |
| Rank-variance decomposition | Design-wide 45.8% decision (35.2% weight, 8.5% terrain formulation), 31.8% spatial support, 22.4% interaction — but the split inverts per component, so the analysis prescribes *per component* whether a weighting decision or a data acquisition would settle its rank |
| Inspection-budget curve | Three components cover a scenario's own three highest priorities in 17.9% of cases; four raise this to 51.8% (+33.9 points, larger than every subsequent addition combined up to k = 8) |

Implemented in `scripts/build_smaa_decision_analysis.py`; outputs and an
execution receipt in `experiments/decision_analysis/2026-09-18/`.

**External confrontation, reported as found.** UNESCO State of Conservation
records could not be retrieved (the World Heritage Centre returns HTTP 403 to all
non-browser clients; evading that check was not acceptable, so it is documented
as a manual step for the authors). The two published sources reporting findings
at named Taxila components were used instead. The result does not favour the
framework and has been made the paper's framing rather than a footnote:

| Component | CHIP rank (fixed 500 m, of 17) | Independent evidence |
|---|---|---|
| Mohra Moradu | 4 | damage documented (Khan et al. 2022) |
| Dharmarajika | 5 | two damage types (Khan et al. 2022) |
| Sirkap | 12 | damage + seismic amplification (Khan et al. 2022) |
| Bhir Mound | 17 (last) | built-up clustering hotspot (Butt et al. 2025) |
| Saraikala | **not scorable** | core zone 0.0168 → 0.0032 km², 2004–2024 (Butt et al. 2025) |

None falls in the CHIP core tier. The manuscript now argues — and supports with
its own ablation evidence — that CHIP measures moisture- and terrain-driven
landscape pressure, a *different construct* from documented fabric damage or
built-up encroachment, and must be combined with damage records rather than
substituted for them. The unscorable component is now a headline limitation.

### 1.2 Integrity repairs

- **All eight aggregation baselines are now reported**, not four. The two
  previously omitted unfavourable ones are stated plainly in the Results: a
  robust-z logistic aggregation is unrelated to the published ranking
  (ρ = 0.038, 95% CI −0.451 to 0.509) and an oriented first principal component
  reverses it (ρ = −0.771, −0.925 to −0.403, no top-five overlap). The
  supplementary table previously captioned "complete" now is.
- **The traceability package is generated, not maintained.**
  `scripts/build_traceability_package.py` derives the display-item and
  equation–code maps from the compiled source, so they cannot desynchronise
  again. The previous maps described a 14-figure, 18-equation article whose
  figure paths did not exist in the repository.
- **The stale selected-model claim is corrected** in `CLAIM_EVIDENCE_AUDIT.csv`,
  `RESULT_DISPOSITION_MATRIX.csv` and
  `source_traceability/frozen_claim_evidence_matrix.csv`: MLP / macro-F1 0.831 →
  random forest / 0.821433 (95% CI 0.691099–0.835178), with the stale FDR values
  corrected to q = 0.026987. The superseded evidence table is renamed with a
  `SUPERSEDED_` prefix, documented in `13_tables/README_SUPERSEDED.md`, and the
  protocol change is disclosed in the supplement rather than left for a reviewer
  to discover.

### 1.3 Statistical reporting

- Every Spearman coefficient now carries a 95% Bonett–Wright interval on n = 17.
  Four of the fourteen comparisons have intervals spanning zero, including the
  MNDWI ablation that appears in the abstract; that sentence is now stated as a
  loss of concordance rather than a negative association.
- Scenario tier frequencies carry exact Clopper–Pearson intervals. These show the
  core tier is separated from its 0.5 threshold while the conditional tier is
  not (Khader Mohra 15/27, 0.556, CI 0.353–0.745), so the two tiers are no longer
  presented with equal authority.
- The headline convergence statistic has an analytic reference. Because the three
  criteria are fixed quantiles of the same cell set, each marginal is exactly
  0.200 by construction, so the independence expectation is known: observed
  co-occurrence is 1.63× (≥2 criteria) and 1.78× (all three) the independence
  rate, while ≥1 falls below it — positive dependence, and a stronger result than
  the bare 16.93%.
- Four of seven model families exceeding the selected model on the outer stripe
  is now stated explicitly.

### 1.4 Journal fit and structure

- Display items rebalanced to exactly 10. The integrated inspection-priority map
  (previously built but unused) and the new decision-diagnostics figure are now
  in the main article; the benchmark models table moved to the supplement and the
  diagnostic-experiments table to `tables/unused/`.
- Figure files renamed to compiled order via tracked renames. Four figures and
  five tables that compiled nowhere are archived under `unused/`.
- Introduction expanded with heritage-conservation framing, citing 26 previously
  uncited heritage and remote-sensing references.
- Methods citations repaired: ERA5, SRTM, Fmask, D8/multiple-direction routing
  and blocked cross-validation now cite the canonical sources rather than vendor
  pages. The elevation product is named and versioned.
- Tool attribution removed from the Figure 2 caption.
- Declarations completed: CRediT, funding, competing interest, permissions and
  ethics, acknowledgements; data availability rewritten for a permanent DOI.
- Title page cleaned of the author-confirmation block and the live private
  repository link.

---

## 2. Verification performed

| Check | Result |
|---|---|
| Manuscript values against source tables | 49 / 49 match |
| Frozen evidence SHA-256 manifest | 158 / 158 verify |
| Submission snapshot manifest | 85 / 85 verify |
| Undefined references, missing inputs, missing graphics | none |
| Duplicate labels, unbalanced environments or braces | none |
| Citations resolving to `references.bib` | 70 / 70 |
| Display items | 10 (cap 10) |
| Body word count | 4,993 (cap 5,000) |
| Research aim | 88 words (cap 200) |
| Highlights | 5, longest 72 characters (cap 85) |

Run `python scripts/validate_manuscript.py --manuscript manuscript` to reproduce
the structural checks.

**Note on a corrected counting error.** An earlier word count in this revision
used a comment-stripping regex that treated escaped percent signs (`95\%`) as
comment starts, truncating every line containing a percentage and undercounting
the body by roughly 650 words. The validator now matches only unescaped `%`.
Word counts reported above are from the corrected counter.

---

## 3. Not done, and why

- **No compiled PDFs.** No TeX distribution is installed on this machine, and the
  sandboxed engine that was installed cannot resolve its cache directories. The
  sources pass every structural check a compile would catch. Produce the PDFs
  with:

      cd manuscript && latexmk -pdf main.tex
      cd manuscript && latexmk -pdf title_page.tex
      cd manuscript/supplementary && latexmk -pdf supplementary_information.tex

- **UNESCO State of Conservation coding.** Blocked by the access restriction
  described above. This remains the single highest-value addition available: the
  records are public in a browser, and coding them into a component-level threat
  indicator would extend the external comparison from five components to the full
  documented record.

---

## 4. Blocked on author input

These are marked `[[...]]` in the sources and are listed in the commented
checklist at the foot of `manuscript/title_page.tex`. The manuscript cannot be
submitted until each is resolved.

1. Deposit the frozen evidence package under a permanent DOI (Zenodo or
   equivalent) and insert it in `sections/08_declarations.tex` and
   `title_page.tex`. A verified SHA-256 manifest already exists, so the deposit is
   mechanical.
2. CRediT roles for the second and third authors.
3. Funding statement — "no specific grant" is acceptable but must be stated.
4. Whether the Department of Archaeology and Museums and/or the Punjab
   Archaeology Department should be acknowledged for inventory access.
5. Individual and institutional acknowledgements.
6. Code and data licences.
7. Full postal details for the second and third affiliations; expansion of FCAI.
8. Confirmation of author order and of the competing-interest statement.

---

## 5. Suggested next step beyond this revision

Resolving Saraikala's coordinate — ideally as a polygon — would remove the
limitation the paper now leads with, and would let the framework score the one
component with the strongest independent evidence of loss. Combined with UNESCO
State of Conservation coding, that would convert the external comparison from a
descriptive check on five components into a testable validation, which is the
change most likely to move this from a methods contribution to a paper the
journal's readership cites.
