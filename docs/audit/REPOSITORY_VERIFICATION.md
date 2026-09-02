# Repository verification — 2026-08-29 (superseded in part)

> This historical checkpoint predates the 2 September 2026 cross-version audit. Its engineering checks remain useful, but its clean-run wording must not be used as evidence that all current publication-profile locks pass. See [`SCIENTIFIC_REPOSITORY_AUDIT_2026-09-02.md`](SCIENTIFIC_REPOSITORY_AUDIT_2026-09-02.md).

This report records checks performed after consolidating the ProjectTaxila research assets into the GitHub repository structure.

## Passed checks

- Repository validator: 288 files parsed or structurally checked before Git initialisation.
- Frozen evidence integrity: every entry in `data/Taxila_CHIP_Frozen_Evidence_Data/SHA256SUMS.txt` passed SHA-256 verification.
- Clean notebook: 25 cells, 13 code cells, no committed execution outputs.
- Notebook Run All: all 13 code cells executed successfully with the validation profile against the committed frozen evidence package. The executed notebook and generated outputs were kept in temporary storage and were not committed.
- Python source: all committed `.py` files passed abstract-syntax-tree parsing.
- Structured data: committed JSON and CSV files passed parsing checks.
- GitHub size gate: no individual file exceeds 95 MiB.
- Secret-pattern scan: no GitHub token, AWS access key, or private-key signature detected by the repository validator.
- LaTeX: the main manuscript and Supplementary Information compiled successfully with `latexmk`, `pdflatex`, and BibTeX.
- Final LaTeX logs: no undefined citations, undefined references, missing-file errors, or fatal compilation errors.
- Current build: 50 A4 pages for the main manuscript and 21 A4 pages for Supplementary Information.

## Later audit qualification

The reduced validation profile passes, but later publication-profile reruns expose environment-sensitive proxy-model drift. The executed V8 notebook corresponding to the supplied submission values passes 24 of 27 headline checks, not a clean set of locks. The separate 15/18-page supplied PDFs are also not built from the journal-neutral 50/21-page source recorded here.

## Preserved audit history

`MANUSCRIPT_QA_REPORT.md` and the copy under `manuscript/QA_REPORT.md` are preserved checkpoint records. Their 48-page figure reflects the earlier audit note, while the source and compiled PDF recovered from the working checkpoint both produce 50 pages. The current result above is authoritative for this repository state.

## Scientific boundary

The successful technical checks do not create missing independent condition labels, official property polygons, station validation, field hydrology validation, or a verified Saraikala geometry. The interpretation limits in `data/Taxila_CHIP_Frozen_Evidence_Data/q1_revision/missing_evidence_and_boundaries.md` remain in force.
