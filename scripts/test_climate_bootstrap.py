"""Regression checks that distinguish residual-block inference from raw-series shuffling."""
from pathlib import Path
import ast
import nbformat
import numpy as np
import pandas as pd
from scipy.stats import theilslopes
from typing import Iterable

n=nbformat.read(Path(__file__).resolve().parents[1]/'notebooks/Taxila_CHIP_Q1_Executable_Analysis.ipynb',as_version=4)
tree=ast.parse(n.cells[3].source)
names={'moving_block_trend_experiment','benjamini_hochberg'}
module=ast.Module(body=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names],type_ignores=[])
scope=dict(np=np,pd=pd,theilslopes=theilslopes,Iterable=Iterable,SEED=311)
exec(compile(module,'notebook-climate-functions','exec'),scope)
fn=scope['moving_block_trend_experiment']
x=np.arange(1991,2026); rng=np.random.default_rng(917)
e=np.zeros(35)
for i in range(1,35):e[i]=.55*e[i-1]+rng.normal(scale=.07)
data=pd.DataFrame({'year':x,'trend':.7*(x-x[0])+e,'constant':np.ones(35)})
a=fn(data,metrics=['trend','constant'],draws=300,seed=311)
b=fn(data,metrics=['trend','constant'],draws=300,seed=311)
pd.testing.assert_frame_equal(a,b)
trend=a.iloc[0]
assert trend.moving_block_slope_ci_low_95>.6
assert trend.moving_block_slope_ci_low_95<.7<trend.moving_block_slope_ci_high_95
assert trend.moving_block_p_two_sided<.05
assert a.iloc[1].moving_block_p_two_sided==1
assert a.moving_block_p_two_sided.between(0,1).all()
assert a.fdr_adjusted_block_p.between(0,1).all()
print('PASS: trend retained, null calibrated in bounds, constant series p=1, seed reproducible')
