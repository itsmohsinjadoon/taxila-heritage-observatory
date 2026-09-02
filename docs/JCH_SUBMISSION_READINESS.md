# Journal of Cultural Heritage submission readiness

## Already available

- Modular LaTeX manuscript and separate Supplementary Information.
- Verified bibliography with 91 cited records.
- Fourteen main figures, four main tables, four supplementary figures, and seven supplementary tables.
- Claim/evidence, equation/code, display/source, reference-verification, and result-disposition records.
- Clean executable notebook and frozen evidence package.
- Scale, threshold, weight, ablation, spatial-block, harmonisation, and proxy-model sensitivity analyses.
- Reproducibility metadata, fixed seed, software environment, checksums, and validation reports.

## Scientific blockers identified on 2 September 2026

- The supplied 15-page main and 18-page supplementary PDFs state that every headline evidence-lock check passed, but the supplementary table resets three proxy targets to the newly observed values. The executed V8 notebook retaining the frozen targets passes 24 of 27 checks. Correct the statement or produce a preserved execution that verifies the original locks.
- Retain the corrected fixed-six-class bootstrap implementation. The audited exact-version rerun now reproduces the PDFs' rounded MLP interval of 0.701–0.851; the original V8 code had changed the class denominator in resamples with an absent class.
- Choose one authoritative proxy-model result generation and propagate it consistently through the abstract, tables, supplement, and validation text. Do not mix the frozen Linux, V8/Colab, and Windows rerun values.
- Recover or recreate and version the exact editable source of the supplied submission PDFs. The repository's current 50/21-page journal-neutral LaTeX source is a different manuscript generation.
- Repair or explicitly archive the standalone integrated experiment rerun boundary: its script refers to raw/derived inputs that are not present in its package.

See [`SCIENTIFIC_REPOSITORY_AUDIT_2026-09-02.md`](audit/SCIENTIFIC_REPOSITORY_AUDIT_2026-09-02.md) before revising the submission.

## Required before final submission

- Confirm the complete author list, order, affiliations, and corresponding author.
- Finalise CRediT contributions for every author.
- Confirm funding and grant numbers, or state that no specific funding supported the work.
- Confirm competing interests.
- Finalise acknowledgements and permissions/site-access statements.
- Decide the final code and data licence.
- Create permanent public repository/release identifiers only after the author approves public disclosure.
- Adapt the journal-neutral LaTeX source to the current *Journal of Cultural Heritage* submission template and live author guidelines.
- Re-check abstract length, keywords, highlights, graphical abstract, declarations, figure/table placement, and separate-file requirements against the live submission portal.
- Perform a final language, reference, figure-resolution, and cross-file consistency audit after journal formatting.
- Replace Figure 1 in the submission with the audited Sentinel-2-based version and its corrected source/caption attribution.
- Retain a transparent generative-AI declaration consistent with the publisher's current policy; do not conceal code, figure-production, or language-editing assistance.

## Scientific wording that must remain controlled

- Use **relative field-inspection priority**, **landscape pressure**, and **terrain/hydrological susceptibility**.
- Do not describe the composite as confirmed damage, absolute risk, deterioration probability, causal climate impact, or legal/UNESCO buffer mapping.
- Keep climate–spectral findings exploratory unless new independent evidence supports stronger inference.
- Describe the machine-learning benchmark as WorldCover-derived proxy agreement, not independent heritage-condition accuracy.
