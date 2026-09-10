"""
MACD(12,26,9) CROSSOVER entry on XAUUSD — same winner-condition analysis as the
EMA / RSI-divergence studies, but the trigger is a MACD-line / signal-line
cross. This is a WITH-momentum entry (not a fade).

Signal (leak-free):
  * macd = EMA12 - EMA26 ; signal = EMA9(macd).
  * BULLISH cross at bar i: macd[i] > signal[i] and macd[i-1] <= signal[i-1] -> LONG.
  * BEARISH cross: macd[i] < signal[i] and macd[i-1] >= signal[i-1]         -> SHORT.
  * Entry = bar i+1 open (entry_lag always 1).
  * Risk R = atr_mult * ATR(14). Stop entry -/+ R. Targets +2R / +3R.

MACD-specific features added: macd_at_cross (level vs zero line), macd_abs,
macd_slope (3-bar), hist_slope, bars_since_prev_cross, cross_above_zero.

Usage:  python -m research.macd_cross_winner_analysis [5min|15min|30min|1h] [1:2|1:3] [atr_mult]
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from research.ema5_winner_analysis import (
    _ema, _rsi, _atr, _adx, _htf_context, FEATURES,
    PIP, CONTRACT, COMMISSION_RT_PER_LOT, SLIP_TICKS, TICK, LOT,
)
from research.rsi_div_winner_analysis import analyze

MAX_HOLD = 288
ATR_MULT = 1.0
MIN_R_PIPS = 5.0

MACD_FEATURES = FEATURES + ["macd_at_cross", "macd_abs", "macd_slope",
                            "hist_slope", "bars_since_prev_cross", "cross_above_zero"]


def build_macd(df: pd.DataFrame, atr_mult=ATR_MULT) -> pd.DataFrame:
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
    macd = _ema(cl, 12) - _ema(cl, 26); sigl = _ema(macd, 9); macd_hist = macd - sigl
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

    d = macd - sigl
    bull = (d > 0) & (np.roll(d, 1) <= 0)
    bear = (d < 0) & (np.roll(d, 1) >= 0)
    bull[0] = bear[0] = False
    cross_idx = np.where(bull | bear)[0]
    prev_cross = {}
    last = None
    for c in cross_idx:
        prev_cross[c] = last
        last = c

    htf = _htf_context(df)
    rows = []
    for i in cross_idx:
        if i < 250 or i + 2 >= n or np.isnan(atr[i]) or atr[i] <= 0 or np.isnan(atr_pct[i]):
            continue
        side = 1 if bull[i] else -1
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
        pc = prev_cross.get(i)
        rows.append(dict(
            ts=ts[i], side=side, entry_lag=1, hour=ts[i].hour, dow=ts[i].dayofweek,
            session=("asia" if ts[i].hour < 7 else "london" if ts[i].hour < 12
                     else "ny_am" if ts[i].hour < 17 else "ny_pm"),
            R_pips=R / PIP,
            macd_at_cross=macd[i] / atr[i],
            macd_abs=abs(macd[i]) / atr[i],
            macd_slope=(macd[i] - macd[i - 3]) / atr[i],
            hist_slope=(macd_hist[i] - macd_hist[i - 3]) / atr[i],
            bars_since_prev_cross=(i - pc) if pc is not None else 999,
            cross_above_zero=float((side > 0 and macd[i] > 0) or (side < 0 and macd[i] < 0)),
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


def main(tf="5min", primary="win_3r", atr_mult=ATR_MULT):
    global MAX_HOLD
    MAX_HOLD = 120 if tf == "1h" else int(round(24 * 60 / {"5min": 5, "15min": 15,
                                                            "30min": 30, "1h": 60}[tf]))
    print(f"### MACD-crossover entry   tf={tf}   R={atr_mult}xATR   MAX_HOLD={MAX_HOLD}   "
          f"primary={primary}")
    tr = build_macd(load_bars(tf, split="in_sample"), atr_mult)
    te = build_macd(load_bars(tf, split="walk_forward"), atr_mult)
    tr["split"] = "in_sample"; te["split"] = "walk_forward"
    analyze(tr, te, primary, feats=MACD_FEATURES)
    tag = tf.replace("min", "m")
    tr.to_csv(f"research/macd_cross_train_{tag}.csv", index=False)
    te.to_csv(f"research/macd_cross_test_{tag}.csv", index=False)
    print(f"\nsaved research/macd_cross_train_{tag}.csv , research/macd_cross_test_{tag}.csv")


if __name__ == "__main__":
    import sys
    tf = sys.argv[1] if len(sys.argv) > 1 else "5min"
    pri = sys.argv[2] if len(sys.argv) > 2 else "win_3r"
    pri = "win_2r" if pri in ("2", "1:2", "win_2r") else "win_3r"
    am = float(sys.argv[3]) if len(sys.argv) > 3 else ATR_MULT
    main(tf, pri, am)
