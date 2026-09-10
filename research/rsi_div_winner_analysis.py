"""
RSI(14) DIVERGENCE fade on XAUUSD — same winner-condition analysis as
research/ema5_winner_analysis.py, but the entry trigger is a regular
(reversal) RSI divergence instead of a 5-EMA detach.

Signal (leak-free):
  * Swing pivots with L bars either side (L=5). A pivot at bar p is only
    CONFIRMED at bar p+L.
  * Bearish divergence -> SHORT (fade): the last two confirmed pivot HIGHS
    p1<p2 have  high[p2] > high[p1]  (higher high in price)  AND
    rsi[p2] < rsi[p1]  (lower high in RSI), with 5 <= p2-p1 <= 60 bars.
    Fires at i = p2 + L.
  * Bullish divergence -> LONG: last two confirmed pivot LOWS with
    low[p2] < low[p1]  AND  rsi[p2] > rsi[p1].
  * Entry = next bar open (market; divergence is a "take it now" signal, so
    entry_lag is always 1 here).
  * Risk R = ATR(14) at the signal bar. Stop = entry -/+ R. Targets +2R / +3R.

Everything else — the ~50-feature snapshot, the fit-on-in_sample /
test-on-walk_forward HistGBM, permutation importance, and the transparent hand
rule — is identical to the EMA study and reuses its helpers.

Usage:  python -m research.rsi_div_winner_analysis [5min|15min|30min] [1:2|1:3] [L] [atr_mult]
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from research.ema5_winner_analysis import (
    _ema, _rsi, _atr, _adx, _htf_context, FEATURES, univariate,
    PIP, CONTRACT, COMMISSION_RT_PER_LOT, SLIP_TICKS, TICK, LOT,
)

MAX_HOLD = 288
L_PIVOT = 5
ATR_MULT = 1.0
MIN_R_PIPS = 5.0
MAX_PIVOT_GAP = 60


def _pivots(x, L):
    n = len(x)
    hi_p = np.zeros(n, bool); lo_p = np.zeros(n, bool)
    for i in range(L, n - L):
        w = x[i - L:i + L + 1]
        if x[i] == w.max() and (w.argmax() == L):
            hi_p[i] = True
        if x[i] == w.min() and (w.argmin() == L):
            lo_p[i] = True
    return hi_p, lo_p


def build_div(df: pd.DataFrame, L=L_PIVOT, atr_mult=ATR_MULT) -> pd.DataFrame:
    df = df.reset_index(drop=True)
    o = df["open"].to_numpy(float); hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float); cl = df["close"].to_numpy(float)
    spr = df["spread_mean"].to_numpy(float)
    tick_ct = df["tick_count"].to_numpy(float); vol = df["volume_sum"].to_numpy(float)
    ts = pd.DatetimeIndex(df["ts"]); n = len(df)

    ema5 = _ema(cl, 5); ema20 = _ema(cl, 20); ema50 = _ema(cl, 50); ema200 = _ema(cl, 200)
    atr, tr = _atr(hi, lo, cl, 14); atr50, _ = _atr(hi, lo, cl, 50)
    atr_pct = pd.Series(atr).rolling(2000, min_periods=250).rank(pct=True).to_numpy()
    rsi14 = _rsi(cl, 14); rsi2 = _rsi(cl, 2)
    adx = _adx(hi, lo, cl, 14)
    ema5_slope = (ema5 - np.roll(ema5, 5)) / PIP
    macd = _ema(cl, 12) - _ema(cl, 26); macd_hist = macd - _ema(macd, 9)
    roc12 = pd.Series(cl).pct_change(12).to_numpy(); roc48 = pd.Series(cl).pct_change(48).to_numpy()
    bb_mid = pd.Series(cl).rolling(20).mean()
    bb_w = (2 * pd.Series(cl).rolling(20).std() / bb_mid).to_numpy()
    rng = hi - lo; body = np.abs(cl - o)
    up_wick = hi - np.maximum(o, cl); dn_wick = np.minimum(o, cl) - lo
    hh20 = pd.Series(hi).rolling(20).max().to_numpy(); ll20 = pd.Series(lo).rolling(20).min().to_numpy()
    vol_ma20 = pd.Series(vol).rolling(20).mean().to_numpy()
    vol_sd20 = pd.Series(vol).rolling(20).std().to_numpy()
    tick_ma20 = pd.Series(tick_ct).rolling(20).mean().to_numpy()
    spr_med = pd.Series(spr).rolling(500, min_periods=50).median().to_numpy()
    rv_1h = pd.Series(cl).pct_change().rolling(12).std().to_numpy()
    rv_4h = pd.Series(cl).pct_change().rolling(48).std().to_numpy()
    above = cl > ema5
    run = np.zeros(n, int)
    for i in range(1, n):
        run[i] = run[i - 1] + 1 if above[i] == above[i - 1] else 1

    hi_piv, lo_piv = _pivots(hi, L)
    lo_piv2 = _pivots(lo, L)[1]
    hi_idx = list(np.where(hi_piv)[0])
    lo_idx = list(np.where(lo_piv2)[0])

    # build (confirm_bar, side) list
    sig = []
    for a, b in zip(hi_idx, hi_idx[1:]):
        if 5 <= b - a <= MAX_PIVOT_GAP and hi[b] > hi[a] and rsi14[b] < rsi14[a]:
            sig.append((b + L, -1, a, b))
    for a, b in zip(lo_idx, lo_idx[1:]):
        if 5 <= b - a <= MAX_PIVOT_GAP and lo[b] < lo[a] and rsi14[b] > rsi14[a]:
            sig.append((b + L, +1, a, b))
    sig.sort()

    htf = _htf_context(df)
    rows = []
    for (i, side, pa, pb) in sig:
        if i < 250 or i + 2 >= n or np.isnan(atr[i]) or atr[i] <= 0 or np.isnan(atr_pct[i]):
            continue
        R = atr_mult * atr[i]
        if R < MIN_R_PIPS * PIP:
            continue
        ent_i = i + 1
        ent_px = o[ent_i]
        stop_px = ent_px + (R if side < 0 else -R)
        risk_usd = R * LOT * CONTRACT
        t2 = ent_px - 2 * R if side < 0 else ent_px + 2 * R
        t3 = ent_px - 3 * R if side < 0 else ent_px + 3 * R

        got2 = got3 = False
        exit_i, r_made, hit_stop_first = min(ent_i + MAX_HOLD, n - 1), 0.0, False
        for k in range(ent_i, min(ent_i + MAX_HOLD, n)):
            s_hit = (hi[k] >= stop_px) if side < 0 else (lo[k] <= stop_px)
            hi2 = (lo[k] <= t2) if side < 0 else (hi[k] >= t2)
            hi3 = (lo[k] <= t3) if side < 0 else (hi[k] >= t3)
            if s_hit and not hi3:
                exit_i, r_made, hit_stop_first = k, -1.0, True; break
            if hi2:
                got2 = True
            if hi3:
                got3 = True; exit_i, r_made = k, 3.0; break
        if not got3 and not hit_stop_first:
            px = cl[exit_i]
            r_made = (ent_px - px) / R if side < 0 else (px - ent_px) / R

        cost_r = (((spr[ent_i] / 2 + spr[exit_i] / 2) + 2 * SLIP_TICKS * TICK) * LOT * CONTRACT
                  + COMMISSION_RT_PER_LOT * LOT) / risk_usd
        sd = hh20[i] - ll20[i]
        rows.append(dict(
            ts=ts[i], side=side, entry_lag=1, hour=ts[i].hour, dow=ts[i].dayofweek,
            session=("asia" if ts[i].hour < 7 else "london" if ts[i].hour < 12
                     else "ny_am" if ts[i].hour < 17 else "ny_pm"),
            R_pips=R / PIP,
            div_pivot_gap=pb - pa,
            div_rsi_drop=rsi14[pa] - rsi14[pb] if side < 0 else rsi14[pb] - rsi14[pa],
            div_px_move=abs(hi[pb] - hi[pa]) / atr[i] if side < 0 else abs(lo[pb] - lo[pa]) / atr[i],
            detach_atr=((lo[i] - ema5[i]) if side < 0 else (ema5[i] - hi[i])) / atr[i],
            ema5_slope=ema5_slope[i],
            ema5_slope_with=float((side < 0 and ema5_slope[i] < 0) or (side > 0 and ema5_slope[i] > 0)),
            px_vs_ema20_atr=(cl[i] - ema20[i]) / atr[i],
            px_vs_ema50_atr=(cl[i] - ema50[i]) / atr[i],
            px_vs_ema200_atr=(cl[i] - ema200[i]) / atr[i],
            ema_stack_up=float(ema20[i] > ema50[i] > ema200[i]),
            trend_align=float((side < 0 and cl[i] < ema200[i]) or (side > 0 and cl[i] > ema200[i])),
            rsi14=rsi14[i], rsi2=rsi2[i],
            rsi14_extreme=float(rsi14[i] > 70 or rsi14[i] < 30),
            macd_hist_atr=macd_hist[i] / atr[i],
            roc12=roc12[i] * 100, roc48=roc48[i] * 100, adx=adx[i],
            atr_pips=atr[i] / PIP, atr_pct=atr_pct[i],
            atr_fast_slow=atr[i] / atr50[i] if atr50[i] else np.nan,
            bb_width=bb_w[i], rv_1h=rv_1h[i] * 1e4, rv_4h=rv_4h[i] * 1e4,
            R_vs_atr=R / atr[i],
            sig_body_frac=body[i] / rng[i] if rng[i] else np.nan,
            sig_updn=float(np.sign(cl[i] - o[i])),
            sig_close_pos=(cl[i] - lo[i]) / rng[i] if rng[i] else np.nan,
            sig_range_vs_atr=rng[i] / atr[i],
            sig_upwick_frac=up_wick[i] / rng[i] if rng[i] else np.nan,
            sig_dnwick_frac=dn_wick[i] / rng[i] if rng[i] else np.nan,
            sig_against_fade=float((side < 0 and cl[i] > o[i]) or (side > 0 and cl[i] < o[i])),
            run_len=run[i],
            dist_hh20_atr=(hh20[i] - cl[i]) / atr[i],
            dist_ll20_atr=(cl[i] - ll20[i]) / atr[i],
            vol_z=(vol[i] - vol_ma20[i]) / vol_sd20[i] if vol_sd20[i] else np.nan,
            vol_ratio=vol[i] / vol_ma20[i] if vol_ma20[i] else np.nan,
            vol_3sum_ratio=(vol[i] + vol[i - 1] + vol[i - 2]) / (3 * vol_ma20[i]) if vol_ma20[i] else np.nan,
            tick_ratio=tick_ct[i] / tick_ma20[i] if tick_ma20[i] else np.nan,
            vol_rising=float(vol[i] > vol[i - 1] > vol[i - 2]),
            vol_on_sig_vs_prev=vol[i] / vol[i - 1] if vol[i - 1] else np.nan,
            spread_pips=spr[i] / PIP,
            spread_vs_med=spr[i] / spr_med[i] if spr_med[i] else np.nan,
            **{c: htf[c].iloc[i] for c in htf.columns},
            h1_trend_with=float((side < 0 and htf["h1_up"].iloc[i] == 0)
                                or (side > 0 and htf["h1_up"].iloc[i] == 1)),
            win_2r=int(got2 or got3), win_3r=int(got3),
            r_made=r_made, cost_r=cost_r,
            net_r_3=(3.0 - cost_r) if got3 else (-1.0 - cost_r) if hit_stop_first else (r_made - cost_r),
        ))
    out = pd.DataFrame(rows)
    if len(out):
        out["net_r_2"] = np.where(out["win_2r"] == 1, 2.0 - out["cost_r"], -1.0 - out["cost_r"])
    return out


DIV_FEATURES = FEATURES + ["div_pivot_gap", "div_rsi_drop", "div_px_move"]


def analyze(tr, te, primary="win_3r", feats=None):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import roc_auc_score
    feats = list(feats) if feats is not None else DIV_FEATURES
    pri_rr = 3 if primary == "win_3r" else 2
    pri_net = "net_r_3" if primary == "win_3r" else "net_r_2"
    print(f"in_sample signals {len(tr):,}   walk_forward signals {len(te):,}")
    print(f"1:3 base rate  IS {tr['win_3r'].mean():.3f}  WF {te['win_3r'].mean():.3f}   |   "
          f"1:2 base rate  IS {tr['win_2r'].mean():.3f}  WF {te['win_2r'].mean():.3f}")

    print(f"\n===== UNIVARIATE separation (in_sample, label={primary}) =====")
    from research.ema5_winner_analysis import univariate as _uni
    globals_backup = _uni.__globals__.get("FEATURES")
    _uni.__globals__["FEATURES"] = feats
    u = _uni(tr, primary)
    print(u.head(22).to_string(index=False))

    Xtr = tr[feats].apply(pd.to_numeric, errors="coerce")
    Xte = te[feats].apply(pd.to_numeric, errors="coerce")
    for lbl, netcol, rr in ([("win_2r", "net_r_2", 2), ("win_3r", "net_r_3", 3)]
                            if primary == "win_2r" else
                            [("win_3r", "net_r_3", 3), ("win_2r", "net_r_2", 2)]):
        ytr, yte = tr[lbl].to_numpy(), te[lbl].to_numpy()
        clf = HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.03, max_iter=400, l2_regularization=1.0,
            min_samples_leaf=200, random_state=0, validation_fraction=0.15,
            n_iter_no_change=30)
        clf.fit(Xtr, ytr)
        auc_tr = roc_auc_score(ytr, clf.predict_proba(Xtr)[:, 1])
        p_te = clf.predict_proba(Xte)[:, 1]
        auc_te = roc_auc_score(yte, p_te)
        print(f"\n===== MODEL label={lbl} (RR 1:{rr}) =====")
        print(f"P(win) AUC  in_sample {auc_tr:.4f}  walk_forward {auc_te:.4f}")
        te2 = te.copy(); te2["p"] = p_te
        te2["q"] = pd.qcut(te2["p"], 5, labels=[1, 2, 3, 4, 5], duplicates="drop")
        g = te2.groupby("q", observed=True).agg(
            n=(lbl, "size"), hit=(lbl, "mean"), exp_net_R=(netcol, "mean"),
            avg_p=("p", "mean")).round(3)
        print(f"walk_forward by P(win) quintile  (1:{rr} gross breakeven {1/(rr+1):.3f}, "
              f"base {yte.mean():.3f}):")
        print(g.to_string())
        imp = permutation_importance(clf, Xte, yte, n_repeats=6, random_state=0, scoring="roc_auc")
        ii = (pd.DataFrame({"feature": feats, "imp": imp.importances_mean})
              .sort_values("imp", ascending=False).head(12).round(4))
        print("permutation importance (walk_forward, top 12):")
        print(ii.to_string(index=False))

    _uni.__globals__["FEATURES"] = globals_backup

    print("\n===== HAND RULE (fit in_sample, test walk_forward) =====")
    top = u.head(6)["feature"].tolist()
    print("built from:", top)

    def rule(d):
        c = pd.Series(True, index=d.index)
        for f in top:
            x = pd.to_numeric(d[f], errors="coerce")
            wlo = tr.loc[tr[primary] == 1, f].pipe(pd.to_numeric, errors="coerce").median()
            wmid = pd.to_numeric(tr[f], errors="coerce").median()
            c &= (x >= wmid) if wlo >= wmid else (x <= wmid)
        return c
    for name, d in [("in_sample", tr), ("walk_forward", te)]:
        m = rule(d)
        print(f"  {name:13s} kept {int(m.sum()):5d}/{len(d):5d} ({m.mean():.2f})  "
              f"hit={d.loc[m, primary].mean():.3f} (base {d[primary].mean():.3f})  "
              f"exp_net={d.loc[m, pri_net].mean():+.3f}R")


def main(tf="5min", primary="win_3r", L=L_PIVOT, atr_mult=ATR_MULT):
    global MAX_HOLD
    MAX_HOLD = 120 if tf == "1h" else int(round(24 * 60 / {"5min": 5, "15min": 15,
                                                            "30min": 30, "1h": 60}[tf]))
    print(f"### RSI-divergence entry   tf={tf}   L={L}   R={atr_mult}xATR   "
          f"MAX_HOLD={MAX_HOLD}   primary={primary}")
    tr = build_div(load_bars(tf, split="in_sample"), L, atr_mult)
    te = build_div(load_bars(tf, split="walk_forward"), L, atr_mult)
    tr["split"] = "in_sample"; te["split"] = "walk_forward"
    analyze(tr, te, primary)
    tag = f"{tf.replace('min','m')}_L{L}"
    tr.to_csv(f"research/rsi_div_train_{tag}.csv", index=False)
    te.to_csv(f"research/rsi_div_test_{tag}.csv", index=False)
    print(f"\nsaved research/rsi_div_train_{tag}.csv , research/rsi_div_test_{tag}.csv")


if __name__ == "__main__":
    import sys
    tf = sys.argv[1] if len(sys.argv) > 1 else "5min"
    pri = sys.argv[2] if len(sys.argv) > 2 else "win_3r"
    pri = "win_2r" if pri in ("2", "1:2", "win_2r") else "win_3r"
    L = int(sys.argv[3]) if len(sys.argv) > 3 else L_PIVOT
    am = float(sys.argv[4]) if len(sys.argv) > 4 else ATR_MULT
    main(tf, pri, L, am)
