"""
H1b — H1 iteration 2 (deliberate). NY opening-range breakout, but:
  1. CLOSE-CONFIRMED break — the break bar must *close* beyond the level by >= buffer
     (fake-out filter), entered market-on-next-open.
  2. DAILY-BIAS alignment — long breaks only if price at 14:00 UTC > prior UTC-day
     close; short breaks only if below.
  3. Tighter OR-size filter: 0.5x .. 1.8x trailing-20d median (was 0.4 .. 2.5).
  4. NO fixed target — trailing stop (activate at +1R, trail 1x OR-height off the
     running close extreme) + 20:00 UTC flat.

Goal: far fewer, higher-conviction trades + bigger average win, to clear the
~0.10 R cost hurdle that H1 could not.

    python -m research.h1b
"""

import argparse
import os
import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from data_pipeline import config as C
from backtest.engine import Backtester, BTConfig
from backtest.metrics import compute_metrics, success_bar, monte_carlo_trades
from research.h1 import (opening_ranges, expectancy_by_year, welch_t, _tod,
                         ENTRY_FROM, ENTRY_TO, FLAT_HOUR, TICK, BUFFER_FRAC,
                         BUFFER_MIN_TICKS, TARGET_R)

FILTER_LO_B, FILTER_HI_B = 0.5, 1.8
TRAIL_ACTIVATE_R = 1.0
TRAIL_MULT = 1.0                 # trail_dist = TRAIL_MULT * OR_height


def _prior_day_close(df):
    d = df["ts"].dt.date
    last_close = df.groupby(d)["close"].last()
    prior = last_close.shift(1)
    return {dt: prior.loc[dt] for dt in prior.index if pd.notna(prior.loc[dt])}


def h1b_signals(df):
    g = opening_ranges(df)
    # override the size filter with the tighter band
    med = g["or_height"].shift(1).rolling(20).median()
    g["tradeable"] = ((g["or_height"] >= FILTER_LO_B * med) &
                      (g["or_height"] <= FILTER_HI_B * med) &
                      (g["or_height"] > 0)).fillna(False)

    n = len(df)
    ts = df["ts"]
    tmin = _tod(ts).to_numpy()
    dates = ts.dt.date.to_numpy()
    cl = df["close"].to_numpy(float)
    ef = ENTRY_FROM[0] * 60 + ENTRY_FROM[1]
    et = ENTRY_TO[0] * 60 + ENTRY_TO[1]
    in_win = (tmin >= ef) & (tmin < et)

    pdc = _prior_day_close(df)
    gd = g[g["tradeable"]]
    lut = {d: (r.or_high, r.or_low, r.or_height) for d, r in gd.iterrows()}

    le = np.zeros(n, bool); se = np.zeros(n, bool)
    stop_d = np.full(n, np.nan); trail_d = np.full(n, np.nan)
    fired_today = set()

    for i in range(n):
        if not in_win[i]:
            continue
        d = dates[i]
        rec = lut.get(d)
        if rec is None or d in fired_today:
            continue
        oh, ol, oht = rec
        buf = max(BUFFER_FRAC * oht, BUFFER_MIN_TICKS * TICK)
        bias = pdc.get(d)
        if bias is None:
            continue
        long_ok = cl[i] >= oh + buf and cl[i] > bias
        short_ok = cl[i] <= ol - buf and cl[i] < bias
        if not (long_ok or short_ok):
            continue
        sd = oht + buf
        # stop_dist read at i (engine market-entry reads i-1); set i and i+1
        for j in (i, i + 1):
            if j < n:
                stop_d[j] = sd
                trail_d[j] = TRAIL_MULT * oht
        (le if long_ok else se)[i] = True
        fired_today.add(d)

    return {"long_entry": le, "short_entry": se,
            "stop_dist": stop_d, "trail_dist": trail_d}, g


def _cfg(size_mode="fixed"):
    return BTConfig(session_flat_hour_utc=FLAT_HOUR, one_trade_per_day=True,
                    allow_short=True, reverse_on_opposite=False,
                    trail_activate_r=TRAIL_ACTIVATE_R, trail_ref="close",
                    size_mode=size_mode, size_lots=0.01, risk_pct=0.005,
                    initial_equity=1000.0)


def null_signals_b(df, g, seed=24680):
    """Same tradeable days, but random direction ignoring the break & bias,
    market entry at 14:00, same trailing exit."""
    n = len(df)
    tmin = _tod(df["ts"]).to_numpy()
    dates = df["ts"].dt.date.to_numpy()
    ef = ENTRY_FROM[0] * 60 + ENTRY_FROM[1]
    fire_min = ef - 5
    rng = np.random.default_rng(seed)
    gd = g[g["tradeable"]]
    dbd = {d: (1 if rng.random() < 0.5 else -1) for d in gd.index}
    lut = {d: (r.or_height) for d, r in gd.iterrows()}
    le = np.zeros(n, bool); se = np.zeros(n, bool)
    stop_d = np.full(n, np.nan); trail_d = np.full(n, np.nan)
    for i in range(n):
        if tmin[i] != fire_min:
            continue
        d = dates[i]
        if d not in dbd:
            continue
        oht = lut[d]
        buf = max(BUFFER_FRAC * oht, BUFFER_MIN_TICKS * TICK)
        sd = oht + buf
        for j in (i, i + 1):
            if j < n:
                stop_d[j] = sd
                trail_d[j] = TRAIL_MULT * oht
        (le if dbd[d] == 1 else se)[i] = True
    return {"long_entry": le, "short_entry": se, "stop_dist": stop_d, "trail_dist": trail_d}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="5min", choices=["1min", "5min", "15min"])
    ap.add_argument("--split", default="in_sample")
    args = ap.parse_args()

    df = load_bars(args.tf, split=args.split,
                   columns=["ts", "open", "high", "low", "close", "spread_mean"])
    print(f"bars={len(df):,}  {df['ts'].iloc[0]} .. {df['ts'].iloc[-1]}", flush=True)

    sig, g = h1b_signals(df)
    n_days = int(g["tradeable"].sum())
    n_fire = int(sig["long_entry"].sum() + sig["short_entry"].sum())
    print(f"tradeable days: {n_days} of {len(g)}   |   days a break+bias fired: {n_fire}", flush=True)

    res = Backtester(_cfg("fixed")).run(df, sig)
    res_r = Backtester(_cfg("risk_pct")).run(df, sig)
    nres = Backtester(_cfg("fixed")).run(df, null_signals_b(df, g))

    m = compute_metrics(res, args.tf)
    mr = compute_metrics(res_r, args.tf)
    nm = compute_metrics(nres, args.tf)
    sb = success_bar({**m, "max_drawdown_pct": mr["max_drawdown_pct"]})
    mc = monte_carlo_trades(res)
    tR = res["trades"]["r_multiple"].to_numpy() if len(res["trades"]) else np.array([])
    nR = nres["trades"]["r_multiple"].to_numpy() if len(nres["trades"]) else np.array([])
    mh, mn, tstat, nh, nn = welch_t(tR, nR)
    eby = expectancy_by_year(res["trades"])

    L = []
    P = L.append
    P("# H1b result - H1 iteration 2 (close-confirmed break + daily bias + trail)\n")
    P(f"_run {pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M} UTC - {args.tf} bars, in-sample_\n")
    P("## Headline (fixed 0.01-lot)\n```")
    for k in ["n_trades", "win_rate", "expectancy_usd", "expectancy_r", "profit_factor",
              "avg_win_usd", "avg_loss_usd", "avg_bars_held", "total_cost_usd",
              "gross_pnl_usd", "net_pnl_usd", "cost_drag_pct_of_gross"]:
        P(f"  {k:26s} {m.get(k)}")
    P(f"  exit_reason_mix            {m.get('exit_reason_mix')}")
    P("```\n")
    P("## 0.5%-risk run ($1,000)\n```")
    for k in ["final_equity", "total_return_pct", "max_drawdown_pct",
              "max_dd_duration_days", "sharpe", "sortino"]:
        P(f"  {k:26s} {mr.get(k)}")
    P("```\n")
    P("## Success bar\n```")
    P(sb.to_string(index=False))
    P(f"\n  ALL PASS: {sb.attrs['all_pass']}")
    P("```\n")
    P("## H1b vs NULL (random dir, same days, same trailing exit)\n```")
    P(f"  H1b  trades={nh:5d}  mean R = {mh:+.4f}  expectancy $ = {m['expectancy_usd']:+.4f}  PF = {m['profit_factor']:.3f}")
    P(f"  NULL trades={nn:5d}  mean R = {mn:+.4f}  expectancy $ = {nm['expectancy_usd']:+.4f}  PF = {nm['profit_factor']:.3f}")
    P(f"  Welch t (per-trade R): t = {tstat:+.2f}   (>|2| = distinguishable)")
    P("```\n")
    P("## Monte-Carlo (resample trade order)\n```")
    for k, v in mc.items():
        P(f"  {k:24s} {v}")
    P("```\n")
    P("## Expectancy by year\n```")
    P(eby.to_string())
    P("```\n")

    passes = (sb.attrs["all_pass"] and (tstat is not np.nan and tstat > 2)
              and m["profit_factor"] >= 1.25 and m["expectancy_usd"] > 0
              and isinstance(mc, dict) and mc.get("final_equity_p50", 0) > 1000.0)
    P("## Verdict\n")
    if passes:
        P("**PASS** -> proceed to M4 (walk-forward).")
    else:
        reasons = []
        if not sb.attrs["all_pass"]:
            reasons.append("success bar not all-PASS")
        if not (tstat is not np.nan and tstat > 2):
            reasons.append(f"null t={tstat:+.2f}")
        if m["profit_factor"] < 1.25:
            reasons.append(f"PF {m['profit_factor']:.3f} < 1.25")
        if m["expectancy_usd"] <= 0:
            reasons.append("expectancy <= 0 after costs")
        P("**KILL** - " + "; ".join(reasons))

    out = os.path.join(C.ROOT, "research", "H1b_RESULT.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L).encode("ascii", "replace").decode())
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
