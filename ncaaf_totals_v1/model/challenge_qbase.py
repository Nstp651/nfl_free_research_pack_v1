#!/usr/bin/env python3
"""Temporal walk-forward challengers for NCAA Totals QBASE.

This does NOT touch production selection. It measures whether a nonlinear model
materially improves the transparent Ridge baseline on exactly the same leak-free
training frame. Results are written for audit before architecture is changed.
The audit is deliberately market-blind and is a required promotion gate.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

import train_qbase as tq


def model_for(name: str):
    if name == "hgb_15":
        return HistGradientBoostingRegressor(
            learning_rate=0.05, max_iter=300, max_leaf_nodes=15,
            min_samples_leaf=30, l2_regularization=5.0, random_state=651,
        )
    if name == "hgb_31":
        return HistGradientBoostingRegressor(
            learning_rate=0.04, max_iter=350, max_leaf_nodes=31,
            min_samples_leaf=35, l2_regularization=10.0, random_state=651,
        )
    if name == "extra_trees":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", ExtraTreesRegressor(
                n_estimators=400, min_samples_leaf=5, max_features=0.75,
                n_jobs=-1, random_state=651,
            )),
        ])
    if name == "random_forest":
        return Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("model", RandomForestRegressor(
                n_estimators=300, min_samples_leaf=6, max_features=0.75,
                n_jobs=-1, random_state=651,
            )),
        ])
    raise KeyError(name)


def walk(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    seasons = sorted(frame["season"].unique())
    out = []
    for i, s in enumerate(seasons):
        tr_seasons = seasons[:i]
        if len(tr_seasons) < 3:
            continue
        tr = frame[frame.season.isin(tr_seasons)]
        te = frame[frame.season == s]
        m = model_for(name)
        m.fit(tr[tq.FULL_FEATURES], tr.total)
        pred = m.predict(te[tq.FULL_FEATURES])
        for (_, r), p in zip(te.iterrows(), pred):
            out.append({"season":int(s), "week":int(r.week), "actual":float(r.total), "pred":float(p)})
    return pd.DataFrame(out)


def met(df: pd.DataFrame) -> dict:
    y=df.actual.to_numpy(float); p=df.pred.to_numpy(float); e=y-p
    return {
        "n":int(len(df)),
        "mae":float(np.mean(np.abs(e))),
        "rmse":float(math.sqrt(np.mean(e**2))),
        "bias":float(np.mean(e)),
        "residual_sd":float(np.std(e, ddof=1)),
    }


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--start',type=int,default=2016)
    ap.add_argument('--end',type=int,default=2025)
    ap.add_argument('--cache',default='/tmp/ncaaf-qbase-cache')
    ap.add_argument('--output',default=str(Path(__file__).parent/'QBASE_CHALLENGERS.md'))
    args=ap.parse_args()
    frame,_=tq.build_frame(args.start,args.end,Path(args.cache))
    results=[]
    # Reproduce selected Ridge on the same frame.
    ridge=tq.walk_forward(frame,tq.FULL_FEATURES,100.0)
    rr={"model":"ridge_full_100",**met(ridge.rename(columns={'residual':'_ignore'}))}
    results.append(rr); print('CHALLENGER',json.dumps(rr,sort_keys=True))
    for name in ('hgb_15','hgb_31','extra_trees','random_forest'):
        p=walk(frame,name); r={"model":name,**met(p)}; results.append(r)
        print('CHALLENGER',json.dumps(r,sort_keys=True))
    results.sort(key=lambda r:(r['mae'],r['rmse']))
    base=next(r for r in results if r['model']=='ridge_full_100')
    lines=[
        '# NCAA Totals QBASE — Nonlinear Challenger Audit','',
        f'Frame: **{len(frame)}** FBS-v-FBS games, {args.start}-{args.end}; temporal walk-forward.', '',
        '| Model | N | MAE | RMSE | Bias | Residual SD | MAE Δ vs Ridge |','|---|---:|---:|---:|---:|---:|---:|']
    for r in results:
        lines.append(f"| {r['model']} | {r['n']} | {r['mae']:.3f} | {r['rmse']:.3f} | {r['bias']:.3f} | {r['residual_sd']:.3f} | {r['mae']-base['mae']:+.3f} |")
    winner=results[0]
    lines += ['',f"Best challenger: **{winner['model']}**.",'',
              'This report is market-blind and does not automatically promote a challenger. Promotion requires a material, stable temporal gain and a reproducible production scorer.']
    Path(args.output).write_text('\n'.join(lines))
    print('WINNER',json.dumps(winner,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
