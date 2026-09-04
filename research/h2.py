"""
H2 — London->NY momentum continuation (XAUUSD). See H2_london_to_ny_momentum.md.

On a *decisive* London session (07:00-12:00 UTC): enter market at 12:00 UTC in the
direction of the London move, stop at the opposite end of the London range, flat
at 20:00 UTC. One trade/day. Baselines: random-direction null + fade.

    python -m research.h2
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

LON_START, LON_END = (7, 0), (12, 0)      # UTC, end exclusive (last bar 11:55)
ENTRY_MIN = 12 * 60                       # fill at 12:00 open -> signal bar is 11:55
FLAT_HOUR = 20
K_MOVE = 0.4                              # |london_move| >= K_MOVE * ATR20d
DIRECTIONALITY = 0.5                      # |london_move| / london_range
MIN_LON_BARS = 48
ATR_WIN = 20


def _tod(ts):
    return ts.dt.hour * 60 + ts.dt.minute


def _atr20_by_date(df):
    d = df.groupby(df["ts"].dt.date).agg(H=("high", "max"), L=("low", "min"),
                                         Cl=("close", "last"))
    d["prevC"] = d["Cl"].shift(1)
    tr = np.maximum(d["H"] - d["L"],
                    np.maximum((d["H"] - d["prevC"]).abs(), (d["L"] - d["prevC"]).abs()))
    atr = tr.rolling(ATR_WIN).mean().shift(1)      # date t uses t-20..t-1
    return atr


def london_table(df):
    tmin = _tod(df["ts"])
    lo_m = LON_START[0] * 60 + LON_START[1]
    hi_m = LON_END[0] * 60 + LON_END[1]
    L = df[(tmin >= lo_m) & (tmin < hi_m)].copy()
    L["date"] = L["ts"].dt.date
    g = L.groupby("date").agg(l_open=("open", "first"), l_close=("close", "last"),
                              l_hi=("high", "max"), l_lo=("low", "min"), n=("open", "size"))
    g = g[g["n"] >= MIN_LON_BARS]
    g["move"] = g["l_close"] - g["l_open"]
    g["rng"] = g["l_hi"] - g["l_lo"]
    g["dirality"] = g["move"].abs() / g["rng"].replace(0, np.nan)
    g = g.join(_atr20_by_date(df).rename("atr20"))
    g["k"] = g["move"].abs() / g["atr20"]
    g["decisive"] = ((g["k"] >= K_MOVE) & (g["dirality"] >= DIRECTIONALITY)
                     & g["atr20"].notna() & (g["rng"] > 0)).fillna(False)
    return g


def _signals(df, g, mode):
    """mode: 'trend' | 'fade' | 'random'. Returns engine signal dict."""
    n = len(df)
    tmin = _tod(df["ts"]).to_numpy()
    dates = df["ts"].dt.date.to_numpy()
    sig_min = ENTRY_MIN - 5                        # 11:55 bar -> fills at 12:00 open
    gd = g[g["decisive"]]
    rng = np.random.default_rng(4242)
    rdir = {d: (1 if rng.random() < 0.5 else -1) for d in gd.index}
    lut = {d: (r.l_close, r.l_hi, r.l_lo, r.move) for d, r in gd.iterrows()}

    le = np.zeros(n, bool); se = np.zeros(n, bool)
    stop_d = np.full(n, np.nan)
    for i in range(n):
        if tmin[i] != sig_min:
            continue
        rec = lut.get(dates[i])
        if rec is None:
            continue
        lc, lhi, llo, mv = rec
        base = 1 if mv > 0 else -1
        side = {"trend": base, "fade": -base, "random": rdir[dates[i]]}[mode]
        sd = (lc - llo) if side > 0 else (lhi - lc)
        if not (sd > 0):
            continue
        for j in (i, i + 1):
            if j < n:
                stop_d[j] = sd
        (le if side > 0 else se)[i] = True
    return {"long_entry": le, "short_entry": se, "stop_dist": stop_d}


def _cfg(size_mode="fixed"):
    return BTConfig(session_flat_hour_utc=FLAT_HOUR, one_trade_per_day=True,
                    allow_short=True, reverse_on_opposite=False,
                    size_mode=size_mode, size_lots=0.01, risk_pct=0.005,
                    initial_equity=1000.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="5min", choices=["1min", "5min", "15min"])
    ap.add_argument("--split", default="in_sample")
    args = ap.parse_args()

    df = load_bars(args.tf, split=args.split,
                   columns=["ts", "open", "high", "low", "close", "spread_mean"])
    print(f"bars={len(df):,}  {df['ts'].iloc[0]} .. {df['ts'].iloc[-1]}", flush=True)

    g = london_table(df)
    n_dec = int(g["decisive"].sum())
    print(f"usable London days: {len(g)}   |   decisive: {n_dec} "
          f"({n_dec/len(g)*100:.0f}%)   up={int((g[g.decisive].move>0).sum())} "
          f"down={int((g[g.decisive].move<0).sum())}", flush=True)

    res = Backtester(_cfg("fixed")).run(df, _signals(df, g, "trend"))
    res_r = Backtester(_cfg("risk_pct")).run(df, _signals(df, g, "trend"))
    fres = Backtester(_cfg("fixed")).run(df, _signals(df, g, "fade"))
    nres = Backtester(_cfg("fixed")).run(df, _signals(df, g, "random"))

    m = compute_metrics(res, args.tf)
    mr = compute_metrics(res_r, args.tf)
    fm = compute_metrics(fres, args.tf)
    nm = compute_metrics(nres, args.tf)
    sb = success_bar({**m, "max_drawdown_pct": mr["max_drawdown_pct"]})
    mc = monte_carlo_trades(res)

    tR = res["trades"]["r_multiple"].to_numpy() if len(res["trades"]) else np.array([])
    nR = nres["trades"]["r_multiple"].to_numpy() if len(nres["trades"]) else np.array([])
    fR = fres["trades"]["r_multiple"].to_numpy() if len(fres["trades"]) else np.array([])
    mh, mn, tstat_n, _, _ = welch_t(tR, nR)
    _, mf, tstat_f, _, _ = welch_t(tR, fR)
    eby = expectancy_by_year(res["trades"])

    # data-reversal slice: stopped within 90 min (<=18 five-min bars) of entry
    tr = res["trades"]
    fast_stop = tr[(tr.exit_reason == "stop") & (tr.bars_held <= 18)]
    slow = tr[~((tr.exit_reason == "stop") & (tr.bars_held <= 18))]

    L = []
    P = L.append
    P("# H2 result - London->NY momentum continuation (in-sample 2009-2022)\n")
    P(f"_run {pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M} UTC - {args.tf} bars, Dukascopy canonical_\n")

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

    P("## H2 (trend) vs baselines — per-trade R\n```")
    P(f"  TREND   n={len(tR):4d}  mean R = {mh:+.4f}   expectancy $ = {m['expectancy_usd']:+.4f}   PF = {m['profit_factor']:.3f}")
    P(f"  RANDOM  n={len(nR):4d}  mean R = {mn:+.4f}   expectancy $ = {nm['expectancy_usd']:+.4f}   PF = {nm['profit_factor']:.3f}")
    P(f"  FADE    n={len(fR):4d}  mean R = {mf:+.4f}   expectancy $ = {fm['expectancy_usd']:+.4f}   PF = {fm['profit_factor']:.3f}")
    P(f"  Welch t  TREND vs RANDOM = {tstat_n:+.2f}   TREND vs FADE = {tstat_f:+.2f}   (>|2| = distinguishable)")
    P("```\n")

    P("## Data-reversal slice (stopped <= 90 min after entry)\n```")
    P(f"  fast stop-outs: {len(fast_stop)} of {len(tr)}  "
      f"({len(fast_stop)/max(len(tr),1)*100:.0f}%)  mean net $ = {fast_stop.net_pnl.mean():+.3f}")
    P(f"  everything else: {len(slow)}  mean net $ = {slow.net_pnl.mean():+.3f}")
    P("```\n")

    P("## Monte-Carlo (resample trade order)\n```")
    for k, v in mc.items():
        P(f"  {k:24s} {v}")
    P("```\n")

    P("## Expectancy by year\n```")
    P(eby.to_string())
    P("```\n")

    passes = (sb.attrs["all_pass"] and (tstat_n is not np.nan and tstat_n > 2)
              and (mh > mf) and m["profit_factor"] >= 1.25 and m["expectancy_usd"] > 0
              and isinstance(mc, dict) and mc.get("final_equity_p50", 0) > 1000.0)
    P("## Verdict\n")
    if passes:
        P("**PASS** -> proceed to M4 (walk-forward).")
    else:
        r = []
        if not sb.attrs["all_pass"]:
            r.append("success bar not all-PASS")
        if not (tstat_n is not np.nan and tstat_n > 2):
            r.append(f"vs random t={tstat_n:+.2f}")
        if not (mh > mf):
            r.append(f"does not beat the FADE (trend R {mh:+.4f} <= fade R {mf:+.4f}) -> reversion, not continuation")
        if m["profit_factor"] < 1.25:
            r.append(f"PF {m['profit_factor']:.3f} < 1.25")
        if m["expectancy_usd"] <= 0:
            r.append("expectancy <= 0 after costs")
        P("**KILL** - " + "; ".join(r))

    out = os.path.join(C.ROOT, "research", "H2_RESULT.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L).encode("ascii", "replace").decode())
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
