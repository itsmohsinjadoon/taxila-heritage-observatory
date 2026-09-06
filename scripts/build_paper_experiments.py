"""Generate numerical paper tables without changing editorial prose."""
from pathlib import Path
import json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];M=ROOT/'manuscript'
EXT=ROOT/'experiments/spatial_extension/2026-09-06-colab'
PUB=ROOT/'experiments/reproduction/2026-09-06-windows/tables'
def write(path,text):path.write_text(text+'\n',encoding='utf-8',newline='\n')
summary=json.loads((EXT/'summary.json').read_text(encoding='utf-8'))
sel=pd.read_csv(EXT/'model_selection.csv');models=pd.read_csv(EXT/'model_comparison.csv');r=summary['primary_metrics']
mac={'ExtensionModel':'random forest','ExtensionFOne':f"{r['macro_f1']:.3f}",'ExtensionCV':f'{sel.iloc[0].inner_macro_f1:.3f}','ExtensionLow':f"{r['f1_low']:.3f}",'ExtensionHigh':f"{r['f1_high']:.3f}",'ExtensionAgreement':f"{r['overall_agreement']:.3f}"}
write(M/'sections/result_macros.tex','\n'.join('\\newcommand{\\'+k+'}{'+v+'}' for k,v in mac.items()))
names={'RandomForest':'Random forest','Logistic':'Logistic regression','ExtraTrees':'Extra trees','HistGradientBoosting':'Histogram boosting','MLP':'MLP','XGBoost':'XGBoost','CatBoost':'CatBoost'}
frame=sel[['model','inner_macro_f1','primary_selected']].merge(models.drop(columns='primary_selected'),on='model')
lines=[r'\begin{table}[tbp]\centering\small',r'\caption{Seven-family spatial comparison. The primary model is selected using buffered development folds; outer intervals use 2,000 shared test-block resamples.}\label{tab:models}',r'\begin{tabular}{p{.35\linewidth}rrrr}\toprule',r'Model & Inner F1 & Outer F1 & 95\% interval & ECE \\\midrule']
for row in frame.itertuples():
    name=names[row.model]+(' (primary)' if row.primary_selected else '')
    lines.append(f'{name} & {row.inner_macro_f1:.3f} & {row.macro_f1:.3f} & {row.f1_low:.3f}--{row.f1_high:.3f} & {row.ece:.3f}'+r' \\')
lines += [r'\bottomrule\end{tabular}',r'\end{table}'];write(M/'tables/main/table_extension_models.tex','\n'.join(lines))
cal=pd.read_csv(EXT/'calibration_comparison.csv');ctl=pd.read_csv(EXT/'diagnostic_controls.csv')
lines=[r'\begin{table}[tbp]\centering\small',r'\caption{Feature controls and probability calibration on the same outer stripe. Feature controls use fixed-capacity logistic regression, except the class-prior control. Temperature is fitted exclusively to development out-of-fold probabilities.}\label{tab:diagnostics}',r'\begin{tabular}{p{.49\linewidth}rrr}\toprule',r'Experiment & Macro-F1 & Log loss & ECE \\\midrule']
for i,row in cal.iterrows():
    name='Random forest, raw' if i==0 else 'Random forest, temperature scaled'
    lines.append(f'{name} & {row.macro_f1:.3f} & {row.log_loss:.3f} & {row.ece:.3f}'+r' \\')
lines.append(r'\midrule')
for name,row in zip(['Bands only','Indices only','Location only','Shuffled development labels','Class prior'],ctl.itertuples()):lines.append(f'{name} & {row.macro_f1:.3f} & {row.log_loss:.3f} & {row.ece:.3f}'+r' \\')
lines += [r'\bottomrule\end{tabular}',r'\end{table}'];write(M/'tables/main/table_diagnostic_experiments.tex','\n'.join(lines))
def supplementary(name,frame,caption,fmt):
    text=frame.to_latex(index=False,longtable=True,escape=True,float_format=lambda x:f'{x:.3f}',caption=caption,column_format=fmt)
    write(M/'tables/supplementary'/name,r'\begingroup\small'+text+r'\endgroup')
j=pd.read_csv(PUB/'joint_uncertainty_rank_summary.csv')[['component_id','rank_median','rank_ci_low_95','rank_ci_high_95','probability_top_3','probability_top_5']]
j.columns=['Component','Median rank','Low','High','Top-3','Top-5'];supplementary('table_full_joint.tex',j,'All components under 500 spatial states crossed with ten decision settings.','lrrrrr')
s=pd.read_csv(PUB/'structural_scenario_stability.csv')[['component_id','median_rank','rank_min','rank_max','top3_frequency','top5_frequency']]
s.columns=j.columns;supplementary('table_full_structural.tex',s,'All components across 27 support, weight and terrain-formulation scenarios.','lrrrrr')
a=pd.read_csv(PUB/'ablation_summary.csv')[['scenario','spearman_rho_with_reference','top5_overlap','maximum_absolute_rank_shift']]
a.columns=['Scenario','Spearman rho','Top-5 overlap','Max shift'];supplementary('table_full_ablation.tex',a,'Complete factor and domain ablation comparisons.',r'p{.38\linewidth}rrr')
sources=[EXT/n for n in ['summary.json','model_comparison.csv','model_selection.csv','calibration_comparison.csv','diagnostic_controls.csv','paired_block_comparisons.csv','seed_sensitivity.csv']]+[PUB/n for n in ['annual_climate_trends_recomputed.csv','ablation_summary.csv','baseline_comparison_summary.csv','structural_scenario_stability.csv','domain_weight_rank_sensitivity.csv','shared_block_size_rank_sensitivity.csv','point_displacement_rank_sensitivity.csv','joint_uncertainty_rank_summary.csv','primary_500m_component_priority.csv']]
pd.DataFrame([dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources]).to_csv(M/'source_traceability/revision_result_sources.csv',index=False)
print('Generated main comparison tables, full supplementary tables and source traceability.')
