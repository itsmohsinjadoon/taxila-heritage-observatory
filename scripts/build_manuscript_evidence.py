from pathlib import Path
import json,shutil,hashlib,re
import numpy as np
import pandas as pd
root=Path(__file__).resolve().parents[1]; m=root/'manuscript'
base=root
ext=root/'experiments/spatial_extension/2026-09-06-colab'
pub=root/'experiments/reproduction/2026-09-06-windows/tables'
data=root/'data/Taxila_CHIP_Frozen_Evidence_Data'
summary=json.loads((ext/'summary.json').read_text());comparison=pd.read_csv(ext/'model_comparison.csv');sel=pd.read_csv(ext/'model_selection.csv')
names={'RandomForest':'random forest','Logistic':'logistic regression','ExtraTrees':'extra trees','HistGradientBoosting':'histogram gradient boosting','MLP':'MLP','XGBoost':'XGBoost','CatBoost':'CatBoost'}
r=summary['primary_metrics']
mac={'ExtensionModel':names[summary['primary']],'ExtensionFOne':f"{r['macro_f1']:.3f}",'ExtensionCV':f"{sel.iloc[0].inner_macro_f1:.3f}",
     'ExtensionLow':f"{r['f1_low']:.3f}",'ExtensionHigh':f"{r['f1_high']:.3f}",'ExtensionAgreement':f"{r['overall_agreement']:.3f}"}
legacy_path=pub/'proxy_model_comparison.csv'
legacy=pd.read_csv(legacy_path);lr=legacy.loc[legacy.primary_selected_from_inner_cv].iloc[0]
mac.update(LegacyFOne=f'{lr.macro_f1:.6f}',LegacyAgreement=f'{lr.overall_agreement:.6f}',LegacyECE=f'{lr.top_label_ece_10bin:.6f}')
mac['ExtensionInterpretation']=r'''The MLP had the largest outer macro-F1 (0.849), but did not lead the inner spatial comparison. Random forest exceeded logistic regression by 0.0145 (paired 95\% interval 0.0028--0.0283), whereas histogram gradient boosting exceeded random forest by 0.0248 (0.0117--0.0663). These are conditional, unadjusted pairwise intervals. Out-of-fold temperature scaling worsened outer log loss from 0.498 to 0.574 and calibration error from 0.014 to 0.136, indicating poor transfer of this calibration. The fixed logistic bands-only control reached macro-F1 0.824, compared with 0.671 for indices alone, 0.140 for location alone and 0.070 after label shuffling. Random-forest macro-F1 ranged from 0.8205 to 0.8214 across three refit seeds. No model was substituted on the basis of these outer diagnostics.'''
(m/'sections/result_macros.tex').write_text('\n'.join('\\newcommand{\\'+k+'}{'+v+'}' for k,v in mac.items())+'\n')
joined=sel[['model','inner_macro_f1','primary_selected']].merge(comparison.drop(columns='primary_selected'),on='model')
lines=[r'\begin{table}[tbp]\centering\small',r'\caption{Buffered spatial extension. Family selection uses inner development macro-F1; outer scores are retrospective proxy agreement.}\label{tab:models}',r'\begin{tabular}{p{.35\linewidth}rrrr}\toprule',r'Model & Inner F1 & Outer F1 & 95\% interval & ECE \\\midrule']
for _,row in joined.iterrows():
    name={'MLP':'MLP','XGBoost':'XGBoost','CatBoost':'CatBoost'}.get(row.model,names[row.model].capitalize())+(' (primary)' if row.primary_selected else '')
    lines.append(f"{name} & {row.inner_macro_f1:.3f} & {row.macro_f1:.3f} & {row.f1_low:.3f}--{row.f1_high:.3f} & {row.ece:.3f}"+r' \\')
lines += [r'\bottomrule\end{tabular}',r'\end{table}']
(m/'tables/main/table_extension_models.tex').write_text('\n'.join(lines))
def tex(s):
    return str(s).replace('\\',r'\textbackslash{}').replace('_',r'\_').replace('&',r'\&').replace('%',r'\%').replace('#',r'\#')
def table(frame,caption,formats=None,widths=None):
    frame=frame.copy()
    for c in frame:
        if pd.api.types.is_numeric_dtype(frame[c]):frame[c]=frame[c].map(lambda x:f'{x:.4f}' if pd.notna(x) else '--')
    fmt=widths or ('l'+'r'*(len(frame.columns)-1))
    return frame.to_latex(index=False,escape=True,longtable=True,caption=caption,column_format=fmt)
supp=[r'''\documentclass[10pt,a4paper]{article}
\usepackage[margin=22mm]{geometry}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern,microtype,graphicx,booktabs,longtable,array,amsmath,caption,pdflscape,placeins}
\usepackage[numbers,sort&compress]{natbib}
\usepackage[hidelinks]{hyperref}
\graphicspath{{../figures/main/}{../figures/supplementary/}}
\setlength{\emergencystretch}{2em}
\begin{document}
\renewcommand{\thetable}{S\arabic{table}}
\renewcommand{\thefigure}{S\arabic{figure}}
\begin{center}\Large\bfseries Supplementary Information\end{center}
\begin{center}Sensitivity-aware inspection prioritisation for archaeological landscapes: a reproducible Taxila observatory\end{center}
\section{Scope and evidence generations}
The main manuscript is the anonymous source in \texttt{main.tex}. This supplement distinguishes historical frozen records from the corrected annual bootstrap and the new seven-family spatial extension. Counts and component scores can be reproduced from frozen inputs; historical stochastic records remain labelled by their uncertainty design. No outer proxy agreement validates monument condition. The previously examined outer stripe makes the new comparison retrospective.

\section{Component inventory and analytical support}
Saraikala is preserved without invented geometry. Coordinates are inventory points, not property polygons. The same 17 mapped components are compared at all three radii.
\input{../tables/supplementary/table_s01_component_inventory.tex}
\section{Corrected annual climate analysis}
The notebook now resamples detrended residual blocks. A trend-restored ensemble supplies confidence intervals; a constant-baseline ensemble supplies null slopes. The 12 annual metrics form the multiplicity family. This differs from the historical annual/seasonal family, so adjusted values must not be interchanged. Heavy precipitation counts days exceeding the 1991--2020 wet-day 95th percentile (wet days have at least 1 mm rain); hot days exceed the baseline maximum-temperature 95th percentile. Heatwave duration is the longest run above that temperature threshold, without a separate minimum-duration criterion. Dry-spell duration counts consecutive days below 1 mm. Rx1day and Rx5day are the largest one-day and rolling five-day precipitation totals. The observed precipitation point slope is unchanged; the earlier notebook's raw-series block intervals and probabilities are superseded. Validation checks newly computed probability bounds and finite ordered intervals, in addition to historical-reference checks.
''']
climate=pd.read_csv(pub/'annual_climate_trends_recomputed.csv')
c=climate[['metric','theil_sen_slope_per_year','moving_block_slope_ci_low_95','moving_block_slope_ci_high_95','moving_block_p_two_sided','fdr_adjusted_block_p']]
c.columns=['Metric','Slope/year','CI low','CI high','p','Annual q']
supp.append(r'\begingroup\scriptsize\setlength{\tabcolsep}{3pt}'+table(c,'Corrected annual residual-block trends; 2,000 draws and five-year blocks.',widths=r'p{.35\linewidth}rrrrr')+r'\endgroup')
supp.append(r'''Precipitation and evapotranspiration slopes are in mm year$^{-1}$, temperature slopes in $^\circ$C year$^{-1}$, humidity in percentage points year$^{-1}$, soil moisture in m$^3$ m$^{-3}$ year$^{-1}$ and event counts in days year$^{-1}$. Effective-sample-size diagnostics use detrended lag-one correlation and are bounded by the observed record length; they do not replace the bootstrap.
\section{Ranks and uncertainty scope}
The following tables retain the archived component-score and uncertainty generations. The weight experiment perturbs the integrated domain architecture; the spatial experiment resamples 150 m spectral blocks with terrain fixed. They must not be described as the same probability distribution.
''')
ranks=pd.read_csv(data/'13_tables/component_rankings_250m_500m_1000m.csv')[['component_id','rank_250m','rank_500m','rank_1000m','score_500m']]
ranks.columns=['Component','Rank 250 m','Rank 500 m','Rank 1,000 m','Score 500 m']
supp.append(table(ranks,'Frozen component scores and scale-dependent ranks.'))
sp=pd.read_csv(data/'14_statistics/component_rank_spatial_block_bootstrap.csv')[['component_id','rank_median','rank_ci_low_95','rank_ci_high_95','probability_top_3']]
sp.columns=['Component','Median rank','Low','High','Top-3 frequency']
supp.append(table(sp,'Archived spatial-block rank uncertainty; terrain held fixed.'))
wt=pd.read_csv(data/'13_tables/baseline_reproduction/monte_carlo_domain_weight_rank_uncertainty.csv')[['component_id','monte_carlo_median_rank','rank_p2_5','rank_p97_5','probability_top_3']]
wt.columns=sp.columns
supp.append(table(wt,'Archived 50,000-draw integrated-domain weight sensitivity.'))
supp.append(r'''\section{Spatial benchmark protocol and complete diagnostics}
The input SHA-256 is \texttt{3188160a144c5020e7d21bb50a195e07a686d941134ade35a57232fe41ddc1b1}. The outer development/buffer/test counts are 12,094/4,467/4,188. The minimum observed inter-sample distance is 2,040 m; the earlier nominal grid-boundary separation was 2,010 m. Both refer to the same geographic split but different distance definitions.

Inner validation covers block rows 0--2, 3--6 and 7--9, with adjacent block rows excluded from training. One fold has no water-class training observations. The six-class scoring denominator remains fixed. All model families receive three configurations; there is no test-driven hyperparameter search. Random forest and extra trees use 300 trees; histogram boosting 250 iterations; XGBoost and CatBoost 300 iterations; MLP a (64,32) hidden layout and 400 iterations. Complete parameters and per-fold scores are in the executable notebook and JSON search record. Early stopping is disabled. XGBoost and CatBoost are strong additional comparators, not evidence of a universal SOTA result.
''')
paired=pd.read_csv(ext/'paired_block_comparisons.csv').drop(columns='primary');paired.columns=['Comparator','F1 difference','CI low','CI high']
supp.append(table(paired,'Paired 2,000-block-bootstrap macro-F1 differences: primary random forest minus comparator. Intervals are unadjusted exploratory comparisons.',widths=r'p{.38\linewidth}rrr'))
cal=pd.read_csv(ext/'calibration_comparison.csv')[['variant','temperature','log_loss','brier','ece']];cal.columns=['Variant','Temperature','Log loss','Brier','ECE']
supp.append(table(cal,'Development-only temperature calibration evaluated on the outer stripe.'))
ctl=pd.read_csv(ext/'diagnostic_controls.csv')[['experiment','macro_f1','overall_agreement','log_loss','ece']];ctl.columns=['Control','Macro-F1','Agreement','Log loss','ECE']
supp.append(table(ctl,'Fixed-capacity diagnostic controls; not alternative model-selection candidates.',widths=r'p{.38\linewidth}rrrr'))
seed=pd.read_csv(ext/'seed_sensitivity.csv')[['seed','macro_f1','overall_agreement','log_loss','ece']];seed.columns=['Seed','Macro-F1','Agreement','Log loss','ECE']
supp.append(table(seed,'Three-seed sensitivity of the development-selected random forest.'))
supp.append(r'''\section{Historical reproduction discrepancies}
The original frozen targets are macro-F1 0.830795, agreement 0.833095 and ECE 0.014280. The historical exact-package Windows rerun reported 0.830072, 0.828080 and 0.015117. The original bootstrap had also changed the macro-F1 denominator when a resample lacked a class; the fixed-six-class correction produced the previously audited interval 0.701--0.851. Historical expected values were not overwritten after observing a rerun. Full current execution status and environment are preserved in the accompanying receipt. Engineering validation that reuses frozen model tables is not a full model refit.

\section{Additional evidence and reproduction boundary}
The frozen archive contains retained scene identifiers, acquisition-window weather, seasonal climate comparisons, sensor composition, common-support counts, threshold sensitivity, harmonisation sensitivity, complete factor/domain ablations, all component ranks and source licences. The notebook additionally generates shared-block, positional and joint-uncertainty analyses. The standalone legacy integrated script references missing intermediate reflectance inputs and is not presented as a self-contained source-to-result pipeline. Original satellite data should be recovered through the acquisition manifests where needed.

The selected supplementary figures below preserve archived non-primary evidence and retain their original scientific scope. Files and caption sources are indexed in the review package.
''')
for file,caption in [('figure_03_five_epoch_landscape_pressure_maps.pdf','Five-epoch landscape-pressure context. Colour denotes relative pressure, not accumulated deterioration.'),('figure_06_epoch_specific_weather_forcing.pdf','Weather matched to the retained Landsat acquisition windows; contextual rather than causal.'),('figure_08_terrain_hydrological_susceptibility.pdf','Elevation-derived terrain and drainage proxies. These do not constitute a hydraulic model.'),('figure_10_component_ranks_by_scale.pdf','Component ranks at the three analytical neighbourhood radii.'),('figure_12_indicator_redundancy.pdf','Dependence among component-level indicator ranks.'),('figure_14_ablation.pdf','Archived factor/domain ablation. Changes in rank identify architectural sensitivity.')]:
    supp.append(r'\begin{figure}[p]\centering\includegraphics[width=\textwidth,height=.77\textheight,keepaspectratio]{'+file+r'}\caption{'+caption+r'}\end{figure}')
supp.append(r'\end{document}')
(m/'supplementary/supplementary_information.tex').write_text('\n'.join(supp))
for file in [m/'sections/04_methods.tex']:
    file.write_text(file.read_text().replace('wilson2017good','wilson2017practices'))
# Tie generated manuscript quantities to specific input bytes.
source_files=[legacy_path,ext/'summary.json',ext/'model_comparison.csv',ext/'model_selection.csv',pub/'annual_climate_trends_recomputed.csv']
pd.DataFrame([dict(path=str(p.relative_to(base)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in source_files]).to_csv(m/'source_traceability/revision_result_sources.csv',index=False)
print('Generated result macros, comparison table and anonymous supplement')
