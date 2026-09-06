from pathlib import Path
import shutil,json,hashlib,re,sys
import numpy as np
import pandas as pd
import nbformat
from sklearn.metrics import f1_score,log_loss,confusion_matrix

root=Path(__file__).resolve().parents[1]
ext=root/'experiments/spatial_extension'
colab=ext/'2026-09-06-colab'
checks=[]
def check(name,condition,detail=''):
    checks.append(dict(check=name,status='PASS' if bool(condition) else 'FAIL',detail=detail))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for run in [ext/'2026-09-06-windows',colab]:
    prefix=run.name
    manifest=pd.read_csv(run/'manifest.csv')
    check(prefix+' recorded file hashes',all(sha(run/r.file)==r.sha256 for r in manifest.itertuples()))
    pred=pd.read_csv(run/'test_predictions.csv');tab=pd.read_csv(run/'model_comparison.csv')
    y=pred.proxy_class.to_numpy()-1
    check(prefix+' unique held-out samples',len(pred)==4188 and not pred.duplicated(['row','col']).any())
    for row in tab.itertuples():
        p=pred[[f'{row.model}_p{k}' for k in range(1,7)]].to_numpy();yp=p.argmax(1)
        check(prefix+' '+row.model+' probabilities',np.isfinite(p).all() and (p>=0).all() and np.allclose(p.sum(1),1,atol=1e-6))
        cm=confusion_matrix(y,yp,labels=np.arange(6));den=cm.sum(0)+cm.sum(1)
        f=np.divide(2*cm.diagonal(),den,out=np.zeros(6),where=den>0).mean()
        check(prefix+' '+row.model+' independent F1',np.isclose(f,row.macro_f1,atol=1e-12))
        check(prefix+' '+row.model+' log loss',np.isclose(log_loss(y,p,labels=np.arange(6)),row.log_loss,atol=1e-12))
        check(prefix+' '+row.model+' Brier',np.isclose(np.mean(np.sum((p-np.eye(6)[y])**2,axis=1)),row.brier,atol=1e-12))
    sel=pd.read_csv(run/'model_selection.csv').sort_values(['inner_macro_f1','model'],ascending=[False,True])
    check(prefix+' primary selected by inner folds',sel.iloc[0].model=='RandomForest' and sel.loc[sel.primary_selected,'model'].tolist()==['RandomForest'])
    split=pd.read_csv(run/'split_manifest.csv')
    check(prefix+' split counts',split.role.value_counts().to_dict()=={'development':12094,'buffer':4467,'test':4188})
nb=nbformat.read(colab/'Taxila_Spatial_Benchmark_Extension_executed.ipynb',as_version=4);nbformat.validate(nb)
code=[c for c in nb.cells if c.cell_type=='code']
check('Colab all six cells executed',len(code)==6 and all(c.execution_count is not None for c in code))
check('Colab no notebook errors',not any(o.output_type=='error' for c in code for o in c.outputs))
for p in (root/'notebooks').glob('*.ipynb'):
    n=nbformat.read(p,as_version=4);nbformat.validate(n)
    check(p.name+' clean source',all(c.get('execution_count') is None and not c.get('outputs') for c in n.cells if c.cell_type=='code'))
win=pd.read_csv(ext/'2026-09-06-windows/model_comparison.csv');lin=pd.read_csv(colab/'model_comparison.csv')
comparison=win[['model','macro_f1','ece']].merge(lin[['model','macro_f1','ece']],on='model',suffixes=('_windows','_colab'))
comparison['f1_colab_minus_windows']=comparison.macro_f1_colab-comparison.macro_f1_windows
comparison.to_csv(ext/'cross_platform_comparison.csv',index=False)
check('primary cross-platform F1 stable',abs(comparison.set_index('model').loc['RandomForest','f1_colab_minus_windows'])<1e-12)
figure=root/'manuscript/figures/main/figure_01_study_area_context_map.pdf'
check('user supplied Figure 1 exact bytes',sha(figure)=='6811779f3cf84089104ce5f53c187d999c3d1402bfb987645ec549e2ef0aae7d')
report=dict(status='PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL',checks=checks,
    colab_url='https://colab.research.google.com/drive/1_-gwyfIhY3L1pYl3VSb3xihCd5TwM2HI',
    scope='Artifact, arithmetic and execution verification; not independent ecological or heritage-condition validation.')
(root/'docs/audit/REVISION_VALIDATION_2026-09-06.json').write_text(json.dumps(report,indent=2))
print(report['status'],len(checks),'checks');print(comparison.to_string(index=False))
if report['status']!='PASS':print([x for x in checks if x['status']=='FAIL']);sys.exit(1)
