# Contributing

Taxila Heritage Observatory is the public data and code archive supporting a submitted research article. Changes should preserve the frozen evidence chain and must not silently alter numerical claims.

## Change discipline

1. Create a focused branch.
2. Record scientific changes in `docs/audit/REVISION_LOG.md`.
3. Update the relevant claim/evidence, equation/code, display/source, and result-disposition records.
4. Run `python scripts/validate_repository.py`.
5. Re-run the affected experiment profile and retain its validation report.
6. Compile both the main manuscript and Supplementary Information.
7. Request review before merging into `main`.

Do not commit credentials, local absolute paths, downloaded publisher PDFs, LaTeX auxiliary files, or unverified replacement datasets.
