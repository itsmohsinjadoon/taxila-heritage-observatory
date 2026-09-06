"""Publication vector schematic of CHIP's executed evidence and experiment paths."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'manuscript/figures/main'
INK='#203648';BLUE='#39789B';GOLD='#B17B37';GREY='#71808C';LIGHT='#F2F5F7'
plt.rcParams.update({'font.family':'DejaVu Sans','pdf.fonttype':42,'svg.fonttype':'none','mathtext.fontset':'dejavusans'})
fig,ax=plt.subplots(figsize=(7.6,8.6));ax.set(xlim=(0,7.6),ylim=(0,8.6));ax.axis('off')
def text(x,y,s,size=8.5,color=INK,weight='normal',ha='left',va='center'):
 return ax.text(x,y,s,fontsize=size,color=color,fontweight=weight,ha=ha,va=va,linespacing=1.4)
def box(x,y,w,h,title,body,color=BLUE,size=8.3):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.008,rounding_size=0.04',fc='white',ec='#CCD5DB',lw=.7))
 ax.plot([x+.015,x+.015],[y+.08,y+h-.08],color=color,lw=2)
 text(x+.11,y+h-.18,title,8.7,color,'bold')
 text(x+.11,y+h-.43,body,size,va='top')
def arrow(x1,y1,x2,y2,dashed=False,color=INK):
 ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle='-|>',mutation_scale=8,lw=.85,color=color,linestyle=(0,(3,2)) if dashed else '-'))

text(.13,8.33,'CHIP',18,INK,'bold')
text(1.09,8.34,'From geospatial evidence to inspection decisions',11.2,INK,'bold')
text(.13,8.01,'17 geolocated components  |  250 / 500 / 1,000 m analytical neighbourhoods',8.8)
ax.plot([.13,7.46],[7.82,7.82],lw=.8,color='#CED7DD')
text(.13,7.64,'A   PRIORITY CONSTRUCTION',9,BLUE,'bold')
text(4.01,7.64,'B   CLIMATE CONTEXT',8.7,GOLD,'bold')
text(5.91,7.64,'C   PROXY EVALUATION',8.5,GREY,'bold')
box(.13,6.53,1.69,.90,'Landsat C2 L2','55 scenes; five epochs\nE2004-E2024; 30 m',BLUE)
box(1.99,6.53,1.73,.90,'Elevation / drainage','One-arc-second DEM\nSlope; wetness; D8',BLUE)
box(4.01,6.53,1.68,.90,'Daily weather','1991-2025; ERA5: 4 cells\nPOWER comparison',GOLD,size=8.0)
box(5.89,6.53,1.57,.90,'Labels + predictors','WorldCover 2020/2021\nLandsat E2019 features',GREY,size=8.0)
arrow(.975,6.51,.975,6.25);arrow(2.85,6.51,2.85,6.25)
arrow(4.85,6.51,4.85,6.25,color=GOLD);arrow(6.67,6.51,6.67,6.25,color=GREY)
box(.13,5.12,3.59,1.11,'01  Summaries and oriented percentiles','Masked spectral medians: NDVI / NDBI / MNDWI\nTerrain: slope P90 / wetness P90 / drainage median\nFixed spectral reference: 85 component-epochs\nTerrain and reconstructed endpoint reference: 17',BLUE,size=8.35)
box(4.01,5.12,1.68,1.11,'Native support','Four-cell daily mean\n35 annual summaries\nMatched acquisition dates\nNo weather downscaling',GOLD,size=8.0)
box(5.89,5.12,1.57,1.11,'Spatial design','20,749 samples\n12,094 development\n4,467 buffer excluded\n4,188 outer test',GREY,size=8.0)
arrow(1.925,5.1,1.925,4.90);arrow(4.85,5.1,4.85,4.90,color=GOLD);arrow(6.67,5.1,6.67,4.90,color=GREY)
box(.13,4.03,3.59,.85,'02  Hierarchical decision rule',r'$L=\frac{1}{4}z_N+\frac{1}{4}z_B+\frac{1}{2}z_W\quad T=\frac{z_S+z_H+z_D}{3}$'+'\n'+r'$P(w)=wL+(1-w)T\quad$ reference: $w=0.5$',BLUE,size=10)
box(4.01,4.03,1.68,.85,'Trend / window tests','Theil-Sen; residual blocks\n12 metrics; FDR adjustment\n7-365 d acquisition lags',GOLD,size=8.0)
box(5.89,4.03,1.57,.85,'Model selection','7 families x 3 settings\n3 buffered inner folds\n63 inner training fits',GREY,size=8.0)
arrow(1.925,4.01,1.925,3.82)
ax.plot([.69,3.15],[3.81,3.81],color=BLUE,lw=.7)
for x in [.69,1.925,3.15]:arrow(x,3.81,x,3.64,color=BLUE)
box(.13,2.55,1.12,1.07,'Structure','Factor ablation\n27 scenarios\n3 x 50,000 draws\nExact crossings',BLUE,size=8.0)
box(1.365,2.55,1.12,1.07,'Blocks','90 / 150 / 300 m\nShared weights\n2,000 per size\nOverlap retained',BLUE,size=8.0)
box(2.60,2.55,1.12,1.07,'Position','30 / 60 / 120 m\n2,000 per radius\nUniform-area jitter\nZero-shift control',BLUE,size=7.8)
for x in [.69,1.925,3.15]:arrow(x,2.53,x,2.34,color=BLUE)
ax.plot([.69,3.15],[2.33,2.33],color=BLUE,lw=.7);arrow(1.925,2.33,1.925,2.15,color=BLUE)
box(.13,1.24,3.59,.89,'03  Joint propagation and rank acceptability','500 spatial states x 10 decision settings = 5,000 vectors\nMedian ranks; central 95% intervals; top-k frequencies\nStructural tiers and reconstruction-dependent priorities',BLUE,size=8.3)
arrow(4.85,4.01,4.85,3.64,color=GOLD);arrow(6.67,4.01,6.67,3.64,color=GREY)
box(4.01,1.24,1.68,2.38,'Interpretation','Opposing product trends\n\nAcquisition-window forcing\n\nFive-epoch associations\n\nProduct and support limits\n\nClimate does not create\nfine-scale rank differences',GOLD,size=8.2)
box(5.89,1.24,1.57,2.38,'Outer diagnostics','Macro-F1 / paired blocks\n\nLog loss / Brier / ECE\n\nOOF temperature scaling\n\nFeature / null controls\n\nThree refit seeds\n\nColab / Windows repeat',GREY,size=8.0)
arrow(1.925,1.22,1.925,1.00,color=BLUE)
arrow(4.85,1.22,4.85,1.00,True,GOLD)
arrow(6.67,1.22,6.67,1.00,True,GREY)
ax.add_patch(FancyBboxPatch((.13,.12),7.33,.86,boxstyle='round,pad=.008,rounding_size=.05',fc=LIGHT,ec='#CCD5DB',lw=.7))
text(.26,.76,'04  CONSERVATION INTERPRETATION',9.2,INK,'bold')
text(.26,.51,'Persistent inspection set  |  Mechanism-specific field questions  |  Explicit evidence limits',8.65)
text(.26,.28,'Output: relative inspection priorities. Independent monument-condition validation remains a field task.',8.25)
fig.subplots_adjust(left=0,right=1,bottom=0,top=1)
for ext in ['pdf','svg','png']:fig.savefig(OUT/f'figure_02_chip_framework.{ext}',dpi=400,facecolor='white')
p=OUT/'figure_02_chip_framework.svg';p.write_text('\n'.join(line.rstrip() for line in p.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8',newline='\n')
plt.close(fig)
