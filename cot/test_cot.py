"""
CFTC Commitments-of-Traders positioning-extreme test for gold.

Data (pulled from publicreporting.cftc.gov Socrata API):
  cot/gold_cot_legacy.csv   - Legacy report, GOLD COMEX (code 088691), 1995+ weekly
  cot/gold_cot_disagg.json  - Disaggregated report, 2006+ weekly (Managed Money)

Signal idea: large speculators (Legacy "Non-Commercial" / Disagg "Managed Money")
are trend-chasers; when their net position is at a multi-year extreme it marks
local exhaustion -> fade it. Commercials (producers/hedgers) are the mirror.

Mechanics:
  - COT report is dated Tuesday, released ~Fri 15:30 ET. First tradeable gold
    close = the following Monday -> signal applied with that lag (no lookahead).
  - Weekly holding; gold weekly return from one tradeable close to the next.
  - Cost 2 bps per unit |change in position| (weekly rebalance, low turnover).
  - Windows: in-sample 2009-2022 (project frozen split; also show 2007-2022),
    walk-forward 2023, recent 2024-2026. vs buy&hold and a random-sign null.
"""
import json
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ANN_W = 52
COST_BPS = 2.0
Z_WIN = 156          # 3-year trailing window for the z-score / rank
EXTREME_Q = 0.20     # top/bottom quintile = "extreme"


def load_gold():
    g = pd.read_parquet("basket/XAUUSD.parquet")[["close"]]
    g.index = pd.to_datetime(g.index).tz_localize(None).normalize()
    return g[~g.index.duplicated()].sort_index()["close"]


def load_cot():
    lg = pd.read_csv("cot/gold_cot_legacy.csv", parse_dates=["date"]).set_index("date").sort_index()
    lg["spec_net"] = lg["noncomm_positions_long_all"] - lg["noncomm_positions_short_all"]
    lg["comm_net"] = lg["comm_positions_long_all"] - lg["comm_positions_short_all"]
    lg["smalls_net"] = lg["nonrept_positions_long_all"] - lg["nonrept_positions_short_all"]
    lg["spec_pct"] = lg["spec_net"] / lg["open_interest_all"]
    lg["comm_pct"] = lg["comm_net"] / lg["open_interest_all"]
    lg["smalls_pct"] = lg["smalls_net"] / lg["open_interest_all"]

    dz = pd.DataFrame(json.load(open("cot/gold_cot_disagg.json")))
    dz["date"] = pd.to_datetime(dz["report_date_as_yyyy_mm_dd"]).dt.tz_localize(None)
    for c in ("open_interest_all", "m_money_positions_long_all", "m_money_positions_short_all"):
        dz[c] = pd.to_numeric(dz[c])
    dz = dz.set_index("date").sort_index()
    lg["mm_net"] = dz["m_money_positions_long_all"] - dz["m_money_positions_short_all"]
    lg["mm_pct"] = lg["mm_net"] / dz["open_interest_all"]
    return lg


def zscore(s, win=Z_WIN):
    return (s - s.rolling(win, min_periods=win // 2).mean()) / s.rolling(win, min_periods=win // 2).std()


def rank_pct(s, win=Z_WIN):
    return s.rolling(win, min_periods=win // 2).apply(lambda x: (x.iloc[-1] > x[:-1]).mean(), raw=False)


def align_to_gold(cot_weekly_signal, gold):
    """Map each weekly COT signal to the first tradeable gold close (Tue report
    + 4 cal days -> next available gold trading day), then forward-fill across
    the week. Returns a daily-indexed position series aligned to `gold`."""
    gi = gold.index
    rows = {}
    for dt, val in cot_weekly_signal.dropna().items():
        eff = dt + pd.Timedelta(days=4)                # Tue -> Sat; roll fwd to a trading day
        pos = gi.searchsorted(eff)
        if pos < len(gi):
            rows[gi[pos]] = val
    s = pd.Series(rows).sort_index()
    return s.reindex(gi).ffill()


def backtest(pos_daily, gold, label, results):
    """pos_daily in [-1,1], known at close t, earns close t -> t+1w? No: we hold
    daily, earn daily gold return, rebalance whenever the weekly signal updates."""
    ret = gold.pct_change().shift(-1)                  # close t -> close t+1
    sig = pos_daily.reindex(gold.index).ffill().fillna(0.0).clip(-1, 1)
    gross = sig * ret
    cost = sig.diff().abs().fillna(sig.abs()) * COST_BPS / 1e4
    daily = (gross - cost).shift(1).dropna()
    results[label] = daily


def report(results, bench):
    wins = [("in-sample 09-22", "2009-01-01", "2023-01-01"),
            ("(also 07-22)", "2007-01-01", "2023-01-01"),
            ("walk-fwd 2023", "2023-01-01", "2024-01-01"),
            ("recent 24-26", "2024-01-01", "2027-01-01"),
            ("ALL", "1900-01-01", "2100-01-01")]
    for label, daily in results.items():
        print(f"  {label}")
        for wn, lo, hi in wins:
            r = daily[(daily.index >= lo) & (daily.index < hi)].dropna()
            if len(r) < 60:
                continue
            n_yr = len(r) / 252
            cagr = (1 + r).prod() ** (1 / n_yr) - 1
            shp = r.mean() / r.std() * np.sqrt(252) if r.std() else 0
            eq = (1 + r).cumprod()
            dd = (eq / eq.cummax() - 1).min()
            b = bench[(bench.index >= lo) & (bench.index < hi)].dropna()
            bc = (1 + b).prod() ** (1 / (len(b) / 252)) - 1 if len(b) else np.nan
            act = r[r != 0]
            hit = (act > 0).mean() if len(act) else np.nan
            print(f"    {wn:16s} CAGR={cagr:+6.1%} Sharpe={shp:+5.2f} maxDD={dd:6.1%} "
                  f"hit={hit:4.0%}  [B&H CAGR {bc:+.1%}]")
        print()


def predictive_check(sigval, gold):
    """Raw: does the weekly signal predict the NEXT week's gold return?
    Uses the release-lagged mapping, quintiles of the signal."""
    gw = gold.resample("W-FRI").last()
    fwd = gw.pct_change().shift(-1)
    s = align_to_gold(sigval, gold).resample("W-FRI").last()
    df = pd.concat([s.rename("sig"), fwd.rename("fwd")], axis=1).dropna()
    df = df[df.index < "2023-01-01"]                    # in-sample only
    q = pd.qcut(df["sig"], 5, labels=[1, 2, 3, 4, 5])
    g = df.groupby(q)["fwd"].agg(["mean", "count"])
    ic = df["sig"].corr(df["fwd"], method="spearman")
    print(f"    in-sample Spearman IC(signal, next-wk gold ret) = {ic:+.3f}")
    print("    next-week gold return by signal quintile (Q1=most short-spec / Q5=most long-spec):")
    for qi, row in g.iterrows():
        print(f"      Q{qi}: {row['mean']*1e4:+6.1f} bps   (n={int(row['count'])})")
    print()


if __name__ == "__main__":
    gold = load_gold()
    cot = load_cot()
    bench = gold.pct_change().shift(-1).shift(1).dropna()   # buy&hold daily

    print("=" * 78)
    print("CFTC COT POSITIONING-EXTREME TEST  — GOLD (COMEX 088691)")
    print(f"  COT weekly {cot.index.min().date()}..{cot.index.max().date()}   "
          f"gold daily {gold.index.min().date()}..{gold.index.max().date()}")
    print("=" * 78)

    # ---- raw predictive check on the core signal --------------------------
    print("RAW PREDICTIVE CHECK (large-spec net % of OI):")
    predictive_check(cot["spec_pct"], gold)

    # ---- strategy variants ----------------------------------------------
    R = {}

    # 1. continuous fade of the spec z-score
    z = zscore(cot["spec_pct"])
    backtest(align_to_gold((-z / 1.5).clip(-1, 1), gold), gold, "1. fade spec z-score (continuous)", R)

    # 2. spec extreme quintile: short at top, long at bottom, else flat
    rk = rank_pct(cot["spec_pct"])
    disc = pd.Series(0.0, index=rk.index)
    disc[rk > 1 - EXTREME_Q] = -1.0
    disc[rk < EXTREME_Q] = 1.0
    backtest(align_to_gold(disc, gold), gold, "2. fade spec extreme quintile (±1 / flat)", R)

    # 3. follow commercials (hedgers) z-score
    zc = zscore(cot["comm_pct"])
    backtest(align_to_gold((zc / 1.5).clip(-1, 1), gold), gold, "3. FOLLOW commercial z-score", R)

    # 4. Managed Money (disaggregated) extreme quintile fade
    rkm = rank_pct(cot["mm_pct"])
    dm = pd.Series(0.0, index=rkm.index)
    dm[rkm > 1 - EXTREME_Q] = -1.0
    dm[rkm < EXTREME_Q] = 1.0
    backtest(align_to_gold(dm, gold), gold, "4. fade Managed-Money extreme quintile", R)

    # 5. fade the weekly CHANGE in spec net (flow, not level)
    dz_ = zscore(cot["spec_pct"].diff())
    backtest(align_to_gold((-dz_ / 1.5).clip(-1, 1), gold), gold, "5. fade weekly change in spec net", R)

    # 6. spec extreme AND commercial extreme agree (both point same way)
    both = pd.Series(0.0, index=rk.index)
    rc = rank_pct(cot["comm_pct"])
    both[(rk > 1 - EXTREME_Q) & (rc < EXTREME_Q)] = -1.0      # specs max long, comms max short -> short gold
    both[(rk < EXTREME_Q) & (rc > 1 - EXTREME_Q)] = 1.0
    backtest(align_to_gold(both, gold), gold, "6. spec extreme AND commercial extreme agree", R)

    # 7. benchmark: always long gold
    backtest(pd.Series(1.0, index=gold.index), gold, "7. always-long gold (bench)", R)

    # 8. random-sign weekly null (avg of 200 seeds)
    rs = []
    wk = pd.date_range(cot.index.min(), cot.index.max(), freq="W-TUE")
    for seed in range(200):
        rng = np.random.default_rng(seed)
        rnd = pd.Series(rng.choice([-1.0, 1.0], len(wk)), index=wk)
        tmp = {}
        backtest(align_to_gold(rnd, gold), gold, "_", tmp)
        rs.append(tmp["_"])
    R["8. random-sign weekly null (mean of 200)"] = pd.concat(rs, axis=1).mean(axis=1)

    print("STRATEGY RESULTS")
    print("-" * 78)
    report(R, bench)
