"""
H5 - Long/short daily trend momentum on gold, vol-targeted. See H5_daily_trend_momentum.md.

Daily bars. Signal = 1/2 (sign(3m return) + sign(12m return)). Position = signal
* min(12% / realised_vol_20d, 3x). Daily rebalance, no stop. Costs: spread +
slippage + $6/lot on turnover, plus 3%/yr carry on gross exposure.

    python -m research.h5
"""

import argparse
import os
import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from data_pipeline import config as C

MOM_FAST, MOM_SLOW = 63, 252
VOL_WIN = 20
TARGET_VOL = 0.12
MAX_LEV = 3.0
SLIP_TICKS = 1.0
TICK = 0.01
COMMISSION_PER_LOT = 6.0
CONTRACT = 100.0
CARRY_ANN = 0.03
TRADING_DAYS = 252


def daily_frame(split):
    df = load_bars("1min", split=split, allow_oos=(split == "out_of_sample"),
                   columns=["ts", "open", "high", "low", "close", "spread_mean"])
    d = df.set_index("ts").resample("1D").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), spread=("spread_mean", "mean")).dropna(subset=["close"])
    d["spread"] = d["spread"].ffill()
    d["ret"] = np.log(d["close"]).diff()
    return d


def trend_signal(close):
    f = np.sign(close / close.shift(MOM_FAST) - 1.0)
    s = np.sign(close / close.shift(MOM_SLOW) - 1.0)
    return 0.5 * (f + s)


def vol_scalar(ret):
    rv = ret.rolling(VOL_WIN).std() * np.sqrt(TRADING_DAYS)
    return (TARGET_VOL / rv).clip(upper=MAX_LEV)


def run_positions(d, pos):
    """pos: target position (signed leverage) already lagged to be tradable on day t.
    Returns dict of series: gross, txn_cost, carry, net, equity."""
    ret = d["ret"].fillna(0.0)
    price = d["close"]
    spr = d["spread"]
    dpos = pos.diff().abs().fillna(pos.abs())
    txn_frac = dpos * ((spr / 2 + SLIP_TICKS * TICK) / price + COMMISSION_PER_LOT / (price * CONTRACT))
    carry_frac = pos.abs() * (CARRY_ANN / TRADING_DAYS)
    gross = pos * ret
    net = gross - txn_frac - carry_frac
    eq = (1.0 + net).cumprod()
    return dict(gross=gross, txn=txn_frac, carry=carry_frac, net=net, equity=eq)


def perf(net, equity):
    n = len(net.dropna())
    r = net.dropna()
    cagr = equity.iloc[-1] ** (TRADING_DAYS / n) - 1.0
    sharpe = r.mean() / r.std() * np.sqrt(TRADING_DAYS) if r.std() > 0 else 0.0
    dn = r[r < 0].std()
    sortino = r.mean() / dn * np.sqrt(TRADING_DAYS) if dn and dn > 0 else 0.0
    peak = equity.cummax()
    ddser = equity / peak - 1.0
    maxdd = float(-ddser.min())
    # DD duration (days): longest run below a running peak
    below = (equity < peak).to_numpy()
    idx = equity.index
    best = 0.0; start = None
    for k, b in enumerate(below):
        if b and start is None:
            start = idx[k]
        elif not b and start is not None:
            best = max(best, (idx[k] - start).days); start = None
    if start is not None:
        best = max(best, (idx[-1] - start).days)
    total_ret = float(equity.iloc[-1] - 1.0)
    return dict(cagr=cagr, sharpe=sharpe, sortino=sortino, max_dd=maxdd,
                dd_days=best, total_return=total_ret)


def holding_trades(pos, net):
    """Segment by constant nonzero sign of pos; trade return = prod(1+net)-1."""
    sgn = np.sign(pos.fillna(0.0)).to_numpy()
    nn = net.fillna(0.0).to_numpy()
    trades = []
    i = 0
    while i < len(sgn):
        if sgn[i] == 0:
            i += 1
            continue
        j = i
        while j < len(sgn) and sgn[j] == sgn[i]:
            j += 1
        tr = np.prod(1.0 + nn[i:j]) - 1.0
        trades.append(tr)
        i = j
    trades = np.array(trades)
    if len(trades) == 0:
        return 0, 0.0, 0.0
    wins = trades[trades > 0].sum()
    losses = -trades[trades <= 0].sum()
    pf = wins / losses if losses > 0 else float("inf")
    return len(trades), pf, float((trades > 0).mean())


def by_period(net, equity):
    e = pd.DataFrame({"net": net}).dropna()
    e["year"] = e.index.year
    yr = e.groupby("year")["net"].apply(lambda s: (1 + s).prod() - 1) * 100
    h1 = e[e.index < "2016-01-01"]["net"]
    h2 = e[e.index >= "2016-01-01"]["net"]
    return yr, float((1 + h1).prod() - 1), float((1 + h2).prod() - 1)


def block_bootstrap(net, n_iter=2000, block=20, seed=0):
    r = net.dropna().to_numpy()
    if len(r) < block * 3:
        return {}
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(len(r) / block))
    cagrs, dds = [], []
    for _ in range(n_iter):
        starts = rng.integers(0, len(r) - block, size=nblocks)
        samp = np.concatenate([r[s:s + block] for s in starts])[:len(r)]
        eq = np.cumprod(1 + samp)
        cagrs.append(eq[-1] ** (TRADING_DAYS / len(samp)) - 1)
        peak = np.maximum.accumulate(eq)
        dds.append(float(-(eq / peak - 1).min()))
    cagrs, dds = np.array(cagrs), np.array(dds)
    return dict(cagr_p05=float(np.percentile(cagrs, 5)),
               cagr_p50=float(np.percentile(cagrs, 50)),
               cagr_p95=float(np.percentile(cagrs, 95)),
               prob_cagr_pos=float((cagrs > 0).mean()),
               maxdd_p50=float(np.percentile(dds, 50)),
               maxdd_p95=float(np.percentile(dds, 95)))


def realistic_account(d, sig, vs, equity0=1000.0):
    """Min-lot 0.01 on a small account: recompute the path with lot rounding."""
    price = d["close"].to_numpy()
    tgt = (sig * vs).shift(1).fillna(0.0).to_numpy()
    ret = d["ret"].fillna(0.0).to_numpy()
    spr = d["spread"].to_numpy()
    eq = equity0
    eqs = np.empty(len(price)); pos_prev_lots = 0.0
    lev_used = []
    for k in range(len(price)):
        want_lots = tgt[k] * eq / (price[k] * CONTRACT)
        lots = np.sign(want_lots) * max(0.01, round(abs(want_lots) / 0.01) * 0.01) if abs(want_lots) > 1e-9 else 0.0
        notional = lots * price[k] * CONTRACT
        pos_frac = notional / eq if eq > 0 else 0.0
        lev_used.append(abs(pos_frac))
        dlots = abs(lots - pos_prev_lots)
        txn = dlots * ((spr[k] / 2 + SLIP_TICKS * TICK) * CONTRACT + COMMISSION_PER_LOT)
        carry = abs(notional) * (CARRY_ANN / TRADING_DAYS)
        pnl = pos_frac * eq * ret[k] - txn - carry
        eq = max(eq + pnl, 0.0)
        eqs[k] = eq
        pos_prev_lots = lots
        if eq <= 0:
            eqs[k:] = 0.0
            break
    s = pd.Series(eqs, index=d.index)
    net = s.pct_change().fillna(0.0)
    return s, net, float(np.mean(lev_used))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="in_sample")
    args = ap.parse_args()

    d = daily_frame(args.split)
    print(f"daily bars: {len(d)}  {d.index[0].date()} .. {d.index[-1].date()}", flush=True)

    sig = trend_signal(d["close"])
    vs = vol_scalar(d["ret"])
    pos = (sig * vs).shift(1)                       # tradable on day t

    R = run_positions(d, pos)
    p = perf(R["net"], R["equity"])
    nt, pf, wr = holding_trades(pos, R["net"])
    yr, h1, h2 = by_period(R["net"], R["equity"])
    bb = block_bootstrap(R["net"])

    # comparisons
    bh = run_positions(d, pd.Series(1.0, index=d.index)); bp = perf(bh["net"], bh["equity"])
    lf = run_positions(d, (sig.clip(lower=0) * vs).shift(1)); lp = perf(lf["net"], lf["equity"])
    rng = np.random.default_rng(20260904)
    rsign = pd.Series(rng.choice([-1.0, 1.0], size=len(d)), index=d.index)
    rn = run_positions(d, (rsign * vs).shift(1)); rp = perf(rn["net"], rn["equity"])

    ra_eq, ra_net, ra_lev = realistic_account(d, sig, vs)
    rap = perf(ra_net, ra_eq)

    cost_tot = (R["txn"].sum() + R["carry"].sum())
    turnover = pos.diff().abs().sum()

    L = []; P = L.append
    P("# H5 result - long/short daily trend momentum on gold (in-sample 2009-2022)\n")
    P(f"_run {pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M} UTC - daily bars, Dukascopy canonical, vs recalibrated bar (blueprint 6a)_\n")

    P("## Idealised run (fractional sizing - true risk-adjusted properties)\n```")
    for k in ["total_return", "cagr", "sharpe", "sortino", "max_dd", "dd_days"]:
        P(f"  {k:14s} {p[k]:+.4f}")
    P(f"  holding_trades {nt}   profit_factor {pf:.3f}   win_rate {wr:.3f}")
    P(f"  ann.turnover ~{turnover/ (len(d)/TRADING_DAYS):.0f}x   total cost (txn+carry) frac {cost_tot:+.4f}")
    P("```\n")

    P("## Comparisons (idealised, same cost model)\n```")
    P(f"  {'':16s} {'totRet':>9} {'CAGR':>8} {'Sharpe':>7} {'Sortino':>8} {'maxDD':>8}")
    for name, x in [("H5 trend L/S", p), ("buy & hold", bp), ("long/flat", lp), ("random-sign", rp)]:
        P(f"  {name:16s} {x['total_return']:+9.3f} {x['cagr']:+8.3f} {x['sharpe']:+7.2f} {x['sortino']:+8.2f} {x['max_dd']:8.3f}")
    P("```\n")

    P("## Realistic $1,000 account (min lot 0.01)\n```")
    for k in ["total_return", "cagr", "sharpe", "sortino", "max_dd"]:
        P(f"  {k:14s} {rap[k]:+.4f}")
    P(f"  final_equity ${ra_eq.iloc[-1]:.0f}   mean gross leverage used {ra_lev:.2f}x")
    P("  (min-lot forces leverage above the 12% vol target on a $1k account -> higher DD; needs ~$3-5k to run as designed)")
    P("```\n")

    P("## Robustness\n```")
    P(f"  half 2009-2015 return: {h1*100:+.1f}%     half 2016-2022 return: {h2*100:+.1f}%")
    P("  by year (%):")
    for y, v in yr.items():
        P(f"    {y}  {v:+7.1f}")
    if bb:
        P(f"  block-bootstrap (20d): CAGR p05/p50/p95 = {bb['cagr_p05']:+.3f}/{bb['cagr_p50']:+.3f}/{bb['cagr_p95']:+.3f}  "
          f"prob(CAGR>0) {bb['prob_cagr_pos']:.2f}  maxDD p50/p95 {bb['maxdd_p50']:.3f}/{bb['maxdd_p95']:.3f}")
    P("```\n")

    # verdict vs recalibrated bar
    beats_bh = (p["total_return"] > bp["total_return"]) and (p["max_dd"] < bp["max_dd"])
    checks = {
        "beats buy&hold on return AND maxDD": beats_bh,
        "max_dd <= 0.30": p["max_dd"] <= 0.30,
        "dd_days <= 365": p["dd_days"] <= 365,
        "sharpe >= 0.5": p["sharpe"] >= 0.5,
        "sortino >= 0.7": p["sortino"] >= 0.7,
        "profit_factor >= 1.15": pf >= 1.15,
        "cagr > 0": p["cagr"] > 0,
        "positive both halves": (h1 > 0 and h2 > 0),
        "beats random-sign null (Sharpe)": p["sharpe"] > rp["sharpe"],
    }
    P("## Verdict (recalibrated single-asset bar, blueprint 6a)\n```")
    for k, v in checks.items():
        P(f"  [{'PASS' if v else 'FAIL'}] {k}")
    P("```\n")
    if all(checks.values()):
        P("**PASS** -> proceed to M4 (walk-forward).")
    else:
        P("**KILL** - fails: " + "; ".join(k for k, v in checks.items() if not v))

    out = os.path.join(C.ROOT, "research", "H5_RESULT.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L).encode("ascii", "replace").decode())
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
