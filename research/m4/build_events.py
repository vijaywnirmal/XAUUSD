"""
M4 Run 1 — step 1 of 2:  build the anchor-event / forward-fingerprint table.

Implements CONDITIONAL_RESEARCH_PROTOCOL.md v1.1 §2 (frozen state list), §2D
anchors, §3 fingerprint.  Produces one row per (anchor event, horizon) with:
  - ids: idx, ts, anchor, dir, block, session, dow, month, sigma
  - state buckets, nominal AND +1-step look-ahead-shifted: m1..m5, t1, t2, e1..e3
  - forward-path metrics at that horizon (raw, + = price up; dir carried separately)

No effects, no bootstrap, no interpretation here — that is run1.py.
Output: research/m4/events.parquet

Run:  python -m research.m4.build_events
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from research.ema5_winner_analysis import _atr
from monitor import calendar_history as CH

warnings.filterwarnings("ignore", message=".*timezones available for np.datetime64.*")
warnings.filterwarnings("ignore", category=RuntimeWarning)

HORIZONS = [2, 4, 8, 16, 32, 96]
WARM_D = 504            # trading-day warm-up for daily trailing quantiles
WARM_T1 = 200           # prior-event warm-up for T1 duration terciles
IMP_SD = 2.0            # 1h impulse threshold (frozen)
IMP_SIGWIN = 480        # trailing 1h returns for sigma_1h
A2_COOLDOWN = 16        # 15m bars (4h)
A3_LB = 96             # new 1-day extreme lookback
A3_COOLDOWN = 16
T2_CONF_AGE = 3
T2_ACTIVE = 192        # bars a confirmed level stays active (48h)
T2_WIN = 48            # failed-attempt window (12h)
T1_TIMEOUT = 96


# --------------------------------------------------------------------------- #
#  trailing-quantile bucketing (expanding window, strictly prior values)      #
# --------------------------------------------------------------------------- #
def trail_bucket(x: pd.Series, qs, warmup: int) -> pd.Series:
    cuts = [x.expanding(min_periods=warmup).quantile(q).shift(1) for q in qs]
    valid = cuts[0].notna()
    lab = np.zeros(len(x), float)
    for c in cuts:
        lab += (x.to_numpy() > c.to_numpy()).astype(float)
    out = pd.Series(np.where(valid.to_numpy(), lab, np.nan), index=x.index)
    return out


TERCILE = [1 / 3, 2 / 3]
QUINTILE = [0.2, 0.4, 0.6, 0.8]


# --------------------------------------------------------------------------- #
#  MARKET states (daily)                                                      #
# --------------------------------------------------------------------------- #
def market_states(df15: pd.DataFrame):
    d = (df15.set_index("ts").resample("1D")
         .agg(close=("close", "last")).dropna())
    c = d["close"]
    ret = c.pct_change()
    rv20 = ret.rolling(20).std()
    rv5 = ret.rolling(5).std()
    sma200 = c.rolling(200).mean()
    sig20p = ret.rolling(20).std() * c
    dz = (c - sma200) / sig20p
    sgn = np.sign(ret.fillna(0.0))

    def _ac1(s):
        a, b = s[:-1], s[1:]
        if a.std() == 0 or b.std() == 0:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])
    ac1 = sgn.rolling(40).apply(_ac1, raw=True)

    ts = (log_ratio := np.log(rv5 / rv20))
    # dollar: macro/gold_drivers.csv 'dxy' column (DXY-style USD index),
    # trailing 5-business-day % change, observation dated <= D-2.
    drv = pd.read_csv("macro/gold_drivers.csv", parse_dates=["date"]).set_index("date")
    drv.index = drv.index.tz_localize("UTC")
    cal = pd.date_range(drv.index.min(), d.index.max(), freq="D", tz="UTC")
    dxy = drv["dxy"].reindex(cal).ffill()
    usd5 = (dxy / dxy.shift(5) - 1.0).shift(2)          # shift(2) days = "<= D-2"
    usd5 = usd5.reindex(d.index, method="ffill")

    raw = pd.DataFrame({
        "m1": trail_bucket(rv20, TERCILE, WARM_D),
        "m2": trail_bucket(ts, TERCILE, WARM_D),
        "m3": trail_bucket(ac1, TERCILE, WARM_D),
        "m4": trail_bucket(dz, QUINTILE, WARM_D),
        "m5": trail_bucket(usd5, TERCILE, WARM_D),
    }, index=d.index)
    # bucket applicable DURING day D uses data through D-1  -> shift(1);
    # look-ahead-shift test uses shift(2).
    nominal = raw.shift(1)
    shifted = raw.shift(2)
    return nominal, shifted


# --------------------------------------------------------------------------- #
#  T1 — unresolved duration after a 2sigma 1h impulse                         #
# --------------------------------------------------------------------------- #
def t1_events(df15: pd.DataFrame):
    o = df15["open"].to_numpy(float); hi = df15["high"].to_numpy(float)
    lo = df15["low"].to_numpy(float); cl = df15["close"].to_numpy(float)
    ts = pd.DatetimeIndex(df15["ts"]); n = len(df15)
    # non-overlapping 1h bars: every 4 15m bars aligned to :00
    start = int(np.argmax(ts.minute.to_numpy() == 0))
    h_idx = np.arange(start, n - 4, 4)            # 15m index where each 1h bar STARTS
    h_open = o[h_idx]
    h_close = cl[h_idx + 3]
    h_ret = h_close / h_open - 1.0
    sig = pd.Series(h_ret).rolling(IMP_SIGWIN).std().to_numpy()
    imp = np.abs(h_close - h_open) / (sig * h_open) >= IMP_SD
    imp &= ~np.isnan(sig)

    events = []
    last_close_15 = -10 ** 9
    for m in np.where(imp)[0]:
        close_15 = h_idx[m] + 3                     # 15m bar that completes the impulse
        if close_15 - last_close_15 < A2_COOLDOWN:  # inherit A2 4h cooldown
            continue
        d = 1 if h_close[m] > h_open[m] else -1
        O = h_open[m]; X = h_close[m]; L = abs(X - O)
        res_idx, kind, dur = None, None, None
        # supersede check: is there a later impulse 1h bar before resolution?
        nxt_imp_15 = None
        for m2 in range(m + 1, len(h_idx)):
            if imp[m2]:
                nxt_imp_15 = h_idx[m2] + 3
                break
        for k in range(close_15 + 1, min(close_15 + T1_TIMEOUT + 1, n)):
            if nxt_imp_15 is not None and k >= nxt_imp_15:
                res_idx, kind, dur = nxt_imp_15, "superseded", nxt_imp_15 - close_15
                break
            retr = (cl[k] <= X - 0.5 * L) if d > 0 else (cl[k] >= X + 0.5 * L)
            ext = (cl[k] >= X + 0.5 * L) if d > 0 else (cl[k] <= X - 0.5 * L)
            if retr:
                res_idx, kind, dur = k, "retraced", k - close_15
                break
            if ext:
                res_idx, kind, dur = k, "extended", k - close_15
                break
        if res_idx is None:
            res_idx, kind, dur = min(close_15 + T1_TIMEOUT, n - 1), "timeout", T1_TIMEOUT
        events.append((res_idx, d, dur, O, X, kind))
        last_close_15 = close_15

    e = pd.DataFrame(events, columns=["res_idx", "dir", "duration", "origin", "imp_close", "kind"])
    if len(e) == 0:
        e["t1"] = []; e["t1_s"] = []
        return e
    dur = pd.Series(e["duration"].to_numpy(), dtype=float)
    e["t1"] = trail_bucket(dur, TERCILE, WARM_T1).to_numpy()
    e["t1_s"] = trail_bucket(dur, TERCILE, WARM_T1).shift(1).to_numpy()   # drop 1 prior event
    return e


# --------------------------------------------------------------------------- #
#  T2 — failed extreme-resolution count  (per-bar series)                     #
# --------------------------------------------------------------------------- #
def t2_series(df15: pd.DataFrame):
    hi = df15["high"].to_numpy(float); lo = df15["low"].to_numpy(float)
    cl = df15["close"].to_numpy(float); n = len(df15)
    roll_hi = pd.Series(hi).rolling(A3_LB).max().to_numpy()
    roll_lo = pd.Series(lo).rolling(A3_LB).min().to_numpy()
    is_lmax = hi >= roll_hi
    is_lmin = lo <= roll_lo
    up_j = np.where(is_lmax)[0]
    dn_j = np.where(is_lmin)[0]

    fails = np.full(n, np.nan)
    for t in range(A3_LB + T2_CONF_AGE, n):
        u = up_j[(up_j <= t - T2_CONF_AGE) & (up_j >= t - T2_ACTIVE)]
        dd = dn_j[(dn_j <= t - T2_CONF_AGE) & (dn_j >= t - T2_ACTIVE)]
        U = hi[u[-1]] if len(u) else np.nan
        D = lo[dd[-1]] if len(dd) else np.nan
        if np.isnan(U) and np.isnan(D):
            continue
        w0 = max(0, t - T2_WIN)
        f = 0
        if not np.isnan(U):
            f += int(np.sum((hi[w0:t] > U) & (cl[w0:t] <= U)))
        if not np.isnan(D):
            f += int(np.sum((lo[w0:t] < D) & (cl[w0:t] >= D)))
        fails[t] = f
    b = np.where(np.isnan(fails), np.nan, np.minimum(fails, 2.0))   # 0 / 1 / 2+
    b_s = pd.Series(b).shift(1).to_numpy()
    return b, b_s


# --------------------------------------------------------------------------- #
#  EVENT states — proximity (hours) to FOMC / NFP / CPI                       #
# --------------------------------------------------------------------------- #
def event_series(df15: pd.DataFrame):
    ts = pd.DatetimeIndex(df15["ts"])
    sched = CH.schedule()
    out = {}
    for kind, col in [("FOMC", "e1"), ("NFP", "e2"), ("CPI", "e3")]:
        w = np.sort(sched.loc[sched["kind"] == kind, "when"].values.astype("datetime64[ns]"))
        arr = ts.values.astype("datetime64[ns]")
        pos = np.searchsorted(w, arr)
        nxt = np.where(pos < len(w), w[np.clip(pos, 0, len(w) - 1)], np.datetime64("NaT"))
        prv = np.where(pos > 0, w[np.clip(pos - 1, 0, len(w) - 1)], np.datetime64("NaT"))
        d_next = (nxt - arr) / np.timedelta64(1, "h")
        d_prev = (arr - prv) / np.timedelta64(1, "h")
        delta = np.where(d_next <= d_prev, -d_next, d_prev)     # <0 before, >=0 after
        b = np.full(len(ts), np.nan)
        b[(delta >= -24) & (delta < -4)] = 0                    # PRE_24_4
        b[(delta >= -4) & (delta < 0)] = 1                      # PRE_4_0
        b[(delta >= 0) & (delta < 4)] = 2                       # POST_0_4
        out[col] = b
        out[col + "_s"] = b        # calendar is exogenous: shift test is a no-op
    return out


# --------------------------------------------------------------------------- #
#  anchors                                                                    #
# --------------------------------------------------------------------------- #
def anchors(df15: pd.DataFrame, t1e: pd.DataFrame):
    o = df15["open"].to_numpy(float); hi = df15["high"].to_numpy(float)
    lo = df15["low"].to_numpy(float); cl = df15["close"].to_numpy(float)
    ts = pd.DatetimeIndex(df15["ts"]); n = len(df15)

    A = {}
    A["A1"] = [(i, 0) for i in range(0, n, 4)]

    # A2: reuse impulse detection identical to T1
    start = int(np.argmax(ts.minute.to_numpy() == 0))
    h_idx = np.arange(start, n - 4, 4)
    h_open = o[h_idx]; h_close = cl[h_idx + 3]
    h_ret = h_close / h_open - 1.0
    sig = pd.Series(h_ret).rolling(IMP_SIGWIN).std().to_numpy()
    imp = (np.abs(h_close - h_open) / (sig * h_open) >= IMP_SD) & ~np.isnan(sig)
    a2 = []; last = -10 ** 9
    for m in np.where(imp)[0]:
        k = h_idx[m] + 3
        if k - last < A2_COOLDOWN:
            continue
        a2.append((k, 1 if h_close[m] > h_open[m] else -1)); last = k
    A["A2"] = a2

    # A3: new 96-bar extreme, per-direction cooldown
    roll_hi = pd.Series(hi).rolling(A3_LB).max().to_numpy()
    roll_lo = pd.Series(lo).rolling(A3_LB).min().to_numpy()
    a3 = []; lu = ld = -10 ** 9
    for i in range(A3_LB, n):
        if hi[i] >= roll_hi[i] and i - lu >= A3_COOLDOWN:
            a3.append((i, 1)); lu = i
        elif lo[i] <= roll_lo[i] and i - ld >= A3_COOLDOWN:
            a3.append((i, -1)); ld = i
    A["A3"] = a3

    # A4: first bar of each UTC session boundary
    h = ts.hour.to_numpy(); mn = ts.minute.to_numpy()
    a4 = [(i, 0) for i in range(n) if mn[i] == 0 and h[i] in (0, 7, 12, 17)]
    A["A4"] = a4

    # A5: bar containing a scheduled release
    sched = CH.schedule()
    rel = pd.DatetimeIndex(sched["when"]).tz_convert("UTC")
    a5 = []
    for r in rel:
        pos = ts.searchsorted(r, side="right") - 1
        if 0 <= pos < n and ts[pos] <= r < ts[pos] + pd.Timedelta("15min"):
            a5.append((int(pos), 0))
    A["A5"] = a5

    # A6: T1 resolution bars
    A["A6"] = [(int(r.res_idx), int(r.dir)) for r in t1e.itertuples()] if len(t1e) else []
    return A


# --------------------------------------------------------------------------- #
#  forward fingerprint for one event                                          #
# --------------------------------------------------------------------------- #
def fingerprint(i, s, c0, o, hi, lo, cl, n, sma_d, sess_open, origin):
    rows = []
    for H in HORIZONS:
        j0, j1 = i + 1, i + 1 + H
        if j1 > n:
            rows.append({"H": H})
            continue
        sh = hi[j0:j1]; sl = lo[j0:j1]; sc = cl[j0:j1]
        r = (sc[-1] - c0) / s
        cum_up = (np.maximum.accumulate(sh) - c0) / s
        cum_dn = (c0 - np.minimum.accumulate(sl)) / s
        mfe, mae = cum_up[-1], cum_dn[-1]
        t_mfe = int(np.argmax(sh)) + 1
        t_mae = int(np.argmin(sl)) + 1

        def _first(cum, thr):
            w = np.where(cum >= thr)[0]
            return int(w[0]) if len(w) else 10 ** 9
        races = {}
        for x, y in [(1, 1), (2, 1), (1, 2)]:
            fu, fd = _first(cum_up, x), _first(cum_dn, y)
            races[f"race_{x}_{y}"] = np.nan if fu == fd == 10 ** 9 else float(fu < fd)

        fr = np.diff(sc, prepend=c0) / c0
        pr = np.diff(cl[max(0, i - H):i + 1]) / cl[max(0, i - H):i]
        rv_ratio = (np.std(fr) / np.std(pr)) if len(pr) > 2 and np.std(pr) > 0 else np.nan

        cross_sma = np.nan
        if not np.isnan(sma_d):
            s0 = np.sign(c0 - sma_d)
            cross_sma = float(np.any(np.sign(sc - sma_d) == -s0)) if s0 != 0 else np.nan
        cross_so = float(np.any(np.sign(sc - sess_open) != np.sign(c0 - sess_open))) \
            if sess_open == sess_open else np.nan
        ret_orig = np.nan
        if origin == origin:
            ret_orig = float(np.any(sl <= origin) or np.any(sh >= origin))

        rows.append({
            "H": H, "r": r, "mfe": mfe, "mae": mae, "t_mfe": t_mfe, "t_mae": t_mae,
            "tail_up": float(r > 2), "tail_dn": float(r < -2),
            "mfe_before_mae": float(np.argmax(sh) < np.argmin(sl)),
            **races, "rv_ratio": rv_ratio,
            "cross_sma": cross_sma, "cross_sopen": cross_so, "ret_origin": ret_orig,
        })
    return rows


# --------------------------------------------------------------------------- #
def main():
    df = load_all()
    print(f"{len(df):,} 15m bars  {df['ts'].min()} .. {df['ts'].max()}")
    o = df["open"].to_numpy(float); hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float); cl = df["close"].to_numpy(float)
    ts = pd.DatetimeIndex(df["ts"]); n = len(df)
    atr = _atr(hi, lo, cl, 14)[0]
    sma20_d = (df.set_index("ts")["close"].resample("1D").last()
               .rolling(20).mean().shift(1))
    sma20_map = sma20_d.reindex(ts.floor("D")).to_numpy()
    day = ts.floor("D")
    # session-open price per bar (open of the session's first bar)
    hh = ts.hour.to_numpy()
    sess_id = np.select([hh < 7, hh < 12, hh < 17], [0, 1, 2], 3)
    sopen = np.full(n, np.nan)
    cur = -1; op = np.nan
    for i in range(n):
        key = (day[i].value, sess_id[i])
        if key != cur:
            cur = key; op = o[i]
        sopen[i] = op

    mkt_nom, mkt_shf = market_states(df)
    t1e = t1_events(df)
    print(f"T1 events: {len(t1e)}")
    t2_b, t2_bs = t2_series(df)
    ev = event_series(df)
    A = anchors(df, t1e)
    for k, v in A.items():
        print(f"  {k}: {len(v)} anchors")

    mkt_nom_map = mkt_nom.reindex(day).reset_index(drop=True)
    mkt_shf_map = mkt_shf.reindex(day).reset_index(drop=True)
    t1_by_res = {int(r.res_idx): (r.t1, r.t1_s, r.origin) for r in t1e.itertuples()} if len(t1e) else {}

    sess_name = np.array(["ASIA", "LONDON", "NY_AM", "NY_PM"])[sess_id]
    dow = day.dayofweek.to_numpy()
    mon = day.month.to_numpy()
    yr = day.year.to_numpy()
    before_p4 = np.asarray(ts < pd.Timestamp("2024-07-01", tz="UTC"))
    block = np.select(
        [yr <= 2015, (yr >= 2016) & (yr <= 2022), before_p4],
        ["P1", "P2", "P3"], "P4")

    recs = []
    for atype, lst in A.items():
        for (i, d) in lst:
            s = atr[i]
            if not np.isfinite(s) or s <= 0 or i + 1 + HORIZONS[0] > n:
                continue
            origin = t1_by_res.get(i, (None, None, np.nan))[2] if atype == "A6" else np.nan
            if atype == "A2":
                origin = o[i - 3] if i - 3 >= 0 else np.nan     # 1h bar open
            base = {
                "idx": i, "ts": ts[i], "anchor": atype, "dir": d,
                "block": block[i], "session": sess_name[i], "dow": int(dow[i]),
                "month": int(mon[i]), "sigma": s,
                "m1": mkt_nom_map.at[i, "m1"], "m2": mkt_nom_map.at[i, "m2"],
                "m3": mkt_nom_map.at[i, "m3"], "m4": mkt_nom_map.at[i, "m4"],
                "m5": mkt_nom_map.at[i, "m5"],
                "m1_s": mkt_shf_map.at[i, "m1"], "m2_s": mkt_shf_map.at[i, "m2"],
                "m3_s": mkt_shf_map.at[i, "m3"], "m4_s": mkt_shf_map.at[i, "m4"],
                "m5_s": mkt_shf_map.at[i, "m5"],
                "t2": t2_b[i], "t2_s": t2_bs[i],
                "e1": ev["e1"][i], "e2": ev["e2"][i], "e3": ev["e3"][i],
                "e1_s": ev["e1"][i], "e2_s": ev["e2"][i], "e3_s": ev["e3"][i],
                "t1": t1_by_res.get(i, (np.nan,))[0] if atype == "A6" else np.nan,
                "t1_s": t1_by_res.get(i, (np.nan, np.nan))[1] if atype == "A6" else np.nan,
            }
            fp = fingerprint(i, s, cl[i], o, hi, lo, cl, n, sma20_map[i], sopen[i], origin)
            for row in fp:
                recs.append({**base, **row})
    out = pd.DataFrame(recs)
    out.to_parquet("research/m4/events.parquet")
    print(f"\nwrote research/m4/events.parquet  rows={len(out):,}  events={out['idx'].nunique():,}")
    print(out.groupby("anchor")["idx"].nunique())


def load_all():
    parts = []
    for sp in ("in_sample", "walk_forward"):
        d = load_bars("15min", split=sp); parts.append(d)
    d = load_bars("15min", split="out_of_sample", allow_oos=True); parts.append(d)
    return (pd.concat(parts, ignore_index=True).drop_duplicates("ts")
            .sort_values("ts").reset_index(drop=True))


if __name__ == "__main__":
    main()
