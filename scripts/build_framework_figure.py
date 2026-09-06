"""Editable vector schematic of the executed CHIP evidence paths."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'manuscript/figures/main'
INK='#203648'; TEAL='#207F82'; BLUE='#39789B'; GOLD='#B17B37'; LIGHT='#F1F5F7'
plt.rcParams.update({'font.family':'DejaVu Sans','pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none'})
fig,ax=plt.subplots(figsize=(7.6,5.45))
ax.set(xlim=(0,7.6),ylim=(0,5.45)); ax.axis('off')
def text(x,y,s,size=8.5,color=INK,weight='normal',ha='left'):
    ax.text(x,y,s,fontsize=size,color=color,fontweight=weight,ha=ha,va='center',linespacing=1.45)
def box(x,y,w,h,title,body,color=TEAL):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.015,rounding_size=0.07',lw=.8,ec=color,fc='white'))
    ax.plot([x+.1,x+w-.1],[y+h-.37,y+h-.37],color=color,lw=.65,alpha=.4)
    text(x+.13,y+h-.2,title,9,color,'bold')
    text(x+.13,y+(h-.4)/2,body,8.2)
def arrow(a,b,color=INK,style='-'):
    ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=9,lw=.9,color=color,linestyle=style))
text(.12,5.2,'CHIP',16,INK,'bold')
text(1.0,5.19,'Evidence to field-inspection priorities',11,INK,'bold')
text(.12,4.86,'01  OBSERVATIONS',8.3,BLUE,'bold')
text(2.66,4.86,'02  ANALYSIS',8.3,BLUE,'bold')
text(5.2,4.86,'03  INTERPRETATION',8.3,BLUE,'bold')
box(.12,3.6,2.13,1.03,'Landsat landscape record','55 scenes | five epochs\n30 m common endpoint mask',BLUE)
box(.12,2.36,2.13,1.03,'Terrain and components','Elevation and D8 drainage\n17 mapped components',TEAL)
box(.12,1.12,2.13,1.03,'Regional weather','Daily records, 1991–2025\nFour native reanalysis cells',GOLD)
box(2.66,3.6,2.13,1.03,'Landscape pressure  L','Oriented NDVI, NDBI, MNDWI\nCorrelated terms grouped',BLUE)
box(2.66,2.36,2.13,1.03,'Terrain susceptibility  T','Slope, wetness and proximity\n250 / 500 / 1,000 m support',TEAL)
box(2.66,1.12,2.13,1.03,'Climate context','Trends and acquisition lags\nCross-product comparison',GOLD)
box(5.2,2.94,2.22,1.69,'Relative priority','P = 0.5 L + 0.5 T\n\nSensitivity-aware tiers\nTargeted inspection questions',TEAL)
box(5.2,1.12,2.22,1.59,'Separate proxy benchmark','WorldCover-derived labels\nBuffered spatial model selection\nAgreement and calibration\nNo condition-validation link',BLUE)
for y in [4.115,2.875,1.635]: arrow((2.28,y),(2.63,y))
arrow((4.82,4.115),(5.17,4.115)); arrow((4.82,2.875),(5.17,3.3))
text(4.2,.91,'Climate informs interpretation; it does not create 30 m weather detail.',8,INK,ha='center')
ax.add_patch(FancyBboxPatch((.12,.12),7.3,.57,boxstyle='round,pad=.02,rounding_size=.05',fc=LIGHT,ec='none'))
text(.27,.50,'ROBUSTNESS',8.4,TEAL,'bold')
text(1.46,.50,'Scale • weights • ablation • spatial resampling • positional sensitivity',8)
text(.27,.28,'Decision boundary: screening of landscape context, not observed damage or deterioration probability.',8)
fig.subplots_adjust(left=0,right=1,bottom=0,top=1)
OUT.mkdir(parents=True,exist_ok=True)
for ext in ['pdf','svg','png']:
    fig.savefig(OUT/f'figure_02_chip_framework.{ext}',dpi=400,facecolor='white')
svg=OUT/'figure_02_chip_framework.svg'
svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8',newline='\n')
plt.close(fig)
