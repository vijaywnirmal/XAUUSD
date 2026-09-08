"""
Fit every monitor model on Postgres history + cross-asset data, save as JSON:
  model.json        direction  - logistic P(next ~1h return > 0)  (+ cross-asset feats)
  meta_model.json    meta-label - GBM P(the direction call is correct); trade only when high
  london_model.json  dedicated  - logistic at 13:00 UTC -> sign of the 13:00-17:00 move
  vol_model.json     volatility - ridge on log realised vol of the next ~1h

    python -m monitor.calibrate          # needs monitor/data/*_m5.parquet (run fetch_crossasset first)

Prints honest OOS numbers for each. The point of meta + london is COVERAGE vs
HIT-RATE on the confident subset, not a higher blanket AUC.
"""
from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, brier_score_loss, r2_score

from data_pipeline.dataset import load_bars
from monitor import config as C
from monitor.features import feature_frame, MODEL_COLS, VOL_COLS, LONDON_COLS
from monitor.xa_data import training_xa

H = C.PREDICT_HORIZON_BARS
LON_H = 48                          # 13:00 -> 17:00 UTC = 48 M5 bars


def _frame(split, oos=False):
    df = load_bars(C.TF, split=split, allow_oos=oos,
                   columns=["ts", "open", "high", "low", "close", "spread_mean"])
    xa = training_xa(df["ts"].min(), df["ts"].max())
    f = feature_frame(df, xa)
    from monitor.features import XA_COLS
    f[XA_COLS] = f[XA_COLS].fillna(0.0)          # pre-2016 / gaps -> neutral
    c = df["close"]
    f["y_dir"] = (c.shift(-H) / c - 1.0 > 0).astype(int)
    r5 = c.pct_change()
    f["y_vol"] = np.log(r5.pow(2).rolling(H).sum().shift(-H).pow(0.5).clip(lower=1e-8))
    f["fwd_ret"] = c.shift(-H) / c - 1.0
    f["fwd_ret_lon"] = c.shift(-LON_H) / c - 1.0
    return f


def _std(X):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    return mu, sd


def _save(path, obj):
    json.dump(obj, open(path, "w"), indent=1)


def main():
    tr, wf, oos = _frame("in_sample"), _frame("walk_forward"), _frame("out_of_sample", oos=True)
    cut_frac = 0.7

    # ============ DIRECTION (logistic, + cross-asset) ============
    d = tr.dropna(subset=MODEL_COLS + ["y_dir"])
    X, y = d[MODEL_COLS].to_numpy(float), d["y_dir"].to_numpy(int)
    k = int(len(X) * cut_frac)
    mu, sd = _std(X[:k])
    clf = LogisticRegression(C=0.5, max_iter=3000).fit((X[:k] - mu) / sd, y[:k])

    def dp(F):
        g = F.dropna(subset=MODEL_COLS + ["y_dir"])
        return g, clf.predict_proba((g[MODEL_COLS].to_numpy(float) - mu) / sd)[:, 1]

    print("DIRECTION (logistic + cross-asset)")
    for lab, F in [("train", d.iloc[:k]), ("test", d.iloc[k:]), ("walk-fwd 23", wf), ("oos 24-26", oos)]:
        g, p = dp(F)
        if len(g) > 200:
            a = roc_auc_score(g.y_dir, p)
            print(f"  {lab:12s} n={len(g):7d}  AUC={a:.4f}")
            if lab == "oos 24-26":
                a_oos = a
    g_oos, p_oos = dp(oos)
    session_auc = {s: round(float(roc_auc_score(g_oos[g_oos.session == s].y_dir,
                                                p_oos[(g_oos.session == s).to_numpy()])), 4)
                   for s in ("asia", "london", "ny_preopen", "ny", "late")
                   if (g_oos.session == s).sum() > 200}
    print("  session AUC:", session_auc)

    dd = pd.concat([d, wf.dropna(subset=MODEL_COLS + ["y_dir"])])
    Xf, yf = dd[MODEL_COLS].to_numpy(float), dd["y_dir"].to_numpy(int)
    muf, sdf = _std(Xf)
    clf = LogisticRegression(C=0.5, max_iter=3000).fit((Xf - muf) / sdf, yf)
    _save(C.MODEL_PATH, {"cols": MODEL_COLS, "coef": clf.coef_[0].tolist(),
                         "intercept": float(clf.intercept_[0]), "mean": muf.tolist(), "std": sdf.tolist(),
                         "horizon_bars": H, "metrics": {"oos_auc": round(float(a_oos), 4)},
                         "session_auc": session_auc, "trained_on": "2009..2024-06 + events + cross-asset"})

    # ============ META-LABEL (GBM: is the direction call right?) ============
    print("\nMETA-LABEL (GBM: P[direction call correct])")
    META_COLS = MODEL_COLS + ["_pdir", "_pdir_conf"]

    def meta_frame(F):
        g, p = dp(F)
        g = g.copy()
        g["_pdir"] = p
        g["_pdir_conf"] = np.abs(p - 0.5)
        g["_side"] = np.where(p >= 0.5, 1, -1)
        g["y_meta"] = (np.sign(g["fwd_ret"]) == g["_side"]).astype(int)
        return g.dropna(subset=["fwd_ret"])

    mt = meta_frame(d)
    mk = int(len(mt) * cut_frac)
    meta = HistGradientBoostingClassifier(max_depth=4, max_iter=250, learning_rate=0.05,
                                          l2_regularization=1.0)
    meta.fit(mt[META_COLS].iloc[:mk], mt["y_meta"].iloc[:mk])

    def meta_eval(F, label, thr=0.55):
        g = meta_frame(F)
        if len(g) < 200:
            return
        pm = meta.predict_proba(g[META_COLS])[:, 1]
        auc = roc_auc_score(g.y_meta, pm)
        sel = pm >= thr
        cov = sel.mean()
        hit_all = g.y_meta.mean()
        hit_sel = g.y_meta[sel].mean() if sel.any() else float("nan")
        print(f"  {label:12s} n={len(g):7d}  meta_AUC={auc:.4f}  base_hit={hit_all:.3f}  "
              f"| thr {thr}: coverage={cov:.2f}  hit_on_selected={hit_sel:.3f}")

    meta_eval(mt.iloc[:mk], "train")
    meta_eval(mt.iloc[mk:], "test")
    meta_eval(meta_frame(wf), "walk-fwd 23")
    meta_eval(meta_frame(oos), "oos 24-26")
    # sweep threshold on OOS
    go = meta_frame(oos); pmo = meta.predict_proba(go[META_COLS])[:, 1]
    print("  OOS threshold sweep (coverage / hit):")
    for thr in (0.52, 0.55, 0.58, 0.62):
        s = pmo >= thr
        if s.sum() > 50:
            print(f"    thr {thr}: cov={s.mean():.3f}  hit={go.y_meta[s].mean():.3f}  n={int(s.sum())}")

    metaf = pd.concat([mt, meta_frame(wf)])
    meta = HistGradientBoostingClassifier(max_depth=4, max_iter=250, learning_rate=0.05,
                                          l2_regularization=1.0).fit(metaf[META_COLS], metaf["y_meta"])
    import joblib
    joblib.dump({"model": meta, "cols": META_COLS, "dir_mu": muf.tolist(), "dir_sd": sdf.tolist(),
                 "dir_cols": MODEL_COLS, "dir_coef": clf.coef_[0].tolist(),
                 "dir_intercept": float(clf.intercept_[0])},
                C.MODEL_PATH.replace("model.json", "meta_model.joblib"))

    # ============ LONDON model (13:00 -> 17:00 UTC) ============
    print("\nLONDON continuation (logistic at 13:00 UTC -> sign of 13:00-17:00)")

    def lon_rows(F):
        m = pd.DatetimeIndex(F["ts"]).hour * 60 + pd.DatetimeIndex(F["ts"]).minute
        g = F[(m == 780)].dropna(subset=LONDON_COLS + ["fwd_ret_lon"])   # 13:00 bar
        return g, (g["fwd_ret_lon"] > 0).astype(int)

    lg, ly = lon_rows(d)
    lk = int(len(lg) * cut_frac)
    lmu, lsd = _std(lg[LONDON_COLS].to_numpy(float)[:lk])
    lclf = LogisticRegression(C=0.3, max_iter=3000).fit(
        (lg[LONDON_COLS].to_numpy(float)[:lk] - lmu) / lsd, ly.to_numpy()[:lk])

    def lon_eval(F, label):
        g, yv = lon_rows(F)
        if len(g) < 60:
            return
        p = lclf.predict_proba((g[LONDON_COLS].to_numpy(float) - lmu) / lsd)[:, 1]
        a = roc_auc_score(yv, p); acc = ((p > 0.5).astype(int) == yv).mean()
        print(f"  {label:12s} n={len(g):5d}  AUC={a:.4f}  acc={acc:.3f}")
        return a

    lon_eval(lg.iloc[:lk], "train")
    lon_eval(lg.iloc[lk:], "test")
    lon_eval(wf, "walk-fwd 23")
    l_oos = lon_eval(oos, "oos 24-26")

    lgf = pd.concat([lg, lon_rows(wf)[0]])
    lyf = (lgf["fwd_ret_lon"] > 0).astype(int)
    lmuf, lsdf = _std(lgf[LONDON_COLS].to_numpy(float))
    lclf = LogisticRegression(C=0.3, max_iter=3000).fit((lgf[LONDON_COLS].to_numpy(float) - lmuf) / lsdf, lyf)
    _save(C.MODEL_PATH.replace("model.json", "london_model.json"),
          {"cols": LONDON_COLS, "coef": lclf.coef_[0].tolist(), "intercept": float(lclf.intercept_[0]),
           "mean": lmuf.tolist(), "std": lsdf.tolist(), "horizon_bars": LON_H,
           "metrics": {"oos_auc": round(float(l_oos), 4)}})

    # ============ VOLATILITY (ridge) ============
    print("\nVOLATILITY (ridge on log realised vol, next ~1h)")
    v = tr.dropna(subset=VOL_COLS + ["y_vol"])
    Xv, yv = v[VOL_COLS].to_numpy(float), v["y_vol"].to_numpy(float)
    kv = int(len(Xv) * cut_frac)
    mv, sv = _std(Xv[:kv])
    reg = Ridge(alpha=2.0).fit((Xv[:kv] - mv) / sv, yv[:kv])

    def vr(F, label):
        g = F.dropna(subset=VOL_COLS + ["y_vol"])
        if len(g) < 200:
            return None, None
        p = reg.predict((g[VOL_COLS].to_numpy(float) - mv) / sv)
        r2 = r2_score(g.y_vol, p)
        qt = np.quantile(g.y_vol, [1/3, 2/3])
        acc = float((np.digitize(p, qt) == np.digitize(g.y_vol, qt)).mean())
        print(f"  {label:12s} n={len(g):7d}  R2={r2:.3f}  tercile_acc={acc:.3f}")
        return r2, acc

    vr(v.iloc[:kv], "train"); vr(v.iloc[kv:], "test"); vr(wf, "walk-fwd 23")
    r2o, acco = vr(oos, "oos 24-26")
    vf = pd.concat([v, wf.dropna(subset=VOL_COLS + ["y_vol"])])
    mvf, svf = _std(vf[VOL_COLS].to_numpy(float))
    reg = Ridge(alpha=2.0).fit((vf[VOL_COLS].to_numpy(float) - mvf) / svf, vf["y_vol"].to_numpy(float))
    preds = reg.predict((vf[VOL_COLS].to_numpy(float) - mvf) / svf)
    lo, hi = np.quantile(preds, [1/3, 2/3])
    _save(C.MODEL_PATH.replace("model.json", "vol_model.json"),
          {"cols": VOL_COLS, "coef": reg.coef_.tolist(), "intercept": float(reg.intercept_),
           "mean": mvf.tolist(), "std": svf.tolist(), "horizon_bars": H,
           "terciles": [float(lo), float(hi)],
           "pred_grid": np.quantile(preds, np.linspace(0, 1, 101)).round(6).tolist(),
           "metrics": {"oos_r2": round(float(r2o), 3), "oos_tercile_acc": round(float(acco), 3)}})

    print("\nsaved model.json, meta_model.joblib, london_model.json, vol_model.json")


if __name__ == "__main__":
    main()
