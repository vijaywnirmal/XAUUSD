"""
H7 - G7 FX carry. Rank EUR/GBP/JPY/AUD/NZD/CAD by 3-month rate vs USD; go long the
high-carry currencies vs USD, short the low-carry ones. Monthly rebalance, vol-
targeted. The rate differential is accrued daily (that IS the edge); the FX spot
move is the risk. Broker swap haircut applied.

    python -m research.h7_carry                    # in-sample 2009-2022
    python -m research.h7_carry --start 2023-01-01 --end 2024-07-01
"""
import argparse
import os
import numpy as np
import pandas as pd

from data_pipeline import config as C

BDIR = os.path.join(C.ROOT, "basket")
RATES = os.path.join(C.ROOT, "carry", "rates_3m.csv")
TD = 252
VOL_WIN = 20
INST_VOL = 0.08
PORT_VOL = 0.10
PORT_CAP = 3.0
SWAP_HAIRCUT_ANN = 0.010     # broker markup on the rate differential, both sides
FX_COST_BP = 0.6e-4          # round-trip per unit turnover
N_LONG = N_SHORT = 2

# pair -> (parquet, ccy, sign): "long ccy vs USD" return = sign * log(pair).diff()
PAIRS = {
    "EUR": ("EURUSD", +1), "GBP": ("GBPUSD", +1), "AUD": ("AUDUSD", +1),
    "NZD": ("NZDUSD", +1), "JPY": ("USDJPY", -1), "CAD": ("USDCAD", -1),
}


def load(start, end):
    rates = pd.read_csv(RATES, parse_dates=["date"]).set_index("date")
    px = {}
    for ccy, (fn, _s) in PAIRS.items():
        d = pd.read_parquet(os.path.join(BDIR, f"{fn}.parquet"))["close"]
        px[ccy] = d
    P = pd.DataFrame(px).sort_index()
    if P.index.tz is not None:
        P.index = P.index.tz_localize(None)
    P = P[(P.index >= pd.Timestamp(start)) & (P.index < pd.Timestamp(end))].asfreq("B").ffill(limit=3)
    return P, rates


def build(P, rates, mode="carry", seed=0):
    ccys = list(PAIRS)
    # "long ccy vs USD" daily return
    ret = pd.DataFrame({c: PAIRS[c][1] * np.log(P[c]).diff() for c in ccys})
    # carry (annual, decimal): rate[ccy] - rate[USD], forward-filled to daily
    rd = (rates[ccys].sub(rates["USD"], axis=0)) / 100.0
    rd = rd.reindex(P.index, method="ffill")
    carry_daily = rd / TD

    # monthly signal: rank by carry, long top N / short bottom N
    month = P.index.to_period("M")
    sig = pd.DataFrame(0.0, index=P.index, columns=ccys)
    rng = np.random.default_rng(seed)
    for m in month.unique():
        rows = P.index[month == m]
        if len(rows) == 0:
            continue
        d0 = rows[0]
        cd = rd.loc[d0]
        if mode == "carry":
            order = cd.sort_values()
            s = pd.Series(0.0, index=ccys)
            s[order.index[-N_LONG:]] = 1.0
            s[order.index[:N_SHORT]] = -1.0
        elif mode == "random":
            pick = rng.permutation(ccys)
            s = pd.Series(0.0, index=ccys)
            s[pick[:N_LONG]] = 1.0
            s[pick[N_LONG:N_LONG + N_SHORT]] = -1.0
        elif mode == "longUSD":                      # short every ccy vs USD
            s = pd.Series(-1.0, index=ccys)
        sig.loc[rows] = s.values

    rvol = ret.rolling(VOL_WIN).std() * np.sqrt(TD)
    w = (sig * (INST_VOL / rvol)).clip(-4, 4).shift(1)         # tradable day t
    gross = (w * (ret + carry_daily)).sum(axis=1)              # spot move + carry accrual
    pv = (gross.rolling(VOL_WIN).std() * np.sqrt(TD)).shift(1)
    k = (PORT_VOL / pv).clip(upper=PORT_CAP).fillna(0.0)
    turn = (w.mul(k, axis=0)).diff().abs().sum(axis=1)
    swap_hc = (w.mul(k, axis=0)).abs().sum(axis=1) * (SWAP_HAIRCUT_ANN / TD)
    net = k * gross - turn * FX_COST_BP - swap_hc
    eq = (1 + net.fillna(0)).cumprod()
    return net, eq


def perf(net, eq):
    r = net.dropna(); n = len(r)
    cagr = eq.iloc[-1] ** (TD / n) - 1
    sh = r.mean() / r.std() * np.sqrt(TD) if r.std() > 0 else 0.0
    dn = r[r < 0].std(); so = r.mean() / dn * np.sqrt(TD) if dn and dn > 0 else 0.0
    mdd = float(-(eq / eq.cummax() - 1).min())
    below = (eq < eq.cummax()).to_numpy(); ix = eq.index; best = 0; s = None
    for kk, b in enumerate(below):
        if b and s is None: s = ix[kk]
        elif not b and s is not None: best = max(best, (ix[kk] - s).days); s = None
    if s is not None: best = max(best, (ix[-1] - s).days)
    mret = r.groupby(r.index.to_period("M")).apply(lambda x: (1 + x).prod() - 1)
    return dict(cagr=cagr, sharpe=sh, sortino=so, maxdd=mdd, dddays=best,
               total=float(eq.iloc[-1] - 1), skew=float(mret.skew()),
               worst_month=float(mret.min()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2023-01-01")
    ap.add_argument("--eval-start", default=None)
    a = ap.parse_args()
    P, rates = load("2008-06-01" if a.eval_start else a.start, a.end)

    def rep(net, eq, tag):
        if a.eval_start:
            m = (net.index >= pd.Timestamp(a.eval_start)) & (net.index < pd.Timestamp(a.end))
            net = net[m]; eq = (1 + net.fillna(0)).cumprod()
        p = perf(net, eq)
        print(f"  {tag:18s} totRet={p['total']:+.3f} CAGR={p['cagr']:+.3f} Sharpe={p['sharpe']:+.2f} "
              f"Sortino={p['sortino']:+.2f} maxDD={p['maxdd']:.3f} ddDays={p['dddays']:.0f} "
              f"skew={p['skew']:+.2f} worstM={p['worst_month']:+.3f}")
        return p

    print(f"FX carry - {P.index[0].date()}..{P.index[-1].date()}  pairs={list(PAIRS)}\n")
    pc = rep(*build(P, rates, "carry"), "H7 carry")
    pr = rep(*build(P, rates, "random", seed=11), "random-sign null")
    pu = rep(*build(P, rates, "longUSD"), "long-USD only")

    # by year
    net, eq = build(P, rates, "carry")
    if a.eval_start:
        net = net[(net.index >= pd.Timestamp(a.eval_start))]
    e = pd.DataFrame({"net": net}).dropna(); e["y"] = e.index.year
    yr = e.groupby("y")["net"].apply(lambda s: (1 + s).prod() - 1) * 100
    print("\n  by year %:", {int(k): round(v, 1) for k, v in yr.items()})
    h1 = (1 + e[e.index < "2016-01-01"]["net"]).prod() - 1
    h2 = (1 + e[e.index >= "2016-01-01"]["net"]).prod() - 1
    if not a.eval_start:
        print(f"  half 2009-15: {h1*100:+.1f}%   half 2016-22: {h2*100:+.1f}%")

    print("\n  verdict vs bars: single-book Sharpe>=0.5 (6a) / >=1.0 (6b);  beats random-sign;  "
          f"result Sharpe={pc['sharpe']:.2f}  beats_random={pc['sharpe']>pr['sharpe']+0.2}")


if __name__ == "__main__":
    main()
