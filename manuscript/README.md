# Journal of Cultural Heritage manuscript source

This directory contains the current anonymized article (main.tex), anonymized Supplementary Information (supplementary/supplementary_information.tex), and the separate editor-facing title_page.tex. The article and title page are separate submission files. Do not include title_page.tex in an anonymized review source archive.

The current article contains 8 figures and 2 tables. Its source-based count is 4,837 words excluding tables and references. The Overleaf article compiled to 22 pages with 0 errors and 0 warnings on 24 September 2026. The separate title page compiled to 2 pages with 0 errors and 0 warnings. The [repository submission checklist](../docs/JCH_SUBMISSION_READINESS.md) records the remaining author and portal checks.

## Source map

- main.tex loads sections 01, 02, 04–08 and sections/result_macros.tex, then references.bib.
- title_page.tex holds author names and institutional postal addresses, the corresponding author, CRediT roles, funding, interests, acknowledgements, data/code access and the AI declaration. It is for the editor, not anonymous reviewers.
- figures/main/figure_02_chip_framework.pdf is the canonical raster-inclusive CHIP diagram. The .png and .svg files are source or export variants. figures/main/figure_02_chip_workflow.tex is a superseded workflow schematic and is not included by main.tex.
- Figure 1 is the author-approved study-area map. Do not replace it with a regenerated open-data comparison. Figure 1 imagery and Figure 2 Copernicus credits are documented in [licences and attribution](LICENSES_AND_ATTRIBUTION.md).
- highlights.txt, cover_letter.txt, and Declaration_of_Interest.txt are separate submission components. The GitHub repository has no release or DOI; the data/code statements do not claim one.

## Compile

From this directory, run latexmk -pdf main.tex for the article. The LaTeX source must include sections/result_macros.tex; omitting it causes undefined commands in the Results section. GitHub Actions runs the manuscript PDF build and repository validation. Check both on the final commit before packaging.

For review, supply editable anonymized source with the required sections, tables, bibliography and figures. Exclude title_page.tex, draft notes, historical figure variants not referenced by main.tex, and private author information. The article reports relative field-inspection priority and does not claim independent heritage-condition prediction or legal/UNESCO buffer mapping. Historical revision and reproducibility findings remain in [docs/audit/](../docs/audit/).
