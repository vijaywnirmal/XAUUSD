"""
5-EMA (Pani) fade on 5-min XAUUSD — what separates the WINNERS?

Approach (leak-free):
  1. Generate every mechanical Pani detach signal (same rules as
     research/ema5_1to3_conditions.py).
  2. At the signal bar, snapshot a wide feature set — momentum, volatility,
     trend/structure, candle shape, VOLUME (tick_count + volume_sum), session,
     spread microstructure, and 1-hour higher-timeframe context. All features
     use only information available at signal-bar close.
  3. Forward-walk to the 1:3 (and 1:2) outcome.
  4. FIT on in_sample (2009-2022) ONLY:
        - univariate winner-vs-loser separation + per-feature AUC
        - HistGradientBoosting P(win) model + permutation importance
        - a hand rule from the top features
  5. APPLY the frozen model / rule to walk_forward (2023-2024) and report the
     OOS hit-rate, coverage and NET expectancy by P(win) bucket.
     OOS 2024-2026 is left untouched (touch-once guard) — it is the final gate
     only if walk_forward clears.

Usage:  python -m research.ema5_winner_analysis
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars

PIP = 0.10
CONTRACT = 100.0
COMMISSION_RT_PER_LOT = 6.0
SLIP_TICKS = 1.0
TICK = 0.01
LOT = 0.01
MIN_R_PIPS = 5.0
ENTRY_VALID = 3
MAX_HOLD = 288          # ~24h; reset per-timeframe in main()
_TF_MIN = {"5min": 5, "15min": 15, "30min": 30, "1h": 60}
EMA_LEN = 5
SIG_EMA = 5              # detach/signal EMA length; override via CLI arg 3


def _ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def _rsi(x, n=14):
    d = np.diff(x, prepend=x[0])
    up = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean()
    dn = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50).to_numpy()


def _atr(hi, lo, cl, n=14):
    tr = np.maximum(hi - lo, np.maximum(np.abs(hi - np.roll(cl, 1)),
                                        np.abs(lo - np.roll(cl, 1))))
    tr[0] = hi[0] - lo[0]
    return pd.Series(tr).rolling(n).mean().to_numpy(), tr


def _adx(hi, lo, cl, n=14):
    up = hi - np.roll(hi, 1)
    dn = np.roll(lo, 1) - lo
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    _, tr = _atr(hi, lo, cl, n)
    atr = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(plus).ewm(alpha=1 / n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean().fillna(0).to_numpy()


def _htf_context(df):
    """1-hour features, shifted so a 5-min bar only sees the last CLOSED 1h bar."""
    g = (df.set_index("ts").resample("1h")
         .agg(open=("open", "first"), high=("high", "max"),
              low=("low", "min"), close=("close", "last"),
              vol=("volume_sum", "sum")).dropna())
    c = g["close"].to_numpy()
    g["h1_ema20_slope"] = (_ema(c, 20) - np.roll(_ema(c, 20), 3)) / PIP
    g["h1_rsi"] = _rsi(c, 14)
    g["h1_ret6"] = g["close"].pct_change(6)
    g["h1_pos_in_20"] = ((g["close"] - g["low"].rolling(20).min()) /
                         (g["high"].rolling(20).max() - g["low"].rolling(20).min()))
    g["h1_up"] = (c > _ema(c, 50)).astype(int)
    keep = ["h1_ema20_slope", "h1_rsi", "h1_ret6", "h1_pos_in_20", "h1_up"]
    h = g[keep].shift(1)                                   # last closed 1h bar
    return h.reindex(df["ts"], method="ffill").reset_index(drop=True)


def build(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True)
    o = df["open"].to_numpy(float); hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float); cl = df["close"].to_numpy(float)
    spr = df["spread_mean"].to_numpy(float)
    tick_ct = df["tick_count"].to_numpy(float)
    vol = df["volume_sum"].to_numpy(float)
    ts = pd.DatetimeIndex(df["ts"])
    n = len(df)

    ema5 = _ema(cl, SIG_EMA); ema20 = _ema(cl, 20); ema50 = _ema(cl, 50); ema200 = _ema(cl, 200)
    atr, tr = _atr(hi, lo, cl, 14)
    atr50, _ = _atr(hi, lo, cl, 50)
    atr_pct = pd.Series(atr).rolling(2000, min_periods=250).rank(pct=True).to_numpy()
    rsi14 = _rsi(cl, 14); rsi2 = _rsi(cl, 2)
    adx = _adx(hi, lo, cl, 14)
    ema5_slope = (ema5 - np.roll(ema5, 5)) / PIP
    macd = _ema(cl, 12) - _ema(cl, 26)
    macd_hist = macd - _ema(macd, 9)
    roc12 = pd.Series(cl).pct_change(12).to_numpy()
    roc48 = pd.Series(cl).pct_change(48).to_numpy()
    bb_mid = pd.Series(cl).rolling(20).mean()
    bb_w = (2 * pd.Series(cl).rolling(20).std() / bb_mid).to_numpy()
    rng = hi - lo
    body = np.abs(cl - o)
    up_wick = hi - np.maximum(o, cl)
    dn_wick = np.minimum(o, cl) - lo
    hh20 = pd.Series(hi).rolling(20).max().to_numpy()
    ll20 = pd.Series(lo).rolling(20).min().to_numpy()
    vol_ma20 = pd.Series(vol).rolling(20).mean().to_numpy()
    vol_sd20 = pd.Series(vol).rolling(20).std().to_numpy()
    tick_ma20 = pd.Series(tick_ct).rolling(20).mean().to_numpy()
    spr_med = pd.Series(spr).rolling(500, min_periods=50).median().to_numpy()
    rv_1h = pd.Series(cl).pct_change().rolling(12).std().to_numpy()
    rv_4h = pd.Series(cl).pct_change().rolling(48).std().to_numpy()

    touch = (lo <= ema5) & (ema5 <= hi)
    short_sig = (lo > ema5) & np.roll(touch, 1)
    long_sig = (hi < ema5) & np.roll(touch, 1)
    short_sig[0] = long_sig[0] = False
    above = cl > ema5
    run = np.zeros(n, int)
    for i in range(1, n):
        run[i] = run[i - 1] + 1 if above[i] == above[i - 1] else 1

    htf = _htf_context(df)

    rows = []
    for i in np.where(short_sig | long_sig)[0]:
        if i < 250 or i + 2 >= n or np.isnan(atr[i]) or atr[i] <= 0 or np.isnan(atr_pct[i]):
            continue
        side = -1 if short_sig[i] else 1
        trig = lo[i] if side < 0 else hi[i]
        R = (hi[i] - trig) if side < 0 else (trig - lo[i])
        if R < MIN_R_PIPS * PIP:
            continue

        ent_i = ent_px = None
        for k in range(i + 1, min(i + 1 + ENTRY_VALID, n)):
            if side < 0 and lo[k] <= trig:
                ent_i, ent_px = k, min(o[k], trig); break
            if side > 0 and hi[k] >= trig:
                ent_i, ent_px = k, max(o[k], trig); break
        if ent_i is None:
            continue
        stop_px = hi[i] if side < 0 else lo[i]
        risk_usd = R * LOT * CONTRACT

        got2 = got3 = False
        exit_i, r_made, hit_stop_first = min(ent_i + MAX_HOLD, n - 1), 0.0, False
        t2 = ent_px - 2 * R if side < 0 else ent_px + 2 * R
        t3 = ent_px - 3 * R if side < 0 else ent_px + 3 * R
        for k in range(ent_i, min(ent_i + MAX_HOLD, n)):
            s_hit = (hi[k] >= stop_px) if side < 0 else (lo[k] <= stop_px)
            hi2 = (lo[k] <= t2) if side < 0 else (hi[k] >= t2)
            hi3 = (lo[k] <= t3) if side < 0 else (hi[k] >= t3)
            if s_hit and not (hi3):
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

        rows.append(dict(
            ts=ts[i], side=side, entry_lag=ent_i - i,
            hour=ts[i].hour, dow=ts[i].dayofweek,
            session=("asia" if ts[i].hour < 7 else "london" if ts[i].hour < 12
                     else "ny_am" if ts[i].hour < 17 else "ny_pm"),
            R_pips=R / PIP,
            # --- detachment / EMA structure
            detach_atr=((lo[i] - ema5[i]) if side < 0 else (ema5[i] - hi[i])) / atr[i],
            ema5_slope=ema5_slope[i],
            ema5_slope_with=float((side < 0 and ema5_slope[i] < 0) or (side > 0 and ema5_slope[i] > 0)),
            px_vs_ema20_atr=(cl[i] - ema20[i]) / atr[i],
            px_vs_ema50_atr=(cl[i] - ema50[i]) / atr[i],
            px_vs_ema200_atr=(cl[i] - ema200[i]) / atr[i],
            ema_stack_up=float(ema20[i] > ema50[i] > ema200[i]),
            trend_align=float((side < 0 and cl[i] < ema200[i]) or (side > 0 and cl[i] > ema200[i])),
            # --- momentum
            rsi14=rsi14[i], rsi2=rsi2[i],
            rsi14_extreme=float(rsi14[i] > 70 or rsi14[i] < 30),
            macd_hist_atr=macd_hist[i] / atr[i],
            roc12=roc12[i] * 100, roc48=roc48[i] * 100,
            adx=adx[i],
            # --- volatility
            atr_pips=atr[i] / PIP, atr_pct=atr_pct[i],
            atr_fast_slow=atr[i] / atr50[i] if atr50[i] else np.nan,
            bb_width=bb_w[i], rv_1h=rv_1h[i] * 1e4, rv_4h=rv_4h[i] * 1e4,
            R_vs_atr=R / atr[i],
            # --- signal candle shape
            sig_body_frac=body[i] / rng[i] if rng[i] else np.nan,
            sig_updn=float(np.sign(cl[i] - o[i])),
            sig_close_pos=(cl[i] - lo[i]) / rng[i] if rng[i] else np.nan,
            sig_range_vs_atr=rng[i] / atr[i],
            sig_upwick_frac=up_wick[i] / rng[i] if rng[i] else np.nan,
            sig_dnwick_frac=dn_wick[i] / rng[i] if rng[i] else np.nan,
            sig_against_fade=float((side < 0 and cl[i] > o[i]) or (side > 0 and cl[i] < o[i])),
            # --- structure
            run_len=run[i],
            dist_hh20_atr=(hh20[i] - cl[i]) / atr[i],
            dist_ll20_atr=(cl[i] - ll20[i]) / atr[i],
            # --- VOLUME / activity
            vol_z=(vol[i] - vol_ma20[i]) / vol_sd20[i] if vol_sd20[i] else np.nan,
            vol_ratio=vol[i] / vol_ma20[i] if vol_ma20[i] else np.nan,
            vol_3sum_ratio=(vol[i] + vol[i - 1] + vol[i - 2]) / (3 * vol_ma20[i]) if vol_ma20[i] else np.nan,
            tick_ratio=tick_ct[i] / tick_ma20[i] if tick_ma20[i] else np.nan,
            vol_rising=float(vol[i] > vol[i - 1] > vol[i - 2]),
            vol_on_sig_vs_prev=vol[i] / vol[i - 1] if vol[i - 1] else np.nan,
            # --- microstructure
            spread_pips=spr[i] / PIP,
            spread_vs_med=spr[i] / spr_med[i] if spr_med[i] else np.nan,
            # --- HTF
            **{c: htf[c].iloc[i] for c in htf.columns},
            h1_trend_with=float((side < 0 and htf["h1_up"].iloc[i] == 0)
                                or (side > 0 and htf["h1_up"].iloc[i] == 1)),
            # --- outcomes
            win_2r=int(got2 or got3), win_3r=int(got3),
            r_made=r_made, cost_r=cost_r,
            net_r_3=(3.0 - cost_r) if got3 else (-1.0 - cost_r) if hit_stop_first else (r_made - cost_r),
        ))
    out = pd.DataFrame(rows)
    out["net_r_2"] = np.where(out["win_2r"] == 1, 2.0 - out["cost_r"], -1.0 - out["cost_r"])
    return out


FEATURES = [
    "side", "entry_lag", "hour", "dow", "R_pips", "detach_atr", "ema5_slope",
    "ema5_slope_with", "px_vs_ema20_atr", "px_vs_ema50_atr", "px_vs_ema200_atr",
    "ema_stack_up", "trend_align", "rsi14", "rsi2", "rsi14_extreme",
    "macd_hist_atr", "roc12", "roc48", "adx", "atr_pips", "atr_pct",
    "atr_fast_slow", "bb_width", "rv_1h", "rv_4h", "R_vs_atr", "sig_body_frac",
    "sig_updn" if False else "sig_updn", "sig_close_pos", "sig_range_vs_atr",
    "sig_upwick_frac", "sig_dnwick_frac", "sig_against_fade", "run_len",
    "dist_hh20_atr", "dist_ll20_atr", "vol_z", "vol_ratio", "vol_3sum_ratio",
    "tick_ratio", "vol_rising", "vol_on_sig_vs_prev", "spread_pips",
    "spread_vs_med", "h1_ema20_slope", "h1_rsi", "h1_ret6", "h1_pos_in_20",
    "h1_up", "h1_trend_with",
]
FEATURES = [f for f in dict.fromkeys(FEATURES) if f != "sig_updn"] + ["sig_updn"]


def univariate(tr: pd.DataFrame, label="win_3r"):
    from sklearn.metrics import roc_auc_score
    rows = []
    y = tr[label].to_numpy()
    for f in FEATURES:
        x = pd.to_numeric(tr[f], errors="coerce")
        m = x.notna()
        if m.sum() < 500 or x[m].nunique() < 3:
            continue
        try:
            auc = roc_auc_score(y[m], x[m])
        except ValueError:
            continue
        w = x[m][y[m] == 1].mean()
        l = x[m][y[m] == 0].mean()
        rows.append((f, auc, w, l, w - l))
    d = pd.DataFrame(rows, columns=["feature", "auc", "mean_win", "mean_loss", "diff"])
    d["auc_edge"] = (d["auc"] - 0.5).abs()
    return d.sort_values("auc_edge", ascending=False).round(4)


def main(tf="5min", primary="win_3r"):
    global MAX_HOLD
    # ~24h horizon on intraday TFs; give the 1h chart ~5 trading days so a
    # 2-3R target (R = whole 1h candle range) has room to resolve.
    MAX_HOLD = 120 if tf == "1h" else int(round(24 * 60 / _TF_MIN[tf]))
    pri_rr = 3 if primary == "win_3r" else 2
    pri_net = "net_r_3" if primary == "win_3r" else "net_r_2"
    print(f"### timeframe {tf}   signal EMA={SIG_EMA}   MAX_HOLD={MAX_HOLD} bars   "
          f"PRIMARY label={primary} (1:{pri_rr})")
    tr = build(load_bars(tf, split="in_sample"))
    te = build(load_bars(tf, split="walk_forward"))
    tr["split"] = "in_sample"; te["split"] = "walk_forward"
    print(f"in_sample signals {len(tr):,}   walk_forward signals {len(te):,}")
    base_tr, base_te = tr["win_3r"].mean(), te["win_3r"].mean()
    print(f"1:3 base rate   in_sample {base_tr:.3f}   walk_forward {base_te:.3f}")
    print(f"1:2 base rate   in_sample {tr['win_2r'].mean():.3f}   walk_forward {te['win_2r'].mean():.3f}")

    other = "win_2r" if primary == "win_3r" else "win_3r"
    print(f"\n================  UNIVARIATE separation (in_sample, label={primary})  ================")
    u = univariate(tr, primary)
    print(u.head(25).to_string(index=False))
    print(f"\n(univariate, label={other}) top 12")
    print(univariate(tr, other).head(12).to_string(index=False))

    # ---- model: HistGBM fit on in_sample, scored on walk_forward -----------
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import roc_auc_score

    Xtr = tr[FEATURES].apply(pd.to_numeric, errors="coerce")
    Xte = te[FEATURES].apply(pd.to_numeric, errors="coerce")
    _order = ([("win_2r", "net_r_2", 2), ("win_3r", "net_r_3", 3)]
              if primary == "win_2r" else
              [("win_3r", "net_r_3", 3), ("win_2r", "net_r_2", 2)])
    for lbl, netcol, rr in _order:
        ytr, yte = tr[lbl].to_numpy(), te[lbl].to_numpy()
        clf = HistGradientBoostingClassifier(
            max_depth=3, learning_rate=0.03, max_iter=400,
            l2_regularization=1.0, min_samples_leaf=200, random_state=0,
            validation_fraction=0.15, n_iter_no_change=30)
        clf.fit(Xtr, ytr)
        p_tr = clf.predict_proba(Xtr)[:, 1]
        p_te = clf.predict_proba(Xte)[:, 1]
        auc_tr = roc_auc_score(ytr, p_tr)
        auc_te = roc_auc_score(yte, p_te)
        print(f"\n================  MODEL  label={lbl}  (RR 1:{rr})  ================")
        print(f"P(win) AUC   in_sample {auc_tr:.4f}   walk_forward {auc_te:.4f}   "
              f"(0.50 = useless)")

        te2 = te.copy(); te2["p"] = p_te
        te2["q"] = pd.qcut(te2["p"], 5, labels=[1, 2, 3, 4, 5], duplicates="drop")
        g = te2.groupby("q", observed=True).agg(
            n=(lbl, "size"), hit=(lbl, "mean"),
            exp_net_R=(netcol, "mean"), avg_p=("p", "mean")).round(3)
        be = 1 / (rr + 1)
        print(f"walk_forward by P(win) quintile   (1:{rr} gross breakeven {be:.3f}, "
              f"base {yte.mean():.3f}):")
        print(g.to_string())

        for thr in (0.5, 0.6, 0.7):
            sel = te2[te2["p"] >= thr]
            if len(sel) >= 30:
                print(f"  P>={thr}:  n={len(sel):4d}  cov={len(sel)/len(te2):.2f}  "
                      f"hit={sel[lbl].mean():.3f}  exp_net={sel[netcol].mean():+.3f}R")

        imp = permutation_importance(clf, Xte, yte, n_repeats=6, random_state=0,
                                     scoring="roc_auc")
        ii = (pd.DataFrame({"feature": FEATURES, "imp": imp.importances_mean})
              .sort_values("imp", ascending=False).head(15).round(4))
        print("permutation importance (walk_forward, top 15):")
        print(ii.to_string(index=False))

    # ---- transparent hand rule from the strongest in_sample features ------
    print("\n================  HAND RULE (fit on in_sample, tested on walk_forward)  ================")
    top = u.head(6)["feature"].tolist()
    print("built from:", top)
    def apply_rule(d):
        c = pd.Series(True, index=d.index)
        for f in top:
            x = pd.to_numeric(d[f], errors="coerce")
            wlo = tr.loc[tr[primary] == 1, f].pipe(pd.to_numeric, errors="coerce").median()
            wmid = pd.to_numeric(tr[f], errors="coerce").median()
            # keep the half that the winners lean toward
            c &= (x >= wmid) if wlo >= wmid else (x <= wmid)
        return c
    for name, d in [("in_sample", tr), ("walk_forward", te)]:
        m = apply_rule(d)
        print(f"  {name:13s} kept {m.sum():5d}/{len(d):5d} ({m.mean():.2f})  "
              f"hit={d.loc[m, primary].mean():.3f} (base {d[primary].mean():.3f})  "
              f"exp_net={d.loc[m, pri_net].mean():+.3f}R")

    tag = f"{tf.replace('min', 'm')}_ema{SIG_EMA}"
    tr.assign(split="in_sample").to_csv(f"research/ema5_winner_train_{tag}.csv", index=False)
    te.assign(split="walk_forward").to_csv(f"research/ema5_winner_test_{tag}.csv", index=False)
    print(f"\nsaved research/ema5_winner_train_{tag}.csv , research/ema5_winner_test_{tag}.csv")


if __name__ == "__main__":
    import sys
    tf = sys.argv[1] if len(sys.argv) > 1 else "5min"
    pri = sys.argv[2] if len(sys.argv) > 2 else "win_3r"
    if pri in ("2", "1:2", "win_2r"):
        pri = "win_2r"
    elif pri in ("3", "1:3", "win_3r"):
        pri = "win_3r"
    if len(sys.argv) > 3:
        SIG_EMA = int(sys.argv[3])
    main(tf, pri)
