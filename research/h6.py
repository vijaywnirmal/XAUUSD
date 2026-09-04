"""
H6 - multi-instrument trend book (managed-futures style). See H6_multi_instrument_trend.md.

Per instrument: 3m+12m sign blend, vol-targeted. Portfolio: sum the sleeves, then
scale the whole book to 12% annualised vol. Daily rebalance, no stops.

    python -m research.h6           # in-sample 2009-2022
    python -m research.h6 --start 2013-01-01
"""
import argparse
import os
import numpy as np
import pandas as pd

from data_pipeline import config as C
from research.fetch_basket import CLASS

BASKET_DIR = os.path.join(C.ROOT, "basket")
MOM_FAST, MOM_SLOW, VOL_WIN = 63, 252, 20
SIGMA_INST = 0.10
INST_CAP = 4.0
PORT_VOL_TARGET = 0.12
PORT_LEV_CAP = 3.0
CARRY_ANN = 0.02
TRADING_DAYS = 252
COST_BP = {"fx": 0.6e-4, "metal": 1.5e-4, "index": 1.5e-4, "energy": 4.0e-4}
IN_SAMPLE_END = "2023-01-01"


def load_panel(start, end):
    closes = {}
    for f in sorted(os.listdir(BASKET_DIR)):
        if not f.endswith(".parquet"):
            continue
        name = f[:-8]
        d = pd.read_parquet(os.path.join(BASKET_DIR, f))
        closes[name] = d["close"]
    px = pd.DataFrame(closes).sort_index()
    px = px[(px.index >= start) & (px.index < end)]
    # business-day grid, forward-fill gaps up to 3 days (holidays), then require real data
    px = px.asfreq("B").ffill(limit=3)
    return px


def sleeves(px):
    """Return dict of per-instrument series: ret, weight w (pre portfolio-scaling)."""
    out = {}
    for name in px.columns:
        p = px[name].dropna()
        if len(p) < MOM_SLOW + VOL_WIN + 50:
            continue
        ret = np.log(p).diff()
        sig = 0.5 * (np.sign(p / p.shift(MOM_FAST) - 1) + np.sign(p / p.shift(MOM_SLOW) - 1))
        rvol = ret.rolling(VOL_WIN).std() * np.sqrt(TRADING_DAYS)
        w = (sig * (SIGMA_INST / rvol)).clip(-INST_CAP, INST_CAP).shift(1)   # tradable day t
        out[name] = dict(ret=ret.reindex(px.index), w=w.reindex(px.index))
    return out


def portfolio(px, slv, sign_override=None, drop=None, seed=0):
    """Build the vol-targeted book. sign_override: 'random' -> random daily signs;
    'long' -> all +1 (equal-risk buy&hold). drop: instrument name to exclude."""
    idx = px.index
    names = [n for n in slv if n != drop]
    rng = np.random.default_rng(seed)
    W = pd.DataFrame(index=idx)
    RET = pd.DataFrame(index=idx)
    for n in names:
        w = slv[n]["w"].copy()
        r = slv[n]["ret"].copy()
        if sign_override == "random":
            rs = pd.Series(rng.choice([-1.0, 1.0], size=len(idx)), index=idx)
            w = (rs * (w.abs())).where(w.notna())
        elif sign_override == "long":
            w = (w.abs()).where(w.notna())
        W[n], RET[n] = w, r
    active = W.notna().sum(axis=1)
    gross = (W.fillna(0) * RET.fillna(0)).sum(axis=1)
    port_rvol = (gross.rolling(VOL_WIN).std() * np.sqrt(TRADING_DAYS)).shift(1)
    k = (PORT_VOL_TARGET / port_rvol).clip(upper=PORT_LEV_CAP).fillna(0.0)
    # costs
    Wk = W.fillna(0).mul(k, axis=0)
    dpos = Wk.diff().abs()
    dpos.iloc[0] = Wk.iloc[0].abs()
    cost = pd.Series(0.0, index=idx)
    for n in names:
        cost = cost + dpos[n] * COST_BP[CLASS[n]]
    carry = Wk.abs().sum(axis=1) * (CARRY_ANN / TRADING_DAYS)
    net = k * gross - cost - carry
    eq = (1.0 + net.fillna(0)).cumprod()
    # per-instrument pnl contribution
    pnl_i = {}
    for n in names:
        pnl_i[n] = float((Wk[n] * RET[n].fillna(0)).sum())
    strat_ret = (W.fillna(0) * RET.fillna(0))   # per-sleeve strategy return (pre-scale)
    return dict(net=net, equity=eq, active=active, k=k, pnl_i=pnl_i,
                strat_ret=strat_ret, gross=gross)


def perf(net, eq):
    r = net.dropna()
    n = len(r)
    cagr = eq.iloc[-1] ** (TRADING_DAYS / n) - 1 if n else 0.0
    sharpe = r.mean() / r.std() * np.sqrt(TRADING_DAYS) if r.std() > 0 else 0.0
    dn = r[r < 0].std()
    sortino = r.mean() / dn * np.sqrt(TRADING_DAYS) if dn and dn > 0 else 0.0
    peak = eq.cummax()
    mdd = float(-(eq / peak - 1).min())
    below = (eq < peak).to_numpy(); ix = eq.index
    best = 0.0; s = None
    for kk, b in enumerate(below):
        if b and s is None:
            s = ix[kk]
        elif not b and s is not None:
            best = max(best, (ix[kk] - s).days); s = None
    if s is not None:
        best = max(best, (ix[-1] - s).days)
    return dict(cagr=cagr, sharpe=sharpe, sortino=sortino, max_dd=mdd, dd_days=best,
               total_return=float(eq.iloc[-1] - 1))


def block_bootstrap(net, n_iter=2000, block=20, seed=0):
    r = net.dropna().to_numpy()
    if len(r) < block * 5:
        return {}
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(len(r) / block))
    cg, dd = [], []
    for _ in range(n_iter):
        st = rng.integers(0, len(r) - block, size=nb)
        s = np.concatenate([r[i:i + block] for i in st])[:len(r)]
        eq = np.cumprod(1 + s)
        cg.append(eq[-1] ** (TRADING_DAYS / len(s)) - 1)
        pk = np.maximum.accumulate(eq)
        dd.append(float(-(eq / pk - 1).min()))
    cg, dd = np.array(cg), np.array(dd)
    return dict(cagr_p05=float(np.percentile(cg, 5)), cagr_p50=float(np.percentile(cg, 50)),
               cagr_p95=float(np.percentile(cg, 95)), prob_pos=float((cg > 0).mean()),
               dd_p50=float(np.percentile(dd, 50)), dd_p95=float(np.percentile(dd, 95)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default=IN_SAMPLE_END)
    args = ap.parse_args()

    px = load_panel(pd.Timestamp(args.start, tz="UTC"), pd.Timestamp(args.end, tz="UTC"))
    slv = sleeves(px)
    print(f"panel {px.index[0].date()}..{px.index[-1].date()}  instruments with a signal: {len(slv)}", flush=True)

    P = portfolio(px, slv)
    pf = perf(P["net"], P["equity"])
    bh = portfolio(px, slv, sign_override="long"); bp = perf(bh["net"], bh["equity"])
    rs = portfolio(px, slv, sign_override="random", seed=7); rp = perf(rs["net"], rs["equity"])
    goldonly = portfolio(px, {k: v for k, v in slv.items() if k == "XAUUSD"})
    gp = perf(goldonly["net"], goldonly["equity"])
    bb = block_bootstrap(P["net"])

    # pnl contribution
    tot = sum(P["pnl_i"].values())
    contrib = sorted(((n, v, v / tot * 100 if tot else 0) for n, v in P["pnl_i"].items()),
                     key=lambda t: -t[1])
    # strategy-return correlation (mean off-diагonal)
    sr = P["strat_ret"].loc[:, list(slv)].replace(0, np.nan)
    cm = sr.corr()
    offdiag = cm.where(~np.eye(len(cm), dtype=bool)).stack()
    mean_rho = float(offdiag.mean())
    # leave-one-out
    loo = {}
    for n in slv:
        q = portfolio(px, slv, drop=n)
        loo[n] = perf(q["net"], q["equity"])["sharpe"]
    # by year / half
    e = pd.DataFrame({"net": P["net"]}).dropna(); e["y"] = e.index.year
    yr = e.groupby("y")["net"].apply(lambda s: (1 + s).prod() - 1) * 100
    h1 = float((1 + e[e.index < "2016-01-01"]["net"]).prod() - 1)
    h2 = float((1 + e[e.index >= "2016-01-01"]["net"]).prod() - 1)

    L = []; W = L.append
    W("# H6 result - multi-instrument trend book (in-sample "
      f"{px.index[0].year}-{px.index[-1].year})\n")
    W(f"_run {pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M} UTC - daily bars, Dukascopy - vs portfolio bar (blueprint 6b)_\n")

    W("## Headline (idealised, vol-targeted 12%)\n```")
    for k in ["total_return", "cagr", "sharpe", "sortino", "max_dd", "dd_days"]:
        W(f"  {k:14s} {pf[k]:+.4f}")
    W(f"  mean active instruments: {P['active'].mean():.1f}  (range {int(P['active'].min())}-{int(P['active'].max())})")
    W(f"  mean strategy-return pairwise corr: {mean_rho:+.3f}")
    W("```\n")

    W("## Comparisons\n```")
    W(f"  {'':18s} {'totRet':>9} {'CAGR':>8} {'Sharpe':>7} {'Sortino':>8} {'maxDD':>8}")
    for nm, x in [("H6 trend book", pf), ("equal-wt buy&hold", bp),
                  ("random-sign book", rp), ("gold-only (H5-ish)", gp)]:
        W(f"  {nm:18s} {x['total_return']:+9.2f} {x['cagr']:+8.3f} {x['sharpe']:+7.2f} {x['sortino']:+8.2f} {x['max_dd']:8.3f}")
    W("```\n")

    W("## PnL contribution by instrument\n```")
    for n, v, pct in contrib:
        W(f"  {n:8s} {CLASS[n]:6s} {pct:+6.1f}%   loo_sharpe(drop {n})={loo[n]:.2f}")
    W("```\n")

    W("## Robustness\n```")
    W(f"  half 2009-2015: {h1*100:+.1f}%     half 2016-2022: {h2*100:+.1f}%")
    for y, v in yr.items():
        W(f"    {y}  {v:+7.1f}")
    if bb:
        W(f"  block-bootstrap: CAGR p05/p50/p95 = {bb['cagr_p05']:+.3f}/{bb['cagr_p50']:+.3f}/{bb['cagr_p95']:+.3f}  "
          f"prob(CAGR>0) {bb['prob_pos']:.2f}   maxDD p50/p95 {bb['dd_p50']:.3f}/{bb['dd_p95']:.3f}")
    W("```\n")

    max_contrib = max(abs(pct) for _, _, pct in contrib)
    min_loo = min(loo.values())
    checks = {
        "sharpe >= 1.0": pf["sharpe"] >= 1.0,
        "sortino >= 1.5": pf["sortino"] >= 1.5,
        "max_dd <= 0.20": pf["max_dd"] <= 0.20,
        "dd_days <= 183": pf["dd_days"] <= 183,
        "cagr > 0": pf["cagr"] > 0,
        "positive both halves": (h1 > 0 and h2 > 0),
        "no instrument > 40% of PnL": max_contrib <= 40.0,
        "leave-one-out keeps Sharpe >= 0.8": min_loo >= 0.8,
        "beats random-sign book (Sharpe)": pf["sharpe"] > rp["sharpe"] + 0.2,
    }
    W("## Verdict (portfolio bar, blueprint 6b)\n```")
    for k, v in checks.items():
        W(f"  [{'PASS' if v else 'FAIL'}] {k}")
    W("```\n")
    W("**PASS** -> proceed to M4 (walk-forward)." if all(checks.values())
      else "**KILL** - fails: " + "; ".join(k for k, v in checks.items() if not v))

    out = os.path.join(C.ROOT, "research", "H6_RESULT.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n".join(L).encode("ascii", "replace").decode())
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
