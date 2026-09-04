"""
H1 — New York opening-range breakout (XAUUSD).  See H1_ny_opening_range_breakout.md.

    python -m research.h1                 # run in-sample, print + write H1_RESULT.md
    python -m research.h1 --tf 5min

Produces the H1 run, the same-time random-direction NULL, the success-bar table,
Monte-Carlo, expectancy by year, and an H1-vs-NULL t-test on per-trade R.
"""

import argparse
import os
import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from data_pipeline import config as C
from backtest.engine import Backtester, BTConfig
from backtest.metrics import compute_metrics, success_bar, monte_carlo_trades

TICK = 0.01
OR_START = (13, 30)          # UTC
OR_END = (14, 0)             # exclusive
ENTRY_FROM = (14, 0)
ENTRY_TO = (18, 0)           # exclusive — no new entry at/after this
FLAT_HOUR = 20
BUFFER_FRAC = 0.05
BUFFER_MIN_TICKS = 3
TARGET_R = 1.5
FILTER_LO, FILTER_HI = 0.4, 2.5
FILTER_WIN = 20             # trailing days for the OR-size filter


def _tod(ts):
    return ts.dt.hour * 60 + ts.dt.minute


def opening_ranges(df):
    """Per-UTC-date OR high/low/height/mid from the 13:30–14:00 window."""
    tmin = _tod(df["ts"])
    lo_min = OR_START[0] * 60 + OR_START[1]
    hi_min = OR_END[0] * 60 + OR_END[1]
    in_or = (tmin >= lo_min) & (tmin < hi_min)
    w = df.loc[in_or, ["ts", "high", "low"]].copy()
    w["date"] = w["ts"].dt.date
    g = w.groupby("date").agg(or_high=("high", "max"), or_low=("low", "min"),
                              n=("high", "size"))
    g = g[g["n"] >= 5]
    g["or_height"] = g["or_high"] - g["or_low"]
    g["or_mid"] = (g["or_high"] + g["or_low"]) / 2
    # trailing-median filter (prior days only -> no look-ahead)
    med = g["or_height"].shift(1).rolling(FILTER_WIN).median()
    g["tradeable"] = (g["or_height"] >= FILTER_LO * med) & (g["or_height"] <= FILTER_HI * med) \
        & (g["or_height"] > 0)
    g["tradeable"] = g["tradeable"].fillna(False)
    return g


def h1_signals(df):
    g = opening_ranges(df)
    n = len(df)
    ts = df["ts"]
    tmin = _tod(ts).to_numpy()
    dates = ts.dt.date.to_numpy()
    ef = ENTRY_FROM[0] * 60 + ENTRY_FROM[1]
    et = ENTRY_TO[0] * 60 + ENTRY_TO[1]
    in_win = (tmin >= ef) & (tmin < et)

    l_stop = np.full(n, np.nan)
    s_stop = np.full(n, np.nan)
    stop_d = np.full(n, np.nan)
    tgt_d = np.full(n, np.nan)

    gd = g[g["tradeable"]]
    lut = {d: (r.or_high, r.or_low, r.or_height) for d, r in gd.iterrows()}
    for i in range(n):
        if not in_win[i]:
            continue
        rec = lut.get(dates[i])
        if rec is None:
            continue
        oh, ol, oht = rec
        buf = max(BUFFER_FRAC * oht, BUFFER_MIN_TICKS * TICK)
        l_stop[i] = oh + buf
        s_stop[i] = ol - buf
        sd = oht + buf              # entry -> opposite OR side (same for long & short)
        stop_d[i] = sd
        tgt_d[i] = TARGET_R * sd
    return {"long_stop": l_stop, "short_stop": s_stop,
            "stop_dist": stop_d, "target_dist": tgt_d}, g


def null_signals(df, g, seed=12345):
    """Same tradeable days/filter; market entry at 14:00 UTC in a random
    direction; identical stop_dist / target_dist / flat / one-per-day."""
    n = len(df)
    ts = df["ts"]
    tmin = _tod(ts).to_numpy()
    dates = ts.dt.date.to_numpy()
    ef = ENTRY_FROM[0] * 60 + ENTRY_FROM[1]
    # fire on the bar just before 14:00 so the engine fills at the 14:00 open
    fire_min = ef - 5
    rng = np.random.default_rng(seed)
    gd = g[g["tradeable"]]
    dir_by_date = {d: (1 if rng.random() < 0.5 else -1) for d in gd.index}
    lut = {d: r.or_height for d, r in gd.iterrows()}

    le = np.zeros(n, bool); se = np.zeros(n, bool)
    stop_d = np.full(n, np.nan); tgt_d = np.full(n, np.nan)
    for i in range(n):
        if tmin[i] != fire_min:
            continue
        d = dates[i]
        if d not in dir_by_date:
            continue
        oht = lut[d]
        buf = max(BUFFER_FRAC * oht, BUFFER_MIN_TICKS * TICK)
        sd = oht + buf
        # stop_dist is read at i-1 for market entries -> set on the fire bar (i),
        # engine uses index i-1 for the fill; simplest: set for i and i-1.
        stop_d[i] = sd; tgt_d[i] = TARGET_R * sd
        (le if dir_by_date[d] == 1 else se)[i] = True
    # engine reads stop_d[i-1] for a signal at i-1 -> shift a copy forward by 1
    stop_d2 = np.roll(stop_d, 1); stop_d2[0] = np.nan
    tgt_d2 = np.roll(tgt_d, 1); tgt_d2[0] = np.nan
    stop_d = np.where(np.isnan(stop_d), stop_d2, stop_d)
    tgt_d = np.where(np.isnan(tgt_d), tgt_d2, tgt_d)
    return {"long_entry": le, "short_entry": se, "stop_dist": stop_d, "target_dist": tgt_d}


def _cfg(size_mode="fixed"):
    return BTConfig(session_flat_hour_utc=FLAT_HOUR, one_trade_per_day=True,
                    allow_short=True, reverse_on_opposite=False,
                    size_mode=size_mode, size_lots=0.01, risk_pct=0.005,
                    initial_equity=1000.0)


def expectancy_by_year(trades):
    if len(trades) == 0:
        return pd.DataFrame()
    t = trades.copy()
    t["year"] = pd.to_datetime(t["entry_ts"]).dt.year
    return t.groupby("year").agg(
        n=("net_pnl", "size"),
        exp_usd=("net_pnl", "mean"),
        exp_R=("r_multiple", "mean"),
        win_rate=("net_pnl", lambda s: (s > 0).mean() * 100),
    ).round(3)


def welch_t(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    ma, mb = a.mean(), b.mean()
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return ma, mb, (ma - mb) / se if se > 0 else np.nan, len(a), len(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="5min", choices=["1min", "5min", "15min"])
    ap.add_argument("--split", default="in_sample")
    args = ap.parse_args()

    df = load_bars(args.tf, split=args.split,
                   columns=["ts", "open", "high", "low", "close", "spread_mean"])
    print(f"bars={len(df):,}  {df['ts'].iloc[0]} .. {df['ts'].iloc[-1]}", flush=True)

    sig, g = h1_signals(df)
    n_days = int(g["tradeable"].sum())
    print(f"tradeable days (OR present + size filter): {n_days} of {len(g)}", flush=True)

    res_fixed = Backtester(_cfg("fixed")).run(df, sig)
    res_risk = Backtester(_cfg("risk_pct")).run(df, sig)
    nres = Backtester(_cfg("fixed")).run(df, null_signals(df, g))

    m = compute_metrics(res_fixed, args.tf)
    mr = compute_metrics(res_risk, args.tf)
    nm = compute_metrics(nres, args.tf)
    sb = success_bar({**m, "max_drawdown_pct": mr["max_drawdown_pct"]})   # DD from risk_pct run
    mc = monte_carlo_trades(res_fixed)

    tR = res_fixed["trades"]["r_multiple"].to_numpy() if len(res_fixed["trades"]) else np.array([])
    nR = nres["trades"]["r_multiple"].to_numpy() if len(nres["trades"]) else np.array([])
    mh, mn, tstat, nh, nn = welch_t(tR, nR)

    eby = expectancy_by_year(res_fixed["trades"])

    lines = []
    P = lines.append
    P("# H1 result — NY opening-range breakout (in-sample 2009–2022)\n")
    P(f"_run {pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M} UTC · {args.tf} bars · Dukascopy canonical_\n")

    P("## Headline (fixed 0.01-lot run)\n```")
    for k in ["n_trades", "win_rate", "expectancy_usd", "expectancy_r", "profit_factor",
              "avg_win_usd", "avg_loss_usd", "avg_bars_held", "total_cost_usd",
              "gross_pnl_usd", "net_pnl_usd", "cost_drag_pct_of_gross"]:
        P(f"  {k:26s} {m.get(k)}")
    P(f"  exit_reason_mix            {m.get('exit_reason_mix')}")
    P("```\n")

    P("## 0.5%-risk run (drawdown picture, $1,000 start)\n```")
    for k in ["final_equity", "total_return_pct", "max_drawdown_pct", "max_dd_duration_days",
              "sharpe", "sortino"]:
        P(f"  {k:26s} {mr.get(k)}")
    P("```\n")

    P("## Success bar\n```")
    P(sb.to_string(index=False))
    P(f"\n  ALL PASS: {sb.attrs['all_pass']}")
    P("```\n")

    P("## H1 vs NULL (same-time random-direction entry)\n```")
    P(f"  H1   trades={nh:5d}  mean R = {mh:+.4f}   expectancy $ = {m['expectancy_usd']:+.4f}   PF = {m['profit_factor']:.3f}")
    P(f"  NULL trades={nn:5d}  mean R = {mn:+.4f}   expectancy $ = {nm['expectancy_usd']:+.4f}   PF = {nm['profit_factor']:.3f}")
    P(f"  Welch t (H1 vs NULL, per-trade R): t = {tstat:+.2f}   (>|2| = distinguishable)")
    P("```\n")

    P("## Monte-Carlo (resample trade order, fixed-lot)\n```")
    for k, v in mc.items():
        P(f"  {k:24s} {v}")
    P("```\n")

    P("## Expectancy by year (fixed-lot)\n```")
    P(eby.to_string())
    P("```\n")

    # verdict
    passes = sb.attrs["all_pass"] and (tstat is not np.nan and tstat > 2) \
        and m["profit_factor"] >= 1.25 and m["expectancy_usd"] > 0
    mc_ok = isinstance(mc, dict) and mc.get("final_equity_p50", 0) > _cfg().initial_equity
    P("## Verdict\n")
    if passes and mc_ok:
        P("**PASS** — clears the success bar, beats the null, MC median profitable. → proceed to M4 (walk-forward).")
    else:
        P("**KILL** — does not clear the M3 bar. Recorded as a clean negative; draft H2.")
        reasons = []
        if not sb.attrs["all_pass"]:
            reasons.append("success bar not all-PASS")
        if not (tstat is not np.nan and tstat > 2):
            reasons.append(f"not distinguishable from null (t={tstat:+.2f})")
        if m["profit_factor"] < 1.25:
            reasons.append(f"PF {m['profit_factor']:.3f} < 1.25")
        if m["expectancy_usd"] <= 0:
            reasons.append("expectancy <= 0 after costs")
        if not mc_ok:
            reasons.append("MC median not profitable")
        P("\nReasons: " + "; ".join(reasons))

    out = os.path.join(C.ROOT, "research", "H1_RESULT.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
