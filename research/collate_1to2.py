"""
Re-score every entry we tested at RR 1:2 (target = 2R) instead of 1:3.

Nothing is re-simulated: each winner-analysis run already stored win_2r /
net_r_2 alongside win_3r, so this just reloads the saved train/test CSVs, refits
the same HistGBM on the win_2r label, and reports the 1:2 base rate, the
walk-forward P(win) AUC, the best-quintile numbers, and (for Donchian) the
volume + ATR-expansion filter -- all on the untouched 2023-24 walk-forward set.

Usage:  python -m research.collate_1to2
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from research.ema5_winner_analysis import FEATURES as BASE_FEATS

ENTRIES = [
    ("EMA-5 detach",        "ema5_winner_train.csv",          "ema5_winner_test.csv",          []),
    ("EMA-9 detach",        "ema5_winner_train_5m_ema9.csv",  "ema5_winner_test_5m_ema9.csv",  []),
    ("EMA-21 detach",       "ema5_winner_train_5m_ema21.csv", "ema5_winner_test_5m_ema21.csv", []),
    ("RSI divergence",      "rsi_div_train_5m_L5.csv",        "rsi_div_test_5m_L5.csv",
        ["div_pivot_gap", "div_rsi_drop", "div_px_move"]),
    ("MACD crossover",      "macd_cross_train_5m.csv",        "macd_cross_test_5m.csv",
        ["macd_at_cross", "macd_abs", "macd_slope", "hist_slope", "bars_since_prev_cross", "cross_above_zero"]),
    ("Stochastic crossover","stoch_cross_train_5m.csv",       "stoch_cross_test_5m.csv",
        ["stoch_k", "stoch_d", "stoch_in_zone", "stoch_dist_50", "k_slope", "bars_since_prev_cross"]),
    ("Bollinger bounce",    "bb_bounce_train_5m.csv",         "bb_bounce_test_5m.csv",
        ["bb_pierce_atr", "bb_pct_b", "bb_close_vs_mid_atr", "bb_width_now", "bb_reentry_body", "bars_since_prev_touch"]),
    ("Donchian breakout",   "donchian_train_5m.csv",          "donchian_test_5m.csv",
        ["dc_width_atr", "breakout_ext_atr", "bars_since_new_extreme", "dc_slope_atr", "pos_in_dc_prev", "range_traversed_atr"]),
]

BE2 = 1 / 3          # 1:2 gross breakeven
D = "research/"


def score(name, ftr, fte, extra):
    tr = pd.read_csv(D + ftr); te = pd.read_csv(D + fte)
    feats = [c for c in (BASE_FEATS + extra) if c in tr.columns]
    Xtr = tr[feats].apply(pd.to_numeric, errors="coerce")
    Xte = te[feats].apply(pd.to_numeric, errors="coerce")
    ytr, yte = tr["win_2r"].to_numpy(), te["win_2r"].to_numpy()
    clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.03, max_iter=400,
                                         l2_regularization=1.0, min_samples_leaf=200,
                                         random_state=0, validation_fraction=0.15,
                                         n_iter_no_change=30)
    clf.fit(Xtr, ytr)
    p = clf.predict_proba(Xte)[:, 1]
    auc = roc_auc_score(yte, p)
    te = te.assign(p=p)
    q = pd.qcut(te["p"], 5, labels=False, duplicates="drop")
    top = te[q == q.max()]
    return dict(
        entry=name,
        is_base=round(tr["win_2r"].mean(), 3),
        wf_base=round(te["win_2r"].mean(), 3),
        wf_n=len(te),
        wf_auc=round(auc, 3),
        wf_all_net=round(te["net_r_2"].mean(), 3),
        top_hit=round(top["win_2r"].mean(), 3),
        top_net=round(top["net_r_2"].mean(), 3),
        top_n=len(top),
    )


def donchian_filters():
    tr = pd.read_csv(D + "donchian_train_5m.csv"); te = pd.read_csv(D + "donchian_test_5m.csv")
    F = {
        "no filter": lambda d: np.ones(len(d), bool),
        "ADX>=25": lambda d: d.adx >= 25,
        "ADX>=30": lambda d: d.adx >= 30,
        "vol_z>=1": lambda d: d.vol_z >= 1,
        "vol_z>=2": lambda d: d.vol_z >= 2,
        "ATR_exp>=1.2": lambda d: d.atr_fast_slow >= 1.2,
        "vol_z>=1 & ATR_exp>=1.2": lambda d: (d.vol_z >= 1) & (d.atr_fast_slow >= 1.2),
        "vol_z>=1 & atr_pct>=0.6": lambda d: (d.vol_z >= 1) & (d.atr_pct >= 0.6),
        "vol_z>=2 & ATR_exp>=1.2": lambda d: (d.vol_z >= 2) & (d.atr_fast_slow >= 1.2),
        "RSI>=55 & ADX>=25": lambda d: np.where(d.side > 0, d.rsi14 >= 55, d.rsi14 <= 45) & (d.adx >= 25),
    }
    print("\n================  Donchian breakout @ 1:2 — filter stack  ================")
    print(f"{'filter':26s} | {'IS n':>7} {'IS hit':>7} {'IS net':>8} | {'WF n':>6} {'WF hit':>7} {'WF net':>8}")
    for nm, f in F.items():
        mi, mo = f(tr), f(te)
        if mo.sum() < 30:
            print(f"{nm:26s} | thin"); continue
        print(f"{nm:26s} | {mi.sum():7d} {tr.loc[mi,'win_2r'].mean():7.3f} {tr.loc[mi,'net_r_2'].mean():+8.3f} | "
              f"{mo.sum():6d} {te.loc[mo,'win_2r'].mean():7.3f} {te.loc[mo,'net_r_2'].mean():+8.3f}")


if __name__ == "__main__":
    rows = []
    for name, a, b, extra in ENTRIES:
        try:
            rows.append(score(name, a, b, extra))
        except FileNotFoundError as e:
            print(f"skip {name}: {e}")
    r = pd.DataFrame(rows)
    print(f"\n================  ALL ENTRIES @ RR 1:2  (gross breakeven {BE2:.3f})  ================")
    print("walk-forward = 2023-2024, untouched\n")
    print(r.to_string(index=False))
    print("\nis_base/wf_base = 1:2 hit rate (no filter);  wf_auc = model P(win) AUC out-of-sample")
    print("top_* = highest model-P(win) quintile on walk-forward;  net in R, cost included")
    donchian_filters()
