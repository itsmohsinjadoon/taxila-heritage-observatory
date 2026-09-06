"""Exact weight-interval analysis and a three-panel scale/weight figure.

Uses fixed E2024 component summaries; it does not re-extract pixels or interpolate
between radii. The 3D panel shows three discrete rank-response slices.
"""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Patch
from scipy.stats import rankdata

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'data/Taxila_CHIP_Frozen_Evidence_Data/13_tables/baseline_reproduction/component_epoch_integrated_scores.csv'
OUT=ROOT/'experiments/decision_analysis/2026-09-06'
FIG=ROOT/'manuscript/figures/main'
OUT.mkdir(parents=True,exist_ok=True)
SHORT={'139-001':'Khanpur Cave','139-003':'Bhir Mound','139-004':'Sirkap','139-005':'Sirsukh','139-006':'Dharmarajika','139-007':'Khader Mohra','139-008':'Kalawan','139-009':'Giri complex','139-010':'Kunala','139-011':'Jandial','139-012':'Lalchak / Badalpur','139-013':'Mohra Moradu','139-014':'Pippala','139-015':'Jaulian','139-016':'Lalchak mounds','139-017':'Bhallar','139-018':'Giri Mosque / tombs'}
df=pd.read_csv(SOURCE);df=df[df.epoch_id.eq('E2024')].sort_values(['radius_m','component_id'])
assert len(df)==51 and df.groupby('radius_m').size().eq(17).all()
intervals=[];rankrows=[];leaders=[];checks=[]
for radius,part in df.groupby('radius_m',sort=True):
 part=part.reset_index(drop=True);L=part.landscape_pressure_score.to_numpy();T=part.terrain_susceptibility_score.to_numpy();slope=L-T
 np.testing.assert_allclose((L+T)/2,part.local_priority_score,atol=1e-12)
 breaks=[0.,1.]
 for i in range(17):
  for j in range(i+1,17):
   den=slope[i]-slope[j]
   if abs(den)>1e-12:
    crossing=(T[j]-T[i])/den
    if 1e-10<crossing<1-1e-10:breaks.append(float(crossing))
 # Collapse numerically identical crossings; interval interiors avoid tie policy.
 ordered=sorted(breaks);breaks=[ordered[0]]
 for x in ordered[1:]:
  if x-breaks[-1]>1e-10:breaks.append(x)
 local=[]
 for left,right in zip(breaks[:-1],breaks[1:]):
  mid=(left+right)/2;score=T+mid*slope;rank=rankdata(-score,method='ordinal').astype(int)
  # The ordering must hold throughout each exact open interval.
  for frac in [.1,.9]:
   np.testing.assert_array_equal(rank,rankdata(-(T+(left+frac*(right-left))*slope),method='ordinal'))
  for i,row in part.iterrows():
   intervals.append(dict(radius_m=int(radius),w_lower=left,w_upper=right,component_id=row.component_id,component_name=SHORT[row.component_id],rank=int(rank[i]),top3=bool(rank[i]<=3)))
  lead=part.iloc[np.argmin(rank)].component_id
  if local and local[-1]['component_id']==lead:local[-1]['w_upper']=right
  else:local.append(dict(radius_m=int(radius),w_lower=left,w_upper=right,component_id=lead,component_name=SHORT[lead]))
 leaders+=local;checks.append(dict(radius_m=int(radius),interior_intervals=len(breaks)-1,ordering_probes=2*(len(breaks)-1)))
 for w in np.linspace(0,1,1001):
  rank=rankdata(-(T+w*slope),method='ordinal').astype(int)
  for i,row in part.iterrows():rankrows.append(dict(radius_m=int(radius),landscape_weight=float(w),component_id=row.component_id,rank=int(rank[i])))
it=pd.DataFrame(intervals);ld=pd.DataFrame(leaders);grid=pd.DataFrame(rankrows)
it.to_csv(OUT/'exact_rank_intervals.csv',index=False,lineterminator='\n')
ld.to_csv(OUT/'exact_leader_intervals.csv',index=False,lineterminator='\n')
grid.to_csv(OUT/'rank_response_grid.csv',index=False,lineterminator='\n')
freq=it.assign(width=it.w_upper-it.w_lower,top3mass=lambda x:x.width*x.top3).groupby(['radius_m','component_id','component_name'],as_index=False).agg(exact_uniform_top3=('top3mass','sum'),total_weight_mass=('width','sum'))
np.testing.assert_allclose(freq.total_weight_mass,1,atol=1e-12)
for radius,part in freq.groupby('radius_m'):np.testing.assert_allclose(part.exact_uniform_top3.sum(),3,atol=1e-12)
freq.to_csv(OUT/'exact_uniform_weight_acceptability.csv',index=False,lineterminator='\n')
# Independent comparison with the recorded 50,000-draw uniform-weight experiment.
mcpath=ROOT/'experiments/reproduction/2026-09-06-windows/tables/domain_weight_rank_sensitivity.csv'
if not mcpath.exists():
 candidates=list((ROOT/'experiments/reproduction/2026-09-06-windows/tables').glob('*weight*'))
 print('Recorded weight tables:',[p.name for p in candidates])
else:
 mc=pd.read_csv(mcpath);mc=mc[mc.alpha.eq(1)].merge(freq[freq.radius_m.eq(500)],on='component_id')
 maxerr=float(abs(mc.probability_top_3-mc.exact_uniform_top3).max());assert maxerr<.015
 checks.append(dict(recorded_mc_draws=50000,max_absolute_difference=maxerr,check='Exact uniform mass versus recorded Monte Carlo'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
receipt=dict(status='PASS',source=SOURCE.relative_to(ROOT).as_posix(),source_sha256=sha(SOURCE),analysis='Analytical pairwise crossings of fixed E2024 scores, equal-factor terrain',radii_m=[250,500,1000],checks=checks,observational_data_changed=False,radius_interpolation=False)
(OUT/'execution_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8',newline='\n')
(OUT/'manifest.csv').write_text('file,sha256\n'+'\n'.join(p.name+','+sha(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='manifest.csv')+'\n',encoding='utf-8',newline='\n')

# Chart contract: relate rank to analytical radius and decision weight; retain all
# 17 components in panel a, illustrate Giri in b, and report every leader in c.
# Static/vector export; white paper, blue/gold/olive/pink categories plus neutrals.
INK='#203648';BLUE='#39789B';GOLD='#B17B37';OLIVE='#788B3D';PINK='#B35C7A';GREY='#7B8793'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.3,'text.color':INK,'axes.labelcolor':INK,'xtick.color':INK,'ytick.color':INK,'pdf.fonttype':42,'svg.fonttype':'none','axes.linewidth':.65})
fig=plt.figure(figsize=(7.6,6.45),facecolor='white')
ax=fig.add_axes([.205,.13,.245,.74])
order=df[df.radius_m.eq(500)].sort_values('local_priority_score',ascending=False).component_id.tolist()
matrix=np.column_stack([rankdata(-df[df.radius_m.eq(r)].set_index('component_id').loc[order,'local_priority_score'],method='ordinal') for r in [250,500,1000]])
colors=['#D6E5EF']*3+['#EDF3F6']*2+['#FFFFFF']*12
ax.imshow(matrix,cmap=ListedColormap(colors),norm=BoundaryNorm(np.arange(.5,18.5),17),aspect='auto')
for i in range(17):
 for j in range(3):ax.text(j,i,str(matrix[i,j]),ha='center',va='center',fontsize=8.2,fontweight='bold' if matrix[i,j]<=3 else 'normal')
ax.set_yticks(range(17),[SHORT[x] for x in order],fontsize=8);ax.set_xticks(range(3),['250 m','500 m','1,000 m']);ax.xaxis.tick_top()
ax.set_xticks(np.arange(-.5,3,1),minor=True);ax.set_yticks(np.arange(-.5,17,1),minor=True);ax.grid(which='minor',color='#DFE5E9',lw=.5);ax.tick_params(which='both',length=0);ax.tick_params(axis='y',pad=6)
for s in ax.spines.values():s.set_visible(False)
fig.text(.035,.96,'a  Fixed component ranks',fontsize=10,fontweight='bold')
fig.text(.035,.923,'E2024 | w = 0.5 | 17 components',fontsize=8.1)
fig.text(.205,.077,'Top three',fontsize=7.8,bbox=dict(facecolor='#D6E5EF',edgecolor='none',pad=3))
fig.text(.32,.077,'Ranks 4-5',fontsize=7.8,bbox=dict(facecolor='#EDF3F6',edgecolor='none',pad=3))

ax3=fig.add_axes([.51,.545,.46,.345],projection='3d')
for radius,color,style in [(250,GREY,':'),(500,BLUE,'-'),(1000,GOLD,'--')]:
 d=grid[grid.radius_m.eq(radius)&grid.component_id.eq('139-009')]
 ax3.plot(d.landscape_weight,np.full(len(d),radius),d['rank'],color=color,lw=1.5,ls=style)
 mid=d.iloc[500];ax3.scatter([.5],[radius],[mid['rank']],s=22,color=color,edgecolor='white',linewidth=.5,depthshade=False)
ax3.set(xlim=(0,1),ylim=(200,1050),zlim=(17,1),xticks=[0,.5,1],yticks=[250,500,1000],zticks=[1,5,9,13,17])
ax3.set_xlabel('Landscape weight w',labelpad=1,fontsize=7.8);ax3.set_ylabel('Radius (m)',labelpad=0,fontsize=7.8);ax3.set_zlabel('Giri rank',labelpad=0,fontsize=7.8)
ax3.tick_params(labelsize=7,pad=0);ax3.view_init(elev=24,azim=-58);ax3.set_box_aspect((1.15,1,1))
for axis in [ax3.xaxis,ax3.yaxis,ax3.zaxis]:axis.pane.fill=False;axis._axinfo['grid'].update(color='#E5E9EC',linewidth=.45)
fig.text(.51,.96,'b  Weight-by-radius response',fontsize=10,fontweight='bold')
fig.text(.51,.923,'Giri complex | discrete radii | dots: w = 0.5',fontsize=8.1)

axc=fig.add_axes([.59,.265,.355,.16])
lead_ids=list(dict.fromkeys(ld.component_id));palette=dict(zip(lead_ids,[GOLD,BLUE,GREY,OLIVE,PINK,INK,'#D6E5EF','#FFFFFF']))
hatches={x:('///' if k==7 else '') for k,x in enumerate(lead_ids)}
for yi,radius in enumerate([250,500,1000]):
 for row in ld[ld.radius_m.eq(radius)].itertuples():
  axc.barh(yi,row.w_upper-row.w_lower,left=row.w_lower,height=.58,color=palette[row.component_id],edgecolor=INK,lw=.35,hatch=hatches[row.component_id])
axc.set(xlim=(0,1),ylim=(-.6,2.6),xticks=[0,.25,.5,.75,1],yticks=[0,1,2],yticklabels=['250 m','500 m','1,000 m'],xlabel='Landscape weight w')
axc.invert_yaxis();axc.axvline(.5,color=INK,lw=.7,ls=':');axc.tick_params(axis='y',length=0)
for s in ['top','right','left']:axc.spines[s].set_visible(False)
fig.text(.51,.46,'c  Exact first-priority intervals',fontsize=10,fontweight='bold')
fig.legend([Patch(fc=palette[x],ec=INK,lw=.35,hatch=hatches[x]) for x in lead_ids],[SHORT[x] for x in lead_ids],loc='lower left',bbox_to_anchor=(.51,.057),ncol=2,frameon=False,fontsize=7.5,handlelength=1.1,columnspacing=1.2)
fig.text(.51,.023,'Equal-factor terrain; crossings computed analytically.',fontsize=7.7)
for ext in ['pdf','png','svg']:fig.savefig(FIG/f'figure_16_scale_weight_geometry.{ext}',dpi=400,facecolor='white')
p=FIG/'figure_16_scale_weight_geometry.svg';p.write_text('\n'.join(x.rstrip() for x in p.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8',newline='\n')
plt.close(fig)
table=r'''\begin{longtable}{lrll}
\caption{Exact first-priority weight intervals for fixed E2024 summaries and equal-factor terrain. Intervals refer to their interiors; a boundary can tie neighbouring leaders.}\\
\toprule Radius (m) & Lower $w$ & Upper $w$ & First-priority component\\\midrule
\endfirsthead
\toprule Radius (m) & Lower $w$ & Upper $w$ & First-priority component\\\midrule
\endhead
\bottomrule\endlastfoot
'''
for row in ld.itertuples():table+=f'{row.radius_m} & {row.w_lower:.4f} & {row.w_upper:.4f} & {row.component_name} '+r'\\'+'\n'
table+='\\end{longtable}\n'
(ROOT/'manuscript/tables/supplementary/table_exact_weight_intervals.tex').write_text(table,encoding='utf-8',newline='\n')
print(ld.to_string(index=False));print(json.dumps(receipt,indent=2))
