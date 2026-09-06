# Mathematical and visual manuscript revision

The corresponding author requested greater technical depth, directly relevant journal references, a comprehensive framework figure and a meaningful 3D visual. The active paper now contains 14 numbered equations, 44 cited references, seven figures and three tables. Internal review history remains outside the article.

## Equation-to-implementation correspondence

| Main equation | Definition | Implementation evidence |
| --- | --- | --- |
| 1 | NDVI, NDBI, MNDWI band ratios | Original index papers and the acquisition/processing code |
| 2 | Oriented midrank percentile with average ties | `oriented_percentile` and `recompute_fixed_scores` in the canonical analysis notebook |
| 3 | Common-support spectral convergence | Endpoint raster masks and adverse-tail definitions in the analysis |
| 4 | Regularised numerical wetness proxy | `build_terrain_context`; contributing-cell count, geometric-mean cell width, 0.05-degree slope floor and 0.01 tangent regularisation |
| 5 | Hierarchical landscape, terrain and weighted priority | `recompute_fixed_scores`; static terrain uses slope P90, wetness P90 and median drainage distance |
| 6 | Exact pairwise decision-weight crossing | New `scripts/build_decision_geometry.py`; algebraic solution of equal linear scores |
| 7 | Shared exponential block weights and count-weighted medians | `sample_shared_block_medians` and `weighted_median` |
| 8 | Uniform-area coordinate displacement | `displace_points`; radius is maximum radius times square root of a uniform draw |
| 9 | Nested top-k rank frequency | `joint_uncertainty_experiment`; 500 spatial states and ten decision draws each |
| 10 | Theil-Sen annual slope | Annual climate trend implementation and original estimator reference |
| 11 | Acquisition-antecedent precipitation | `lag_features` in `execute_experiment_pipeline.py`; acquisition date excluded |
| 12 | Three-fold family/configuration selection and fixed-six-class macro-F1 | `scripts/run_spatial_extension.py`; seven families, three configurations, three folds |
| 13 | Log loss and unnormalised multiclass Brier score | `metrics` in the spatial-extension script |
| 14 | Probability temperature scaling | Development OOF fitting in the spatial-extension script; 1e-12 clipping, scalar bounds 0.25-4 |

The fixed spectral reference comprises 85 component-epoch summaries per radius. Spatial/positional reconstruction reranks 17 endpoint summaries, as the executable notebook does. The article now explicitly states this reference-population difference. It must not be described as coordinate noise alone. Terrain operations on the geographic elevation tile use local metric approximations; spectral neighbourhoods use UTM.

## New deterministic analysis

The decision-weight calculation uses existing fixed E2024 summaries at three discrete radii with equal-factor terrain. It enumerates 220 open rank-order intervals and checks both an interior 10% and 90% point in each, giving 440 ordering checks. Exact uniform-weight top-three mass sums to three across components at each radius. At 500 m, exact acceptabilities differ from the recorded 50,000-draw Monte Carlo experiment by at most 0.0023816. No observations or earlier experimental outputs were modified.

Figure 5 combines a full component-rank matrix, a 3D Giri rank-response plot at discrete radii, and exact leadership intervals. The 3D view shows decision sensitivity; it does not interpolate a physical surface or represent new terrain measurements. Source CSVs and an execution receipt are in `experiments/decision_analysis/2026-09-06/`. The eight leadership identities are retained using five colour roots plus neutral tones and hatching rather than hiding narrow intervals in an Other category.

Figure 2 has separate priority-construction, climate-context and proxy-evaluation paths, with the scoring equations and executed experimental designs. Both figures are exported as vector PDF/SVG and 400-dpi PNG; Python sources are editable. The author's supplied Figure 1 remains byte-identical.

## Reference selection

The new contextual references include Megarry et al. (2026), Journal of Cultural Heritage, DOI `10.1016/j.culher.2025.11.008`, and Butt et al. (2025), the directly relevant Taxila urban-encroachment study, DOI `10.3390/su17031059`. The mathematical treatment activates original work on GIS multicriteria analysis, rank acceptability, spatial validation and proper scoring rules, alongside the temperature-scaling paper from the official PMLR proceedings.

The bibliography prioritises direct topical and methodological relevance, including Journal of Cultural Heritage and Remote Sensing of Environment. Quartiles are properties of journals in a specified year/category and are not treated as article-level evidence quality. Foundational original sources are retained even when they are conference papers. Active-reference metadata checks are recorded in `reference_verification_2026-09-06.json` and the manuscript traceability log; a verified DOI is not itself a claim-validation test.

Primary content consulted: https://www.sciencedirect.com/science/article/pii/S1296207425002523 ; https://pure.qub.ac.uk/en/publications/land-use-and-land-cover-analysis-of-cultural-world-heritage-to-in/ ; https://www.mdpi.com/2071-1050/17/3/1059 ; https://pubsonline.informs.org/doi/10.1287/opre.49.3.444.11220 ; https://proceedings.mlr.press/v70/guo17a.html . Metadata additionally verified with Crossref and DOI content negotiation on 6 September 2026.

Submission declarations and independent field-condition validation remain unresolved author/data dependencies. This revision strengthens the mathematical description, decision analysis and presentation; it does not assert Q1 acceptance or state-of-the-art predictive superiority.
