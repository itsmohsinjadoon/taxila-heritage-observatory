"""Retrospective, spatially buffered land-cover proxy benchmark; never condition validation."""
from __future__ import annotations
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ.setdefault(key, '2')
import argparse, hashlib, json, platform, time, warnings
from pathlib import Path
from datetime import datetime, timezone
from importlib.metadata import version
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import softmax
from scipy.spatial import cKDTree
from sklearn.base import clone
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import f1_score, accuracy_score, log_loss, confusion_matrix
from sklearn.model_selection import ParameterGrid
from xgboost import XGBClassifier
from catboost import CatBoostClassifier

FEATURES = ['blue','green','red','nir08','swir16','swir22','NDVI','NDBI','MNDWI','BSI']
LABELS = np.arange(6)
SEED = 311

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def metrics(y, p):
    pred = p.argmax(1)
    cm = confusion_matrix(y, pred, labels=LABELS)
    recall = np.divide(cm.diagonal(), cm.sum(1), out=np.zeros(6), where=cm.sum(1)>0)
    conf = p.max(1)
    bins = np.minimum((conf*10).astype(int),9)
    ece = sum(np.mean(bins==b)*abs(np.mean(pred[bins==b]==y[bins==b])-np.mean(conf[bins==b])) for b in range(10) if (bins==b).any())
    return dict(macro_f1=float(f1_score(y,pred,labels=LABELS,average='macro',zero_division=0)),
                overall_agreement=float(accuracy_score(y,pred)), balanced_accuracy_fixed6=float(recall.mean()),
                log_loss=float(log_loss(y,p,labels=LABELS)), brier=float(np.mean(np.sum((p-np.eye(6)[y])**2,axis=1))),ece=float(ece))

def candidates(seed):
    return {
        'Logistic': (make_pipeline(StandardScaler(), LogisticRegression(max_iter=1500)), {'logisticregression__C':[0.1,1,10]}),
        'RandomForest': (RandomForestClassifier(n_estimators=300, random_state=seed,n_jobs=2,class_weight='balanced_subsample'), {'min_samples_leaf':[1,5,12]}),
        'ExtraTrees': (ExtraTreesClassifier(n_estimators=300,random_state=seed,n_jobs=2,class_weight='balanced'), {'min_samples_leaf':[1,3,8]}),
        'HistGradientBoosting': (HistGradientBoostingClassifier(max_iter=250,early_stopping=False,random_state=seed,l2_regularization=1), {'max_leaf_nodes':[15,31,63]}),
        'MLP': (make_pipeline(StandardScaler(),MLPClassifier(max_iter=400,early_stopping=False,random_state=seed,hidden_layer_sizes=(64,32))), {'mlpclassifier__alpha':[0.0001,0.01,0.1]}),
        'XGBoost': (XGBClassifier(n_estimators=300,learning_rate=0.05,tree_method='hist',n_jobs=2,random_state=seed,objective='multi:softprob',num_class=6,subsample=0.8,colsample_bytree=0.8), {'max_depth':[3,5,7]}),
        'CatBoost': (CatBoostClassifier(iterations=300,learning_rate=0.05,loss_function='MultiClass',thread_count=2,random_seed=seed,verbose=False,allow_writing_files=False), {'depth':[4,6,8]})
    }

def inner_folds(frame):
    """Contiguous north/central/south validation bands, with one block-row exclusion."""
    rr = (frame.spatial_block.to_numpy()//10)
    folds=[]
    for lo,hi in [(0,2),(3,6),(7,9)]:
        va=np.flatnonzero((rr>=lo)&(rr<=hi))
        tr=np.flatnonzero((rr<lo-1)|(rr>hi+1))
        assert len(tr) and len(va)
        assert np.min(abs(np.unique(rr[tr])[:,None]-np.unique(rr[va])[None,:]))>=2
        assert frame.proxy_class.iloc[tr].nunique() >= 2
        folds.append((tr,va))
    return folds

def probabilities(model, X):
    raw=np.asarray(model.predict_proba(X))
    p=np.zeros((len(X),6))
    # Spatial folds may lack the geographically concentrated water class.
    # Never create synthetic labels or silently drop that class from scoring.
    if raw.shape[1]==6:
        return raw
    p[:,np.asarray(model.classes_,dtype=int)]=raw
    return p

def fit_search(estimator,grid,X,y,folds):
    records=[]
    for params in ParameterGrid(grid):
        scores=[]
        for tr,va in folds:
            model=clone(estimator).set_params(**params).fit(X[tr],y[tr])
            scores.append(f1_score(y[va],np.asarray(model.predict(X[va])).ravel(),labels=LABELS,average='macro',zero_division=0))
        records.append(dict(parameters=params,fold_scores=scores,mean=float(np.mean(scores))))
    best=max(records,key=lambda x:x['mean'])
    model=clone(estimator).set_params(**best['parameters']).fit(X,y)
    return model,best,records

def block_draw_scores(y,p,groups,draws=2000):
    blocks=np.unique(groups)
    cms=np.stack([confusion_matrix(y[groups==g],p[groups==g].argmax(1),labels=LABELS) for g in blocks])
    multiplicity=np.random.default_rng(SEED).multinomial(len(blocks),np.ones(len(blocks))/len(blocks),size=draws)
    sums=np.einsum('db,bij->dij',multiplicity,cms)
    den=sums.sum(1)+sums.sum(2)
    f1=np.divide(2*np.diagonal(sums,axis1=1,axis2=2),den,out=np.zeros_like(den,dtype=float),where=den>0).mean(1)
    return f1

def run(data,out):
    started=time.time(); out=Path(out); out.mkdir(parents=True,exist_ok=False)
    frame=pd.read_csv(data).drop(columns=['partition'],errors='ignore')
    assert len(frame)==20749 and not frame.duplicated(['row','col']).any()
    assert np.isfinite(frame[FEATURES].to_numpy()).all()
    assert set(frame.proxy_class)==set(range(1,7))
    block_col=frame.spatial_block%10
    test=block_col.isin([3,4]); buffer=block_col.isin([2,5]); dev=~(test|buffer)
    df=frame.loc[dev].reset_index(drop=True); tf=frame.loc[test].reset_index(drop=True)
    folds=inner_folds(df)
    split=frame[['row','col','spatial_block','proxy_class']].copy()
    split['role']=np.where(test,'test',np.where(buffer,'buffer','development'))
    split.to_csv(out/'split_manifest.csv',index=False)
    min_distance=float(cKDTree(df[['row','col']].to_numpy()*30).query(tf[['row','col']].to_numpy()*30)[0].min())
    protocol=dict(schema=1,created_utc=datetime.now(timezone.utc).isoformat(),source_sha256=digest(data),n_samples=len(frame),
                  seed=SEED,features=FEATURES,outer_test_columns=[3,4],outer_buffer_columns=[2,5],inner_validation_rows=[[0,2],[3,6],[7,9]],
                  inner_buffer_rows=1,labels=list(range(6)),selection='largest mean inner buffered macro-F1; lexicographic model tie-break',
                  bootstrap_draws=2000,development_n=len(df),test_n=len(tf),buffer_n=int(buffer.sum()),minimum_test_train_distance_m=min_distance,
                  limitation='Retrospective extension on an already examined outer stripe; not an untouched confirmatory test or independent condition validation.',
                  inner_training_class_counts=[df.proxy_class.iloc[tr].value_counts().sort_index().to_dict() for tr,va in folds],
                  early_stopping=False,packages={p:version(p) for p in ['numpy','pandas','scipy','scikit-learn','xgboost','catboost']},python=platform.python_version(),platform=platform.platform())
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2))
    X=df[FEATURES].to_numpy(); y=df.proxy_class.to_numpy()-1
    Xt=tf[FEATURES].to_numpy(); yt=tf.proxy_class.to_numpy()-1; groups=tf.spatial_block.to_numpy()
    models={}; selections=[]; searches={}
    # All selection completes before any outer-test prediction is made.
    for name,(est,grid) in candidates(SEED).items():
        print('Tuning',name,flush=True); t=time.time()
        model,best,history=fit_search(est,grid,X,y,folds)
        models[name]=model; searches[name]=history
        selections.append(dict(model=name,inner_macro_f1=best['mean'],parameters=json.dumps(best['parameters']),fit_seconds=time.time()-t))
        pd.DataFrame(selections).to_csv(out/'selection_progress.csv',index=False)
    sel=pd.DataFrame(selections).sort_values(['inner_macro_f1','model'],ascending=[False,True])
    primary=sel.iloc[0].model; sel['primary_selected']=sel.model.eq(primary)
    sel.to_csv(out/'model_selection.csv',index=False)
    (out/'inner_search.json').write_text(json.dumps(searches,indent=2))
    print('Development-selected model:',primary,flush=True)
    predictions=tf[['row','col','spatial_block','proxy_class']].copy(); rows=[]; bootstrap={}; probs={}
    for name,model in models.items():
        p=probabilities(model,Xt); probs[name]=p
        score_draws=block_draw_scores(yt,p,groups); bootstrap[name]=score_draws
        row=dict(model=name,primary_selected=name==primary,**metrics(yt,p),f1_low=float(np.quantile(score_draws,.025)),f1_high=float(np.quantile(score_draws,.975)))
        rows.append(row)
        predictions[name+'_prediction']=p.argmax(1)+1
        for k in range(6): predictions[f'{name}_p{k+1}']=p[:,k]
    pd.DataFrame(rows).to_csv(out/'model_comparison.csv',index=False)
    predictions.to_csv(out/'test_predictions.csv',index=False)
    paired=[]
    for name in models:
        if name==primary: continue
        delta=bootstrap[primary]-bootstrap[name]
        paired.append(dict(primary=primary,comparator=name,delta_macro_f1=metrics(yt,probs[primary])['macro_f1']-metrics(yt,probs[name])['macro_f1'],ci_low=np.quantile(delta,.025),ci_high=np.quantile(delta,.975)))
    pd.DataFrame(paired).to_csv(out/'paired_block_comparisons.csv',index=False)
    # One scalar temperature is learned only from development out-of-fold predictions.
    oof=np.full((len(y),6),np.nan)
    for tr,va in folds:
        model=clone(models[primary]).fit(X[tr],y[tr]); oof[va]=probabilities(model,X[va])
    assert np.isfinite(oof).all()
    opt=minimize_scalar(lambda t:log_loss(y,softmax(np.log(np.clip(oof,1e-12,1))/t,axis=1),labels=LABELS),bounds=(.25,4),method='bounded')
    temp=float(opt.x); cal=softmax(np.log(np.clip(probs[primary],1e-12,1))/temp,axis=1)
    pd.DataFrame([dict(variant='raw',temperature=1.,**metrics(yt,probs[primary])),dict(variant='OOF-temperature',temperature=temp,**metrics(yt,cal))]).to_csv(out/'calibration_comparison.csv',index=False)
    diagnostic=[]
    # Predeclared fixed-capacity ablations; none changes primary selection.
    for label,cols in [('bands-only',FEATURES[:6]),('indices-only',FEATURES[6:]),('location-only',['row','col'])]:
        model=make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=1500)).fit(df[cols],y)
        diagnostic.append(dict(experiment=label,**metrics(yt,model.predict_proba(tf[cols]))))
    null=make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=1500)).fit(X,np.random.default_rng(SEED).permutation(y))
    diagnostic.append(dict(experiment='shuffled-development-labels',**metrics(yt,null.predict_proba(Xt))))
    dummy=DummyClassifier(strategy='prior').fit(X,y)
    diagnostic.append(dict(experiment='class-prior',**metrics(yt,dummy.predict_proba(Xt))))
    pd.DataFrame(diagnostic).to_csv(out/'diagnostic_controls.csv',index=False)
    seed_rows=[dict(seed=SEED,**metrics(yt,probs[primary]))]
    primary_params=json.loads(sel.loc[sel.model.eq(primary),'parameters'].iloc[0])
    for seed in [733,2026]:
        est=candidates(seed)[primary][0].set_params(**primary_params).fit(X,y)
        seed_rows.append(dict(seed=seed,**metrics(yt,est.predict_proba(Xt))))
    pd.DataFrame(seed_rows).to_csv(out/'seed_sensitivity.csv',index=False)
    report=dict(status='PASS',primary=primary,source_sha256=digest(data),test_n=len(yt),development_n=len(y),
                test_blocks=int(np.unique(groups).size),minimum_distance_m=min_distance,
                primary_metrics=next(row for row in rows if row['model']==primary),temperature=temp,duration_seconds=time.time()-started,
                scope='Retrospective spatial land-cover proxy benchmark; no claim of heritage-condition accuracy or universal SOTA.')
    (out/'summary.json').write_text(json.dumps(report,indent=2))
    pd.DataFrame([dict(file=p.name,sha256=digest(p),bytes=p.stat().st_size) for p in sorted(out.iterdir()) if p.is_file()]).to_csv(out/'manifest.csv',index=False)
    print(json.dumps(report,indent=2),flush=True)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--data',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); run(args.data,args.output)
