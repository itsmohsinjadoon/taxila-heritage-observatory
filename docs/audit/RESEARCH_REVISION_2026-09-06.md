# Research revision audit — 6 September 2026

## Outcome and evidence boundary

The article was rewritten around sensitivity-aware inspection prioritisation. It does not establish monument deterioration, causal climate effects, universal SOTA superiority or transfer accuracy at a new heritage property. The data provide landscape/terrain proxies and regional climate context; independent field-condition labels were not supplied. Seven contemporary model families, buffered inner validation, paired spatial uncertainty, calibration, controls and seed sensitivity strengthen the proxy benchmark within that boundary.

## Actual executions

The self-contained extension notebook ran to completion in the corresponding author's Google Colab (378 seconds of experiment computation, six executed code cells). Its downloaded results and executed notebook are in `experiments/spatial_extension/2026-09-06-colab`. The same script ran locally (about 430 seconds). The development-selected random forest achieved outer macro-F1 0.821433, 95% block interval 0.691099–0.835178, and agreement 0.812798. The MLP's larger outer F1 (0.849490) did not make it the selected model. Histogram boosting exceeded the selected model under the conditional paired comparison; this negative finding is retained. OOF temperature scaling worsened calibration and is reported without substitution. XGBoost's cross-platform F1 changed by -0.000608; primary random-forest F1 was stable. Complete model comparisons, all predictions, probabilities and source hashes are retained.

The corrected full historical notebook also completed (925 seconds). Data QA passed; frozen claim locks were 24/27. The development-selected historical MLP does not reproduce three earlier target scores; original targets and the REVIEW receipt remain intact. Stored-reference validation must not be called a clean model-refit reproduction.

## Statistical correction

The notebook moving-block climate routine had resampled raw annual values, destroying the trend, and used a two-tail sign fraction that could exceed one when slopes tied. It now resamples residual blocks, restores the fitted trend for confidence intervals and evaluates a constant-baseline null with a bounded plus-one Monte Carlo probability. Annual multiplicity correction covers 12 annual metrics. Historical mixed annual/seasonal q values are separate. Regression tests cover trend preservation, an exact constant null, bounded probabilities and deterministic seeds. Annual tables now come from recomputed outputs, not frozen copies.

## Data and model review

The 20,749 samples are class-stratified. Development/buffer/test counts are 12,094/4,467/4,188; test support spans 20 spatial blocks. Minimum observed sample separation is 2,040 m (the earlier 2,010 m describes grid edges). The outer stripe was already examined, so the extension is retrospective. Three contiguous inner folds exclude adjacent rows; one training fold lacks the concentrated water class. All six classes remain in the scoring denominator. Neither overall agreement nor this sampling design estimates population-area accuracy. The WorldCover response is land cover, not heritage condition. No raw data or expected benchmark targets were changed.

## Manuscript and figures

The main article uses the author's exact supplied study-area PDF and a new editable vector framework; the caption now correctly identifies dark-red analytical circles. The diagram separates the proxy benchmark from conservation prioritisation and climate context from fine-scale ranking. The paper distinguishes fixed two-domain scores, archived integrated-score weight sensitivity, and spatial uncertainty. Negative product agreement and calibration findings remain in the results. The active source entry points and result hashes are documented in `manuscript/README.md`. Earlier manuscript snapshots and audit records are historical.

## Journal and author checks

The live Journal of Cultural Heritage guide was checked: research article limit 5,000 words excluding references/tables, 10 figures/tables and 20 component illustrations; abstract up to 500 words; 1–6 keywords; a separate research aim up to 200 words; 3–5 highlights of up to 85 characters; separate title page and anonymous manuscript. The revised source targets these requirements. Source: https://www.sciencedirect.com/journal/journal-of-cultural-heritage/publish/guide-for-authors

Author order supplied by the user: Mohsin Khan (corresponding), Sadiq Ullah, Faridoon Khan. FAST department naming was checked against https://isb.nu.edu.pk/Academics/Faculty-DAIDS.php and the Khyber Pakhtunkhwa departmental spelling against https://sti.kp.gov.pk/about. The supplied FCAI abbreviation has not been expanded without confirmation. Funding, competing interests, individual CRediT roles, acknowledgements and full affiliation postal details remain unconfirmed. The private repository and Colab require an editor/reviewer access arrangement or a deposited anonymous archive before submission. No submission or public release was made.

## Remaining scientific limits

Independent expert/field labels, a new geographic holdout, and externally calibrated conservation thresholds are absent. A generic SOTA claim cannot be supported by this dataset and experiment alone. The legacy integrated package lacks some intermediate raw reflectance inputs and remains an archived evidence source. The supplied broad study-area locator and its basemap attribution should receive the authors' final cartographic/permissions review. Author approval, declarations and final venue checks remain necessary; detector scores or journal acceptance cannot be guaranteed.
