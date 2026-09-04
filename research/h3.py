"""
H3 - Asian-quiet -> NY range expansion (XAUUSD). See H3_asian_quiet_ny_expansion.md.

On an unusually quiet Asian night (00:00-07:00 UTC range in the bottom 30% of the
trailing 60 days, ATR-normalised): place a two-sided OCO straddle around the Asian
range, break window 08:00-16:00 UTC, stop = opposite Asian extreme, trail from
+1.5R, flat 21:00 UTC. One trade/day. Direction-neutral.

Comparisons: UNCONDITIONAL (same straddle every day) and COIN-FLIP straddle
(one random side per quiet day).

    python -m research.h3
"""

import argparse
import os
import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from data_pipeline import config as C
from backtest.engine import Backtester, BTConfig
from backtest.metrics import compute_metrics, success_bar, monte_carlo_trades
from research.h1 import expectancy_by_year, welch_t
from research.h2 import _atr20_by_date

ASIAN_END = 7 * 60                 # 00:00-07:00 UTC
ENTRY_FROM, ENTRY_TO = 8 * 60, 16 * 60   # 08:00-16:00 UTC (end exclusive)
FLAT_HOUR = 21
MIN_ASIAN_BARS = 67
QUIET_PCTL = 0.30
QUIET_WIN = 60
TRAIL_ACTIVATE_R = 1.5
TRAIL_MULT = 1.5
BUFFER_FRAC = 0.05
BUFFER_MIN_TICKS = 3
TICK = 0.01


def _tod(ts):
    return ts.dt.hour * 60 + ts.dt.minute


def asian_table(df):
    tmin = _tod(df["ts"])
    A = df[tmin < ASIAN_END].copy()
    A["date"] = A["ts"].dt.date
    g = A.groupby("date").agg(a_hi=("high", "max"), a_lo=("low", "min"), n=("open", "size"))
    g = g[g["n"] >= MIN_ASIAN_BARS]
    g["a_rng"] = g["a_hi"] - g["a_lo"]
    g = g.join(_atr20_by_date(df).rename("atr20"))
    g["a_norm"] = g["a_rng"] / g["atr20"]
    g["q_thr"] = g["a_norm"].shift(1).rolling(QUIET_WIN).quantile(QUIET_PCTL)
    g["quiet"] = ((g["a_norm"] <= g["q_thr"]) & g["q_thr"].notna()
                  & (g["a_rng"] > 0) & g["atr20"].notna()).fillna(False)
    return g


def _straddle_signals(df, g, which_days, mode="both", seed=777):
    """which_days: 'quiet' | 'all'.  mode: 'both' | 'coinflip'."""
    n = len(df)
    tmin = _tod(df["ts"]).to_numpy()
    dates = df["ts"].dt.date.to_numpy()
    in_win = (tmin >= ENTRY_FROM) & (tmin < ENTRY_TO)
    sel = g[g["quiet"]] if which_days == "quiet" else g[g["a_rng"] > 0]
    rng = np.random.default_rng(seed)
    side_pick = {d: (1 if rng.random() < 0.5 else -1) for d in sel.index}
    lut = {d: (r.a_hi, r.a_lo, r.a_rng) for d, r in sel.iterrows()}

    l_stop = np.full(n, np.nan); s_stop = np.full(n, np.nan)
    stop_d = np.full(n, np.nan); trail_d = np.full(n, np.nan)
    for i in range(n):
        if not in_win[i]:
            continue
        rec = lut.get(dates[i])
        if rec is None:
            continue
        ah, al, ar = rec
        buf = max(BUFFER_FRAC * ar, BUFFER_MIN_TICKS * TICK)
        sd = ar + buf
        put_long = mode == "both" or side_pick[dates[i]] == 1
        put_short = mode == "both" or side_pick[dates[i]] == -1
        if put_long:
            l_stop[i] = ah + buf
        if put_short:
            s_stop[i] = al - buf
        stop_d[i] = sd
        trail_d[i] = TRAIL_MULT * ar
    return {"long_stop": l_stop, "short_stop": s_stop,
            "stop_dist": stop_d, "trail_dist": trail_d}


def _cfg(size_mode="fixed"):
    return BTConfig(session_flat_hour_utc=FLAT_HOUR, one_trade_per_day=True,
                    allow_short=True, reverse_on_opposite=False,
                    trail_activate_r=TRAIL_ACTIVATE_R, trail_ref="close",
                    size_mode=size_mode, size_lots=0.01, risk_pct=0.005,
                    initial_equity=1000.0)


def realised_ny_range_check(df, g):
    """Mechanism check independent of the trade rules: median NY range
    (08:00-18:00 UTC high-low, ATR-normalised) on quiet vs non-quiet days."""
    tmin = _tod(df["ts"])
    NY = df[(tmin >= ENTRY_FROM) & (tmin < 18 * 60)].copy()
    NY["date"] = NY["ts"].dt.date
    r = NY.groupby("date").agg(hi=("high", "max"), lo=("low", "min"))
    r["ny_rng"] = r["hi"] - r["lo"]
    r = r.join(g[["quiet", "atr20"]])
    r["ny_norm"] = r["ny_rng"] / r["atr20"]
    r = r.dropna(subset=["ny_norm"])
    qmask = r["quiet"].fillna(False).astype(bool).to_numpy()
    q = r["ny_norm"].to_numpy()[qmask]
    nq = r["ny_norm"].to_numpy()[~qmask]
    q = pd.Series(q); nq = pd.Series(nq)
    return dict(n_quiet=len(q), n_nonquiet=len(nq),
                ny_norm_median_quiet=round(float(q.median()), 3),
                ny_norm_median_nonquiet=round(float(nq.median()), 3),
                ny_norm_mean_quiet=round(float(q.mean()), 3),
                ny_norm_mean_nonquiet=round(float(nq.mean()), 3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="5min", choices=["1min", "5min", "15min"])
    ap.add_argument("--split", default="in_sample")
    args = ap.parse_args()

    df = load_bars(args.tf, split=args.split,
                   columns=["ts", "open", "high", "low", "close", "spread_mean"])
    print(f"bars={len(df):,}  {df['ts'].iloc[0]} .. {df['ts'].iloc[-1]}", flush=True)

    g = asian_table(df)
    nq = int(g["quiet"].sum())
    print(f"usable Asian days: {len(g)}   quiet: {nq} ({nq/len(g)*100:.0f}%)", flush=True)

    mech = realised_ny_range_check(df, g)

    res = Backtester(_cfg("fixed")).run(df, _straddle_signals(df, g, "quiet", "both"))
    res_r = Backtester(_cfg("risk_pct")).run(df, _straddle_signals(df, g, "quiet", "both"))
    ures = Backtester(_cfg("fixed")).run(df, _straddle_signals(df, g, "all", "both"))
    cres = Backtester(_cfg("fixed")).run(df, _straddle_signals(df, g, "quiet", "coinflip"))

    m = compute_metrics(res, args.tf)
    mr = compute_metrics(res_r, args.tf)
    um = compute_metrics(ures, args.tf)
    cm = compute_metrics(cres, args.tf)
    sb = success_bar({**m, "max_drawdown_pct": mr["max_drawdown_pct"]})
    mc = monte_carlo_trades(res)

    tR = res["trades"]["r_multiple"].to_numpy() if len(res["trades"]) else np.array([])
    uR = ures["trades"]["r_multiple"].to_numpy() if len(ures["trades"]) else np.array([])
    cR = cres["trades"]["r_multiple"].to_numpy() if len(cres["trades"]) else np.array([])
    mh, mu, t_uncond, _, _ = welch_t(tR, uR)
    _, mc_r, t_coin, _, _ = welch_t(tR, cR)
    eby = expectancy_by_year(res["trades"])

    tr = res["trades"]
    fast = tr[(tr.exit_reason == "stop") & (tr.bars_held <= 12)]

    L = []
    P = L.append
    P("# H3 result - Asian-quiet -> NY range expansion (in-sample 2009-2022)\n")
    P(f"_run {pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M} UTC - {args.tf} bars, Dukascopy canonical_\n")

    P("## Mechanism check (independent of trade rules)\n```")
    for k, v in mech.items():
        P(f"  {k:26s} {v}")
    P("  -> quiet nights SHOULD show a larger realised NY range (ny_norm) than non-quiet")
    P("```\n")

    P("## Headline (fixed 0.01-lot, quiet days, two-sided)\n```")
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

    P("## H3 vs comparisons - per-trade R\n```")
    P(f"  H3 (quiet, two-sided)     n={len(tR):4d}  mean R = {mh:+.4f}   expectancy $ = {m['expectancy_usd']:+.4f}   PF = {m['profit_factor']:.3f}")
    P(f"  UNCONDITIONAL (all days)  n={len(uR):4d}  mean R = {mu:+.4f}   expectancy $ = {um['expectancy_usd']:+.4f}   PF = {um['profit_factor']:.3f}")
    P(f"  COIN-FLIP straddle        n={len(cR):4d}  mean R = {mc_r:+.4f}   expectancy $ = {cm['expectancy_usd']:+.4f}   PF = {cm['profit_factor']:.3f}")
    P(f"  Welch t  H3 vs UNCOND = {t_uncond:+.2f}   H3 vs COINFLIP = {t_coin:+.2f}")
    P("  PASS needs: H3 mean R > UNCOND mean R  AND  H3 mean R > COINFLIP mean R")
    P("```\n")

    P("## Whipsaw slice (stopped <= 60 min after entry)\n```")
    P(f"  fast stop-outs: {len(fast)} of {len(tr)} ({len(fast)/max(len(tr),1)*100:.0f}%)  mean net $ = {fast.net_pnl.mean():+.3f}")
    P("```\n")

    P("## Monte-Carlo (resample trade order)\n```")
    for k, v in mc.items():
        P(f"  {k:24s} {v}")
    P("```\n")

    P("## Expectancy by year\n```")
    P(eby.to_string())
    P("```\n")

    beats_uncond = mh > mu
    beats_coin = mh > mc_r
    passes = (sb.attrs["all_pass"] and beats_uncond and beats_coin
              and m["profit_factor"] >= 1.25 and m["expectancy_usd"] > 0
              and isinstance(mc, dict) and mc.get("final_equity_p50", 0) > 1000.0)
    P("## Verdict\n")
    if passes:
        P("**PASS** -> proceed to M4 (walk-forward).")
    else:
        r = []
        if not sb.attrs["all_pass"]:
            r.append("success bar not all-PASS")
        if not beats_uncond:
            r.append(f"does NOT beat unconditional (H3 R {mh:+.4f} <= all-days R {mu:+.4f}) -> quiet gate adds nothing")
        if not beats_coin:
            r.append(f"does NOT beat coin-flip straddle (H3 R {mh:+.4f} <= {mc_r:+.4f})")
        if m["profit_factor"] < 1.25:
            r.append(f"PF {m['profit_factor']:.3f} < 1.25")
        if m["expectancy_usd"] <= 0:
            r.append("expectancy <= 0 after costs")
        if not (isinstance(mc, dict) and mc.get("final_equity_p50", 0) > 1000.0):
            r.append("MC median not profitable")
        P("**KILL** - " + "; ".join(r))

    out = os.path.join(C.ROOT, "research", "H3_RESULT.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L).encode("ascii", "replace").decode())
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
