"""Publication vector figure of the four central robustness experiments."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'experiments/reproduction/2026-09-06-windows/tables';OUT=ROOT/'manuscript/figures/main'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.titlesize':9,'axes.titleweight':'bold','pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'#203648','text.color':'#203648','axes.edgecolor':'#7a8791'})
fig,axes=plt.subplots(2,2,figsize=(9,7),layout='constrained');a,b,c,d=axes.ravel()
base=pd.read_csv(P/'baseline_comparison_summary.csv').iloc[1:2][['baseline','spearman_rho_with_reference']].rename(columns={'baseline':'scenario'})
abl=pd.read_csv(P/'ablation_summary.csv').iloc[1:][['scenario','spearman_rho_with_reference']]
ab=pd.concat([base,abl],ignore_index=True);labels=ab.scenario.str.replace('Ungrouped equal-factor mean','Ungrouped factors').str.replace('Without ','Omit ')
a.barh(np.arange(len(ab)),ab.spearman_rho_with_reference,color=['#ba6b50' if v<0 else '#287e8a' for v in ab.spearman_rho_with_reference],height=.65)
a.set_yticks(np.arange(len(ab)),labels);a.invert_yaxis();a.set_xlim(-.4,1.05);a.axvline(0,color='#adb5bc',lw=.7);a.set_xlabel('Spearman correlation with reference');a.set_title('(a) Baselines and indicator ablation',loc='left');a.grid(axis='x',alpha=.15);a.set_axisbelow(True)
names={'139-009':'Giri complex','139-017':'Bhallar','139-018':'Giri Mosque/tombs','139-015':'Jaulian'};colors=['#287e8a','#bc7939','#685998','#55769d']
for ax,file,x,label in [(b,'shared_block_size_rank_sensitivity.csv','block_size_m','Spatial block size (m)'),(c,'point_displacement_rank_sensitivity.csv','maximum_displacement_m','Maximum displacement (m)')]:
    t=pd.read_csv(P/file)
    for (key,name),color in zip(names.items(),colors):
        q=t[t.component_id.eq(key)].sort_values(x);ax.plot(q[x],q.probability_top_3,marker='o',ms=4,lw=1.5,label=name,color=color)
    ax.set_ylim(-.035,1.06);ax.set_yticks([0,.25,.5,.75,1]);ax.set_xticks(sorted(t[x].unique()));ax.set_xlabel(label);ax.set_ylabel('Top-three frequency');ax.grid(alpha=.16);ax.set_axisbelow(True)
b.set_title('(b) Shared spatial blocks',loc='left');c.set_title('(c) Position and feature re-extraction',loc='left')
fig.legend(*b.get_legend_handles_labels(),loc='outside lower center',ncol=4,fontsize=8,frameon=False)
j=pd.read_csv(P/'joint_uncertainty_rank_summary.csv').head(8);short={'139-006':'Dharmarajika','139-007':'Khader Mohra','139-013':'Mohra Moradu','139-014':'Pippala',**names}
y=np.arange(len(j));d.errorbar(j.rank_median,y,xerr=np.vstack([j.rank_median-j.rank_ci_low_95,j.rank_ci_high_95-j.rank_median]),fmt='o',color='#287e8a',ecolor='#a6c8cc',capsize=3,ms=4,lw=1.3)
d.set_yticks(y,[short[x] for x in j.component_id]);d.invert_yaxis();d.set_xlim(.5,19.9);d.set_xticks([1,5,9,13,17]);d.set_xlabel('Rank: median and 95% interval');d.set_title('(d) Joint spatial-decision uncertainty',loc='left');d.grid(axis='x',alpha=.15)
for i,row in enumerate(j.itertuples()):d.text(18,i,f'{row.probability_top_3:.3f}',fontsize=7,va='center')
d.text(18,-.8,'Top-3',fontsize=7,ha='left')
for ext in ['pdf','png','svg']:fig.savefig(OUT/f'figure_15_experimental_robustness.{ext}',dpi=350,facecolor='white')
svg=OUT/'figure_15_experimental_robustness.svg';svg.write_text('\n'.join(x.rstrip() for x in svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8',newline='\n')
plt.close(fig);print('Generated four-panel experimental robustness figure.')
