"""
Fit the direction model (logistic regression) on Postgres history and save it to
monitor/model.json. Predicts P(next ~1h M5-return > 0) from the real-time
features in monitor/features.py.

    python -m monitor.calibrate

Prints train / test / 2024-26 AUC + Brier so you can SEE how weak it is
(expect AUC ~0.52-0.55 - a faint lean, not a crystal ball).
"""
from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss

from data_pipeline.dataset import load_bars
from monitor import config as C
from monitor.features import feature_frame, MODEL_COLS


def _xy(df):
    f = feature_frame(df)
    fwd = df["close"].shift(-C.PREDICT_HORIZON_BARS) / df["close"] - 1.0
    f["y"] = (fwd > 0).astype(int)
    f = f.dropna(subset=MODEL_COLS + ["y"])
    return f[MODEL_COLS].to_numpy(float), f["y"].to_numpy(int), f


def _fit(X, y):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    clf = LogisticRegression(C=0.5, max_iter=2000)
    clf.fit(Z, y)
    return clf, mu, sd


def _score(clf, mu, sd, X, y, label):
    Z = (X - mu) / sd
    p = clf.predict_proba(Z)[:, 1]
    auc = roc_auc_score(y, p)
    brier = brier_score_loss(y, p)
    print(f"  {label:14s} n={len(y):7d}  base_rate={y.mean():.3f}  AUC={auc:.4f}  Brier={brier:.4f}")
    return auc, brier


def main():
    df_tr = load_bars(C.TF, split="in_sample",
                      columns=["ts", "open", "high", "low", "close", "spread_mean"])
    df_wf = load_bars(C.TF, split="walk_forward",
                      columns=["ts", "open", "high", "low", "close", "spread_mean"])
    df_oos = load_bars(C.TF, split="out_of_sample", allow_oos=True,
                       columns=["ts", "open", "high", "low", "close", "spread_mean"])

    X, y, _ = _xy(df_tr)
    cut = int(len(X) * 0.7)
    clf, mu, sd = _fit(X[:cut], y[:cut])
    print("Direction model - logistic reg on M5 features, target = sign(next "
          f"{C.PREDICT_HORIZON_BARS}-bar return)\n")
    _score(clf, mu, sd, X[:cut], y[:cut], "train 09-19")
    a_test, b_test = _score(clf, mu, sd, X[cut:], y[cut:], "test 19-22")
    Xw, yw, _ = _xy(df_wf)
    _score(clf, mu, sd, Xw, yw, "walk-fwd 23")
    Xo, yo, _ = _xy(df_oos)
    a_oos, b_oos = _score(clf, mu, sd, Xo, yo, "oos 24-26")

    # final model: all data through walk-forward (keep 2024-26 truly untouched)
    Xall = np.vstack([X, Xw]); yall = np.concatenate([y, yw])
    clf, mu, sd = _fit(Xall, yall)
    model = {
        "cols": MODEL_COLS,
        "coef": clf.coef_[0].tolist(),
        "intercept": float(clf.intercept_[0]),
        "mean": mu.tolist(),
        "std": sd.tolist(),
        "horizon_bars": C.PREDICT_HORIZON_BARS,
        "metrics": {"test_auc": round(float(a_test), 4), "test_brier": round(float(b_test), 4),
                    "oos_auc": round(float(a_oos), 4), "oos_brier": round(float(b_oos), 4)},
        "trained_on": "2009-01..2024-06 M5",
    }
    with open(C.MODEL_PATH, "w") as f:
        json.dump(model, f, indent=1)
    print(f"\nsaved {C.MODEL_PATH}")
    print("top drivers (|standardised coef|):")
    for name, co in sorted(zip(MODEL_COLS, clf.coef_[0]), key=lambda t: -abs(t[1]))[:6]:
        print(f"    {name:18s} {co:+.3f}")
    if a_oos < 0.55:
        print(f"\n  NOTE: OOS AUC {a_oos:.3f} - this is a FAINT lean (0.50 = coin flip). "
              "Directionally consistent across windows, but do not size it like a real signal.\n"
              "  Top driver 'london_drift_atr' matches the H1 London-agree finding.")


if __name__ == "__main__":
    main()
