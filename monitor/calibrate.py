"""
Fit BOTH models on Postgres history and save them:
  monitor/model.json      - direction  : logistic reg -> P(next ~1h return > 0)
  monitor/vol_model.json   - volatility : ridge on log(next ~1h realised vol)

Both now include news / event-proximity features (FOMC / NFP / CPI).

    python -m monitor.calibrate

Prints, honestly:
  - direction AUC per window AND per volatility regime + session
  - volatility R^2 per window + the quiet/normal/explosive tercile accuracy
"""
from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score, brier_score_loss, r2_score

from data_pipeline.dataset import load_bars
from monitor import config as C
from monitor.features import feature_frame, MODEL_COLS, VOL_COLS

H = C.PREDICT_HORIZON_BARS


def _frame(split, oos=False):
    df = load_bars(C.TF, split=split, allow_oos=oos,
                   columns=["ts", "open", "high", "low", "close", "spread_mean"])
    f = feature_frame(df)
    c = df["close"]
    f["y_dir"] = (c.shift(-H) / c - 1.0 > 0).astype(int)
    r5 = c.pct_change()
    # realised vol of bars t+1 .. t+H : sqrt(sum r^2) over that forward window
    fwd_rv = r5.pow(2).rolling(H).sum().shift(-H).pow(0.5).clip(lower=1e-8)
    f["y_vol"] = np.log(fwd_rv)
    return f


def _std_fit(X):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    return mu, sd


def main():
    tr = _frame("in_sample")
    wf = _frame("walk_forward")
    oos = _frame("out_of_sample", oos=True)

    # ================= DIRECTION =================
    d = tr.dropna(subset=MODEL_COLS + ["y_dir"])
    X = d[MODEL_COLS].to_numpy(float); y = d["y_dir"].to_numpy(int)
    cut = int(len(X) * 0.7)
    mu, sd = _std_fit(X[:cut])
    clf = LogisticRegression(C=0.5, max_iter=3000).fit((X[:cut] - mu) / sd, y[:cut])

    def dauc(F, label):
        g = F.dropna(subset=MODEL_COLS + ["y_dir"])
        if len(g) < 200:
            return None
        p = clf.predict_proba((g[MODEL_COLS].to_numpy(float) - mu) / sd)[:, 1]
        a = roc_auc_score(g["y_dir"], p); b = brier_score_loss(g["y_dir"], p)
        print(f"  {label:20s} n={len(g):7d}  AUC={a:.4f}  Brier={b:.4f}")
        return a

    print("DIRECTION  (logistic, +event features)")
    dauc(d.iloc[:cut], "train 09-19")
    a_te = dauc(d.iloc[cut:], "test 19-22")
    dauc(wf, "walk-fwd 23")
    a_oos = dauc(oos, "oos 24-26")

    print("\n  OOS AUC by volatility regime (atr_pct tercile):")
    o = oos.dropna(subset=MODEL_COLS + ["y_dir", "atr_pct"])
    op = clf.predict_proba((o[MODEL_COLS].to_numpy(float) - mu) / sd)[:, 1]
    o = o.assign(_p=op)
    for lab, m in [("low vol  ", o.atr_pct <= 0.33), ("mid vol  ", (o.atr_pct > 0.33) & (o.atr_pct <= 0.66)),
                   ("high vol ", o.atr_pct > 0.66)]:
        s = o[m]
        if len(s) > 200:
            print(f"    {lab} n={len(s):6d}  AUC={roc_auc_score(s.y_dir, s._p):.4f}")
    print("  OOS AUC by session:")
    session_auc = {}
    for sess in ("asia", "london", "ny_preopen", "ny", "late"):
        s = o[o.session == sess]
        if len(s) > 200:
            session_auc[sess] = round(float(roc_auc_score(s.y_dir, s._p)), 4)
            print(f"    {sess:10s} n={len(s):6d}  AUC={session_auc[sess]:.4f}")

    # final direction model: through walk-forward
    dd = pd.concat([d, wf.dropna(subset=MODEL_COLS + ["y_dir"])])
    Xf = dd[MODEL_COLS].to_numpy(float); yf = dd["y_dir"].to_numpy(int)
    muf, sdf = _std_fit(Xf)
    clf = LogisticRegression(C=0.5, max_iter=3000).fit((Xf - muf) / sdf, yf)
    json.dump({
        "cols": MODEL_COLS, "coef": clf.coef_[0].tolist(), "intercept": float(clf.intercept_[0]),
        "mean": muf.tolist(), "std": sdf.tolist(), "horizon_bars": H,
        "metrics": {"test_auc": round(float(a_te), 4), "oos_auc": round(float(a_oos), 4)},
        "session_auc": session_auc,
        "trained_on": "2009-01..2024-06 M5 + FOMC/NFP/CPI proximity",
    }, open(C.MODEL_PATH, "w"), indent=1)

    # ================= VOLATILITY =================
    print("\nVOLATILITY  (ridge on log realised vol of the next ~1h)")
    v = tr.dropna(subset=VOL_COLS + ["y_vol"])
    Xv = v[VOL_COLS].to_numpy(float); yv = v["y_vol"].to_numpy(float)
    cv = int(len(Xv) * 0.7)
    muv, sdv = _std_fit(Xv[:cv])
    reg = Ridge(alpha=2.0).fit((Xv[:cv] - muv) / sdv, yv[:cv])

    def vr2(F, label):
        g = F.dropna(subset=VOL_COLS + ["y_vol"])
        if len(g) < 200:
            return None, None
        p = reg.predict((g[VOL_COLS].to_numpy(float) - muv) / sdv)
        r2 = r2_score(g["y_vol"], p)
        qt = np.quantile(g["y_vol"], [1/3, 2/3])
        acc = float((np.digitize(p, qt) == np.digitize(g["y_vol"], qt)).mean())
        print(f"  {label:20s} n={len(g):7d}  R2={r2:.3f}  tercile_acc={acc:.3f}")
        return r2, acc

    vr2(v.iloc[:cv], "train 09-19")
    vr2(v.iloc[cv:], "test 19-22")
    vr2(wf, "walk-fwd 23")
    r2_oos, acc_oos = vr2(oos, "oos 24-26")

    vf = pd.concat([v, wf.dropna(subset=VOL_COLS + ["y_vol"])])
    Xvf = vf[VOL_COLS].to_numpy(float); yvf = vf["y_vol"].to_numpy(float)
    mvf, svf = _std_fit(Xvf)
    reg = Ridge(alpha=2.0).fit((Xvf - mvf) / svf, yvf)
    preds = reg.predict((Xvf - mvf) / svf)
    lo, hi = np.quantile(preds, [1/3, 2/3])
    json.dump({
        "cols": VOL_COLS, "coef": reg.coef_.tolist(), "intercept": float(reg.intercept_),
        "mean": mvf.tolist(), "std": svf.tolist(), "horizon_bars": H,
        "terciles": [float(lo), float(hi)],
        "pred_grid": np.quantile(preds, np.linspace(0, 1, 101)).round(6).tolist(),
        "metrics": {"oos_r2": round(float(r2_oos), 3), "oos_tercile_acc": round(float(acc_oos), 3)},
    }, open(C.MODEL_PATH.replace("model.json", "vol_model.json"), "w"), indent=1)

    print("\ntop volatility drivers (|standardised coef|):")
    for n, co in sorted(zip(VOL_COLS, reg.coef_), key=lambda t: -abs(t[1]))[:6]:
        print(f"    {n:16s} {co:+.3f}")
    print(f"\nsaved {C.MODEL_PATH} and vol_model.json")
    if a_oos < 0.55:
        print(f"\n  NOTE: direction OOS AUC {a_oos:.3f} - still a faint lean. The value added "
              "here is the VOLATILITY regime (R2 {:.2f}) + news blackout, for sizing/standing aside.".format(r2_oos or 0))


if __name__ == "__main__":
    main()
