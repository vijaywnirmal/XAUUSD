"""
Gold Trend Continuation — Quality-Filtered   (hypothesis test, not a promise)

Structure (multi-timeframe, no-lookahead):
    4H  regime gate   : close vs EMA50, EMA50 vs EMA200, EMA50 slope, ADX(4H)
    1H  impulse        : range expansion + swing break + close in the extreme third
    15m pullback       : controlled retracement that holds structure, lower vol
    15m resumption     : break of the pullback's local high -> ENTER next 15m open
    stop               : pullback swing low  -/+ 0.2 * ATR(15m)   (structural)
    exits (compared)   : A 2R fixed | B 15m swing trail | C 1.5R partial + trail
                         D prior 4H swing extreme as target

The point is the CONDITIONAL decomposition, not the headline number:
net expectancy (R, cost included) sliced by regime strength, pull-back depth,
impulse quality, session, 15m volatility, and first-break vs confirmed entry —
so we can see WHERE any edge lives, and whether it survives 2023-24 walk-forward.

in_sample = 2009-2022, walk_forward = 2023-2024.  OOS 2024-2026 left untouched.

Usage:  python -m research.gold_trend_continuation
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message=".*timezones available for np.datetime64.*")

from data_pipeline.dataset import load_bars
from research.ema5_winner_analysis import _ema, _atr, _adx

PIP = 0.10
CONTRACT = 100.0
COMMISSION_RT_PER_LOT = 6.0
SLIP_TICKS = 1.0
TICK = 0.01
LOT = 0.01

# --- regime (4H) ---
ADX4_MIN = 20.0
SLOPE_LOOKBACK_4H = 6
# --- impulse (1H) ---
IMP_SWING_LB = 10
IMP_RANGE_ATR = 1.3
IMP_CLOSE_FRAC = 0.60
# --- pullback / entry (15m) ---
PB_MIN_RETR = 0.20
PB_MAX_RETR = 0.786
PB_MAX_BARS = 40                 # 10h on 15m
PB_LOCALHI_LB = 3               # local swing window inside the pullback
ENTRY_SCAN_BARS = 12            # look this many bars past a valid pullback for the break
# --- management ---
MAX_HOLD = 96                   # 24h on 15m
ATR_BUF = 0.20


def _htf(df15: pd.DataFrame, rule: str) -> pd.DataFrame:
    g = (df15.set_index("ts").resample(rule)
         .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
              close=("close", "last"), vol=("volume_sum", "sum")).dropna(subset=["open"]))
    o = g["open"].to_numpy(); h = g["high"].to_numpy(); l = g["low"].to_numpy(); c = g["close"].to_numpy()
    g["ema50"] = _ema(c, 50); g["ema200"] = _ema(c, 200)
    g["ema50_slope"] = g["ema50"] - pd.Series(g["ema50"].to_numpy()).shift(SLOPE_LOOKBACK_4H).to_numpy()
    g["adx"] = _adx(h, l, c, 14)
    g["atr"] = _atr(h, l, c, 14)[0]
    g["swing_hi"] = pd.Series(h).rolling(IMP_SWING_LB).max().shift(1).to_numpy()
    g["swing_lo"] = pd.Series(l).rolling(IMP_SWING_LB).min().shift(1).to_numpy()
    g["prior_hi20"] = pd.Series(h).rolling(20).max().shift(1).to_numpy()
    g["prior_lo20"] = pd.Series(l).rolling(20).min().shift(1).to_numpy()
    g["close_time"] = g.index + pd.tseries.frequencies.to_offset(rule)
    return g.reset_index().rename(columns={"ts": "bar_time"})


def _asof(df15, htf, cols, pfx):
    m = pd.merge_asof(df15[["ts"]], htf[["close_time", *cols]].sort_values("close_time"),
                      left_on="ts", right_on="close_time", direction="backward")
    return m[cols].rename(columns={c: f"{pfx}_{c}" for c in cols})


def build_trades(df15: pd.DataFrame, split: str) -> pd.DataFrame:
    df15 = df15.reset_index(drop=True)
    ts = pd.DatetimeIndex(df15["ts"])
    o = df15["open"].to_numpy(float); hi = df15["high"].to_numpy(float)
    lo = df15["low"].to_numpy(float); cl = df15["close"].to_numpy(float)
    spr = df15["spread_mean"].to_numpy(float)
    n = len(df15)
    atr15 = _atr(hi, lo, cl, 14)[0]
    atr15_pct = pd.Series(atr15).rolling(1500, min_periods=200).rank(pct=True).to_numpy()

    h1 = _htf(df15, "1h")
    h4 = _htf(df15, "4h")

    # --- 1H impulses, each tagged with the 4H regime valid at its close --------
    h1c = h1["close_time"].to_numpy()
    reg = pd.merge_asof(h1[["close_time"]], h4[["close_time", "close", "ema50", "ema200",
                                                "ema50_slope", "adx", "atr", "prior_hi20", "prior_lo20"]]
                        .rename(columns=lambda c: c if c == "close_time" else f"h4_{c}")
                        .sort_values("close_time"),
                        left_on="close_time", right_on="close_time", direction="backward")
    H = h1.join(reg.drop(columns=["close_time"]))
    bull = ((H.h4_close > H.h4_ema50) & (H.h4_ema50 > H.h4_ema200) &
            (H.h4_ema50_slope > 0) & (H.h4_adx >= ADX4_MIN))
    bear = ((H.h4_close < H.h4_ema50) & (H.h4_ema50 < H.h4_ema200) &
            (H.h4_ema50_slope < 0) & (H.h4_adx >= ADX4_MIN))
    rng = (H.high - H.low).to_numpy()
    cfrac = ((H.close - H.low) / (H.high - H.low).replace(0, np.nan)).to_numpy()
    imp_long = (bull.to_numpy() & (H.high.to_numpy() > H.swing_hi.to_numpy())
                & (rng >= IMP_RANGE_ATR * H.atr.to_numpy()) & (cfrac >= IMP_CLOSE_FRAC))
    imp_short = (bear.to_numpy() & (H.low.to_numpy() < H.swing_lo.to_numpy())
                 & (rng >= IMP_RANGE_ATR * H.atr.to_numpy()) & ((1 - cfrac) >= IMP_CLOSE_FRAC))

    trades = []
    idx15_for_time = df15["ts"].values
    for j in np.where(imp_long | imp_short)[0]:
        side = 1 if imp_long[j] else -1
        t_close = H["close_time"].iloc[j]
        imp_hi = H["high"].iloc[j]; imp_lo = H["low"].iloc[j]
        leg_lo = min(H["low"].iloc[max(0, j - 3):j + 1].min(), imp_lo)
        leg_hi = max(H["high"].iloc[max(0, j - 3):j + 1].max(), imp_hi)
        imp_range_atr = rng[j] / H["atr"].iloc[j] if H["atr"].iloc[j] else np.nan
        atr_prev = H["atr"].iloc[j - 1] if j >= 1 else np.nan
        imp_atr_exp = (H["atr"].iloc[j] / atr_prev) if atr_prev and not np.isnan(atr_prev) else np.nan
        adx4 = H["h4_adx"].iloc[j]
        dist_ema50_atr = ((H["h4_close"].iloc[j] - H["h4_ema50"].iloc[j]) * side) / H["h4_atr"].iloc[j] \
            if H["h4_atr"].iloc[j] else np.nan

        s = int(np.searchsorted(idx15_for_time, np.datetime64(t_close)))
        if s <= 0 or s >= n - 5:
            continue
        anchor_ext = imp_hi if side > 0 else imp_lo
        pull_ext = anchor_ext
        got_pullback = False
        entered = False
        k = s
        ext_moves = 0                 # times the counter-move made a fresh extreme
        poke_fails = 0                # bars that pierced the local high but closed back
        max_retr = 0.0
        end = min(s + PB_MAX_BARS + ENTRY_SCAN_BARS, n - 1)
        while k < end:
            if side > 0:
                anchor_ext = max(anchor_ext, hi[k])
                if lo[k] < pull_ext:
                    pull_ext = lo[k]; ext_moves += 1
                denom = (anchor_ext - leg_lo)
                retr = (anchor_ext - pull_ext) / denom if denom > 0 else 0.0
                broke_struct = cl[k] < leg_lo
            else:
                anchor_ext = min(anchor_ext, lo[k])
                if hi[k] > pull_ext:
                    pull_ext = hi[k]; ext_moves += 1
                denom = (leg_hi - anchor_ext)
                retr = (pull_ext - anchor_ext) / denom if denom > 0 else 0.0
                broke_struct = cl[k] > leg_hi
            max_retr = max(max_retr, retr)
            if broke_struct or retr > PB_MAX_RETR or (k - s) > PB_MAX_BARS:
                break
            if not got_pullback and retr >= PB_MIN_RETR:
                got_pullback = True
                pb_start_k = k
                pb_low_at_confirm = pull_ext
            if got_pullback:
                w0 = max(pb_start_k - PB_LOCALHI_LB, s)
                local_hi = hi[w0:k].max() if k > w0 else hi[k]
                local_lo = lo[w0:k].min() if k > w0 else lo[k]
                pierced = (hi[k] > local_hi) if side > 0 else (lo[k] < local_lo)
                held = (cl[k] > local_hi) if side > 0 else (cl[k] < local_lo)
                if pierced and not held:
                    poke_fails += 1
                trig = pierced
                if trig and k + 1 < n:
                    ent_i = k + 1
                    ent_px = o[ent_i]
                    if side > 0:
                        sl = pull_ext - ATR_BUF * atr15[k]
                        R = ent_px - sl
                    else:
                        sl = pull_ext + ATR_BUF * atr15[k]
                        R = sl - ent_px
                    if R <= 0 or np.isnan(R):
                        break
                    conf_delay = k - pb_start_k
                    pb_dur = pb_start_k - s               # impulse close -> pullback confirmed
                    total_bars = k - s
                    first_break = int(conf_delay <= 2)
                    dfe = ((anchor_ext - ent_px) if side > 0 else (ent_px - anchor_ext))
                    dist_from_ext_atr = dfe / atr15[k] if atr15[k] else np.nan
                    chase_R = (((ent_px - pull_ext) if side > 0 else (pull_ext - ent_px)) / R)
                    imp_body_ratio = (abs(H["close"].iloc[j] - H["open"].iloc[j]) / rng[j]
                                      if rng[j] else np.nan)
                    sess = ("asia" if ts[ent_i].hour < 7 else "london" if ts[ent_i].hour < 12
                            else "ny_am" if ts[ent_i].hour < 17 else "ny_pm")
                    overlap = int(12 <= ts[ent_i].hour < 16)
                    prior_tgt = (H["h4_prior_hi20"].iloc[j] if side > 0 else H["h4_prior_lo20"].iloc[j])

                    ex = _walk_exits(side, ent_i, ent_px, sl, R, o, hi, lo, cl, atr15, prior_tgt, n)
                    rc = _cost_r(LOT, spr[ent_i], spr[ex["A_exit_i"]], R)
                    trades.append(dict(
                        ts=ts[ent_i], side=side, split=split, year=ts[ent_i].year,
                        retr=round(retr, 3), max_retr=round(max_retr, 3),
                        retr_bucket=str(pd.cut([retr], [0, .38, .5, .618, .786, 9],
                                               labels=["<38", "38-50", "50-62", "62-79", "79+"])[0]),
                        adx4=round(adx4, 1),
                        adx4_bucket=str(pd.cut([adx4], [0, 22, 27, 35, 100],
                                               labels=["20-22", "22-27", "27-35", "35+"])[0]),
                        dist_ema50_atr=round(dist_ema50_atr, 3),
                        imp_range_atr=round(imp_range_atr, 3), imp_atr_exp=round(imp_atr_exp, 3),
                        imp_body_ratio=round(imp_body_ratio, 3),
                        atr15_pct=round(atr15_pct[ent_i], 3),
                        atr15_bucket=("low" if atr15_pct[ent_i] < .33 else "mid" if atr15_pct[ent_i] < .66 else "high"),
                        session=sess, overlap=overlap,
                        first_break=first_break, conf_delay=conf_delay,
                        conf_bucket=("0" if conf_delay == 0 else "1-2" if conf_delay <= 2
                                     else "3-5" if conf_delay <= 5 else "6-10" if conf_delay <= 10 else "11+"),
                        pb_dur=pb_dur, total_bars=total_bars,
                        pb_dur_bucket=("1-2" if pb_dur <= 2 else "3-5" if pb_dur <= 5
                                       else "6-10" if pb_dur <= 10 else "11+"),
                        ext_moves=ext_moves, poke_fails=poke_fails,
                        dist_from_ext_atr=round(dist_from_ext_atr, 3), chase_R=round(chase_R, 3),
                        R_usd=round(R * LOT * CONTRACT, 3), cost_r=round(rc, 3),
                        mae_R=ex["mae_R"], mfe_R=ex["mfe_R"],
                        **{f"{e}_R": ex[f"{e}_R"] for e in "ABCD"},
                        **{f"{e}_net": round(ex[f"{e}_R"] - rc, 3) for e in "ABCD"},
                    ))
                    entered = True
                    break
            k += 1
        _ = entered
    return pd.DataFrame(trades)


def _cost_r(lots, spr_e, spr_x, R):
    usd = (((spr_e / 2 + spr_x / 2) + 2 * SLIP_TICKS * TICK) * lots * CONTRACT
           + COMMISSION_RT_PER_LOT * lots)
    return usd / (R * lots * CONTRACT)


def _walk_exits(side, ent_i, ent_px, sl, R, o, hi, lo, cl, atr15, prior_tgt, n):
    """A: 2R fixed. B: trail on 15m swing (close beyond 3-bar extreme). C: 1.5R
    partial then trail. D: prior 4H 20-bar extreme as target."""
    out = {}
    # A -- 2R  (+ MAE / MFE over the hold)
    tgt = ent_px + side * 2 * R
    xi, r = min(ent_i + MAX_HOLD, n - 1), None
    mae = mfe = 0.0
    for k in range(ent_i, min(ent_i + MAX_HOLD, n)):
        mae = max(mae, (ent_px - lo[k]) if side > 0 else (hi[k] - ent_px))
        mfe = max(mfe, (hi[k] - ent_px) if side > 0 else (ent_px - lo[k]))
        if (lo[k] <= sl) if side > 0 else (hi[k] >= sl):
            xi, r = k, -1.0; break
        if (hi[k] >= tgt) if side > 0 else (lo[k] <= tgt):
            xi, r = k, 2.0; break
    if r is None:
        r = side * (cl[xi] - ent_px) / R
    out["A_R"] = round(r, 3); out["A_exit_i"] = xi
    out["mae_R"] = round(mae / R, 3); out["mfe_R"] = round(mfe / R, 3)
    # B -- swing trail
    stop = sl; xi, r = min(ent_i + MAX_HOLD, n - 1), None
    for k in range(ent_i, min(ent_i + MAX_HOLD, n)):
        if (lo[k] <= stop) if side > 0 else (hi[k] >= stop):
            xi, r = k, side * (stop - ent_px) / R; break
        if k >= ent_i + 3:
            sw = (lo[k - 3:k].min() - ATR_BUF * atr15[k]) if side > 0 else (hi[k - 3:k].max() + ATR_BUF * atr15[k])
            stop = max(stop, sw) if side > 0 else min(stop, sw)
    if r is None:
        r = side * (cl[xi] - ent_px) / R
    out["B_R"] = round(r, 3)
    # C -- 1.5R partial + trail remainder
    half_tgt = ent_px + side * 1.5 * R
    stop = sl; took = False; realized = 0.0; xi, r = min(ent_i + MAX_HOLD, n - 1), None
    for k in range(ent_i, min(ent_i + MAX_HOLD, n)):
        if not took and ((hi[k] >= half_tgt) if side > 0 else (lo[k] <= half_tgt)):
            took = True; realized += 0.5 * 1.5; stop = max(stop, ent_px) if side > 0 else min(stop, ent_px)
        if (lo[k] <= stop) if side > 0 else (hi[k] >= stop):
            xi = k; rem = 0.5 if took else 1.0
            r = realized + rem * side * (stop - ent_px) / R; break
        if took and k >= ent_i + 3:
            sw = (lo[k - 3:k].min() - ATR_BUF * atr15[k]) if side > 0 else (hi[k - 3:k].max() + ATR_BUF * atr15[k])
            stop = max(stop, sw) if side > 0 else min(stop, sw)
    if r is None:
        rem = 0.5 if took else 1.0
        r = realized + rem * side * (cl[xi] - ent_px) / R
    out["C_R"] = round(r, 3)
    # D -- prior 4H extreme target
    xi, r = min(ent_i + MAX_HOLD, n - 1), None
    if prior_tgt is None or np.isnan(prior_tgt) or (side * (prior_tgt - ent_px) <= 0):
        r = out["A_R"]                      # no valid target -> fall back to 2R
    else:
        for k in range(ent_i, min(ent_i + MAX_HOLD, n)):
            if (lo[k] <= sl) if side > 0 else (hi[k] >= sl):
                xi, r = k, -1.0; break
            if (hi[k] >= prior_tgt) if side > 0 else (lo[k] <= prior_tgt):
                xi, r = k, side * (prior_tgt - ent_px) / R; break
        if r is None:
            r = side * (cl[xi] - ent_px) / R
    out["D_R"] = round(r, 3)
    return out


def _tab(d, col, exit_key="B"):
    g = d.groupby(col, observed=True).agg(
        n=("side", "size"), hit=(f"{exit_key}_R", lambda x: (x > 0).mean()),
        net_R=(f"{exit_key}_net", "mean"), gross_R=(f"{exit_key}_R", "mean"))
    return g.round(3)


def report(d: pd.DataFrame, tag: str):
    print(f"\n######################  {tag}  —  {len(d)} trades  ######################")
    if len(d) == 0:
        return
    print(f"exit model            hit    gross R    NET R      (avg cost {d['cost_r'].mean():.3f}R)")
    for e, name in [("A", "2R fixed"), ("B", "15m swing trail"), ("C", "1.5R partial+trail"),
                    ("D", "prior-4H target")]:
        print(f"  {name:20s} {(d[f'{e}_R']>0).mean():.3f}   {d[f'{e}_R'].mean():+.3f}   "
              f"{d[f'{e}_net'].mean():+.3f}")
    print("\n-- NET R by condition (exit B = 15m swing trail) --")
    for col in ["retr_bucket", "adx4_bucket", "atr15_bucket", "session", "overlap", "first_break"]:
        print(f"\n[{col}]"); print(_tab(d, col).to_string())
    print("\n-- edge in entry vs exit? mean NET R per exit, best condition slice --")
    strong = d[(d.adx4_bucket.isin(["27-35", "35+"])) & (d.retr_bucket.isin(["38-50", "50-62"]))
               & (d.session.isin(["london", "ny_am"]))]
    print(f"strong-regime + medium pullback + London/NY  (n={len(strong)}):")
    for e in "ABCD":
        print(f"  exit {e}: gross {strong[f'{e}_R'].mean():+.3f}R   NET {strong[f'{e}_net'].mean():+.3f}R")


def _m(sub, ex="A"):
    if len(sub) == 0:
        return dict(n=0)
    return dict(n=len(sub),
                hit=round((sub[f"{ex}_R"] > 0).mean(), 3),
                gross=round(sub[f"{ex}_R"].mean(), 3),
                net=round(sub[f"{ex}_net"].mean(), 3),
                mae=round(sub["mae_R"].mean(), 2),
                mfe=round(sub["mfe_R"].mean(), 2),
                chase=round(sub["chase_R"].mean(), 2),
                pb_dur=round(sub["pb_dur"].mean(), 1),
                ext_mv=round(sub["ext_moves"].mean(), 1),
                pokes=round(sub["poke_fails"].mean(), 2),
                retr=round(sub["retr"].mean(), 2))


def mechanism(d: pd.DataFrame):
    P = {"P1 2009-15": d[d.year <= 2015], "P2 2016-22": d[(d.year >= 2016) & (d.year <= 2022)],
         "P3 2023-24": d[d.year >= 2023]}
    print("\n" + "=" * 78)
    print("MECHANISM DISCOVERY  —  existing 1,952 trades, no new indicators  (exit A = 2R)")
    print("=" * 78)

    for col, order in [("conf_bucket", ["0", "1-2", "3-5", "6-10", "11+"]),
                       ("retr_bucket", ["<38", "38-50", "50-62", "62-79", "79+"]),
                       ("pb_dur_bucket", ["1-2", "3-5", "6-10", "11+"])]:
        print(f"\n---  by {col}  ---")
        hdr = f"{col:9s}  " + "  ".join(f"{k:>7}" for k in
              ["n", "hit", "gross", "net", "mae", "mfe", "chase", "pb_dur", "ext_mv", "pokes", "retr"])
        print(hdr)
        for b in order:
            s = d[d[col] == b]
            if len(s) < 15:
                continue
            m = _m(s)
            print(f"{b:9s}  " + "  ".join(f"{m[k]:>7}" for k in
                  ["n", "hit", "gross", "net", "mae", "mfe", "chase", "pb_dur", "ext_mv", "pokes", "retr"]))

    print("\n---  multi-period STABILITY (net R, exit A) — a real effect keeps its sign  ---")
    for col, order in [("conf_bucket", ["0", "1-2", "3-5", "6-10", "11+"]),
                       ("retr_bucket", ["<38", "38-50", "50-62", "62-79", "79+"])]:
        print(f"\n  {col:12s}  " + "  ".join(f"{k:>18}" for k in P))
        for b in order:
            cells = []
            for pn, pd_ in P.items():
                s = pd_[pd_[col] == b]
                cells.append(f"{('n='+str(len(s))):>7} {(f'{s.A_net.mean():+.3f}' if len(s) >= 10 else '   --  '):>10}")
            print(f"  {b:12s}  " + "  ".join(cells))

    print("\n---  2D map: confirmation delay x pullback depth  (net R exit A / n)  ---")
    piv = d.pivot_table(index="conf_bucket", columns="retr_bucket", values="A_net", aggfunc="mean").round(3)
    cnt = d.pivot_table(index="conf_bucket", columns="retr_bucket", values="A_net", aggfunc="size")
    piv = piv.reindex(["0", "1-2", "3-5", "6-10", "11+"]).reindex(
        columns=["<38", "38-50", "50-62", "62-79", "79+"])
    print(piv.to_string())
    print("\n  (cell counts)")
    print(cnt.reindex(["0", "1-2", "3-5", "6-10", "11+"]).reindex(
        columns=["<38", "38-50", "50-62", "62-79", "79+"]).to_string())

    print("\n---  winners vs losers (exit A):  mean state variable  ---")
    w, l = d[d.A_R > 0], d[d.A_R <= 0]
    print(f"{'variable':20s} {'winners':>10} {'losers':>10} {'w-l':>10}")
    for v in ["retr", "max_retr", "conf_delay", "pb_dur", "total_bars", "ext_moves", "poke_fails",
              "chase_R", "dist_from_ext_atr", "adx4", "imp_range_atr", "imp_atr_exp",
              "imp_body_ratio", "atr15_pct", "dist_ema50_atr", "mae_R"]:
        if v in d.columns:
            a, b = w[v].mean(), l[v].mean()
            print(f"{v:20s} {a:>10.3f} {b:>10.3f} {a-b:>+10.3f}")

    print("\n---  HYPOTHESIS 2 test: deep(>=50%) & long(>=6 bar) pullback, structure held  ---")
    h2 = d[(d.retr >= 0.50) & (d.pb_dur >= 6)]
    for pn, pd_ in {"ALL": d, **P}.items():
        s = h2[h2.index.isin(pd_.index)] if pn != "ALL" else h2
        s = pd_[(pd_.retr >= 0.50) & (pd_.pb_dur >= 6)] if pn != "ALL" else h2
        if len(s) >= 10:
            print(f"  {pn:12s} n={len(s):4d}  hitA={s.A_R.gt(0).mean():.3f}  "
                  f"grossA={s.A_R.mean():+.3f}  netA={s.A_net.mean():+.3f}  netC={s.C_net.mean():+.3f}")
        else:
            print(f"  {pn:12s} n={len(s):4d}  (thin)")


if __name__ == "__main__":
    frames = []
    for split in ("in_sample", "walk_forward"):
        d15 = load_bars("15min", split=split)
        t = build_trades(d15, split)
        frames.append(t)
    allt = pd.concat(frames, ignore_index=True)
    report(allt, "headline (all trades)")
    mechanism(allt)
    allt.to_csv("research/gold_trend_continuation_trades.csv", index=False)
    print("\nsaved research/gold_trend_continuation_trades.csv")
