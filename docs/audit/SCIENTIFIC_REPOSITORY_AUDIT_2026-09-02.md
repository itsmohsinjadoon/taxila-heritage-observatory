# ProjectTaxila scientific and repository audit

**Audit date:** 2 September 2026  
**Scope:** frozen evidence package, executable notebook, integrated experiment bundle, figures, journal-neutral LaTeX source, and the submitted anonymised main and supplementary PDFs supplied separately by the author.  
**Decision:** suitable as a private revision repository; **not yet suitable for a public archival release or an unchanged Journal of Cultural Heritage resubmission**.

## Executive assessment

The project contains unusually strong traceability material for a pre-submission study: frozen spatial and tabular evidence, checksums, data dictionaries, acquisition records, a clean executable notebook, sensitivity analyses, manuscript source, figure/table assets, and explicit interpretation boundaries. No critical secret or GitHub-size violation was found.

The principal scientific risk is not missing analysis but version consistency. The frozen repository, the later executed V8 notebook associated with the supplied submission PDFs, and reruns made under different environments do not support one internally consistent proxy-model record. The supplied PDFs state that all 26 headline evidence locks passed; however, their supplementary lock table replaces the frozen proxy targets with the newly observed values. The executed V8 notebook retains the frozen targets, reports 24 of 27 checks passed, and explicitly warns against reporting a clean reproduction. The V8 bootstrap implementation also omitted the declared fixed six-class target when a resample lacked a class; this code defect was corrected during the audit, and the corrected interval now reproduces the rounded interval in the PDFs. The evidence-lock statement must still be corrected or supported by a fully reproduced, immutable environment.

## Evidence reviewed

| Evidence | Audit observation |
| --- | --- |
| Frozen repository state | 289 files before this audit; approximately 112.6 MiB; all individual files below GitHub's 100 MiB hard limit. |
| Clean notebook | 25 cells, including 13 code cells; committed without outputs. |
| Frozen evidence manifest | Existing SHA-256 verification records are present under `data/Taxila_CHIP_Frozen_Evidence_Data/`. |
| Submitted main PDF | 15 pages; SHA-256 `8C627FC4FF4883D9905174373BA35CFD730FE4182C5F664BDCA9CE384B9AE7E1`. |
| Submitted supplementary PDF | 18 pages; SHA-256 `86B10F3A93071CBE6A4737D8D8BDB1DF86F718FF31F18F3A730CF6EAB8B02EF6`. |
| Repository LaTeX source | A different journal-neutral manuscript generation: previously compiled as 50 main pages plus 21 supplementary pages. It is not the editable source of the supplied 15/18-page submission PDFs. |
| Latest Figure 1 | Rebuilt from the documented Sentinel-2 display raster and frozen vector sources; source bundle and caption are now versioned. |

The supplied submission PDFs are retained by the author outside the repository. Their checksums are recorded here to make the reviewed snapshot unambiguous without adding about 39 MiB of pre-submission binary PDFs to Git history.

## Reproduction results

### Validation profile

The clean repository notebook completed end to end after two portability fixes: repository-root discovery now searches all ancestors, and atomic figure export now handles Windows filesystems safely. The reduced validation profile passed all 19 applicable checks. This profile is an engineering test; it is not a substitute for the publication-scale stochastic run.

### Publication profile and evidence lock

| Result source | Macro-F1 | Agreement | ECE | Headline locks |
| --- | ---: | ---: | ---: | ---: |
| Frozen Linux evidence lock | 0.830795 | 0.833095 | 0.014280 | authoritative stored targets |
| Executed V8 notebook associated with the supplied PDF point metrics | 0.830072 | 0.828080 | 0.015117 | 24/27 passed |
| Final audited Windows run with the exact frozen package versions | 0.830072 | 0.828080 | 0.015117 | 24/27 passed |
| Fresh Windows run with the former broad dependency ranges | 0.839502 | 0.844078 | 0.011888 | 24/27 passed |

The original V8 notebook's selected MLP block-bootstrap macro-F1 interval was 0.800080–0.851843 even though its method text declared a fixed six-class target. The implementation calculated macro-F1 over only the classes present in each resample, changing the denominator when a block resample omitted a class. The audited notebook now passes `labels=0..5` and `zero_division=0`; an exact-version publication rerun produces 0.701423–0.850954, reproducing the PDFs' rounded 0.701–0.851 interval. This correction does not change the three failed point-metric locks. The PDFs' supplementary lock table still uses the newly observed proxy values as both “observed” and “expected,” whereas the notebook's immutable frozen targets are 0.830795, 0.833095, and 0.014280.

The exact package versions recorded by the frozen Linux run are now pinned in `requirements-reproduction.txt`. The exact-version Windows rerun reproduces the V8 point metrics precisely, but not the frozen Linux proxy targets; this isolates the remaining discrepancy to platform, lower-level numerical behavior, or an unpreserved run-generation difference rather than the Python package versions alone. Operating system, linked numerical libraries, thread scheduling, and estimator implementation details can affect the final MLP refit even with fixed seeds. The repository must report observed platform behavior rather than treating a seed as a cross-platform bitwise guarantee.

## Priority findings

### P0 — resolve before submission

1. **Correct the clean-reproduction claim.** Replace the “all checks passed” statement in the submitted main and supplementary PDFs unless a preserved environment produces the original locked values and a new execution log verifies every check. Do not redefine expected locks after observing a rerun.
2. **Select one authoritative result generation.** The frozen Linux values, V8/Windows values, and broad-environment Windows values cannot be mixed across abstract, tables, supplement, and validation text. Regenerate all dependent manuscript values from the selected immutable run. Retain the corrected fixed-six-class bootstrap rule; its audited MLP interval is 0.701–0.851 after rounding.
3. **Recover or recreate the exact editable submission source.** The repository's 50/21-page LaTeX package is not the source of the supplied 15/18-page PDFs. The publication source, bibliography state, and figure/table placements must be versioned before final revision.
4. **Close the integrated-bundle reproducibility gap.** `experiments/integrated/analysis/run_integrated_experiments.py` references missing derived/raw paths, including an unavailable E2019 six-band reflectance array. Its archived result tables and figures are scientifically relevant and should remain, but the bundle cannot currently be represented as an independent source-to-result rerun.

### P1 — resolve before public release

1. Confirm author names/order, affiliations, corresponding author, CRediT roles, funding, competing interests, acknowledgements, site access, and permissions.
2. Choose explicit licences for original code, text, and figures; retain provider-specific terms for third-party data.
3. Create a DOI or release identifier only when pre-submission disclosure is approved by all authors.
4. Reconcile intentional experiment snapshots and exact duplicate payloads. The audit found about 14.3 MiB of duplicate content across 44 hash groups, principally SRTM and derived-table copies. Duplication is not a scientific error, but each preserved snapshot should have a documented purpose.
5. Confirm the live Journal of Cultural Heritage submission checklist immediately before upload, including anonymisation, highlights, graphical abstract, figure files, supplementary file naming, and declarations.

## Figure 1 correction

The earlier “Final Cyan” graphic displayed Esri World Imagery while its caption described Sentinel-2 and did not show the required basemap attribution. The audited replacement removes that mismatch:

- panel (c) now uses a 10 m true-colour display derived from Copernicus Sentinel-2 L2A tiles T43SCT and T43SBT acquired 26 October 2024;
- panels (a) and (b) use Natural Earth and geoBoundaries administrative outlines, with a frozen OpenStreetMap snapshot for orientation features;
- the 500 m circles are explicitly described as analytical neighbourhoods, not UNESCO or legal buffer boundaries;
- visible attribution, a reproducible QGIS script, source metadata, checksums, and validation notes are included under `manuscript/figures/source/figure_01/`.

The repository-relative QGIS 3.44.13 build completed successfully on 2 September 2026 and the regenerated preview passed visual inspection. The replacement PDF SHA-256 is `C78F4780494A109727B7497D300183079A4E938BEF34D662231E7C2CEB4CA36E`. The derived Sentinel-2 display raster SHA-256 is `B5BB42028C5140CABA22D033DD23CA93EFE18EFDD1357640CCECC8A0CF3162AD`.

## Security, privacy, and repository hygiene

- No GitHub token, AWS access key, private-key block, `.env` secret, notebook checkpoint, or committed LaTeX temporary file was found by the repository scans.
- Local virtual environments, notebook outputs, QGIS-generated outputs, caches, and manuscript build products are ignored.
- The clean notebook contains no committed execution outputs.
- No individual repository file exceeds 10 MiB in the audited working tree; Git LFS is therefore not technically required for the present files. Raw satellite archives and other large upstream datasets should remain provider-hosted and be represented by manifests, acquisition scripts, identifiers, and checksums.
- Submitted pre-publication PDFs are intentionally represented by checksums rather than duplicated in normal Git history.

## Interpretation boundary

The evidence supports relative landscape-pressure screening, terrain/hydrological susceptibility, climate context, and sensitivity-aware prioritisation of field inspection. It does not establish confirmed monument damage, deterioration probability, causal climate impact, official UNESCO/legal buffers, or future loss. The WorldCover benchmark is proxy agreement, not independent heritage-condition accuracy.

## Release gate

The repository may be described as **audited and revision-ready** after the local validation and repository checks pass. It must not be described as a fully reproduced archival package until the three proxy-model locks, the exact submission source, and the standalone integrated-bundle inputs are resolved. Public release additionally requires author approval, licences, third-party permissions review, and stable citation metadata.
