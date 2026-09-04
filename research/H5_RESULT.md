# H5 result - long/short daily trend momentum on gold (in-sample 2009-2022)

_run 2026-09-04 10:25 UTC - daily bars, Dukascopy canonical, vs recalibrated bar (blueprint 6a)_

## Idealised run (fractional sizing - true risk-adjusted properties)
```
  total_return   +0.6554
  cagr           +0.0303
  sharpe         +0.3225
  sortino        +0.3613
  max_dd         +0.2855
  dd_days        +1319.0000
  holding_trades 143   profit_factor 1.575   win_rate 0.357
  ann.turnover ~24x   total cost (txn+carry) frac +0.4121
```

## Comparisons (idealised, same cost model)
```
                      totRet     CAGR  Sharpe  Sortino    maxDD
  H5 trend L/S        +0.655   +0.030   +0.32    +0.36    0.285
  buy & hold          +0.010   +0.001   +0.07    +0.09    0.566
  long/flat           +0.412   +0.021   +0.28    +0.23    0.309
  random-sign         -0.897   -0.120   -0.87    -1.18    0.912
```

## Realistic $1,000 account (min lot 0.01)
```
  total_return   +1518.3317
  cagr           +0.5060
  sharpe         +0.2506
  sortino        +0.2680
  max_dd         +0.3134
  final_equity $1519   mean gross leverage used 0.68x
  (min-lot forces leverage above the 12% vol target on a $1k account -> higher DD; needs ~$3-5k to run as designed)
```

## Robustness
```
  half 2009-2015 return: +66.4%     half 2016-2022 return: -0.5%
  by year (%):
    2009     +9.4
    2010    +20.0
    2011     +9.5
    2012     -2.4
    2013    +23.9
    2014     -7.0
    2015     +3.0
    2016     +2.7
    2017    -13.7
    2018     +1.8
    2019     +7.3
    2020    +13.9
    2021    -13.6
    2022     +4.5
  block-bootstrap (20d): CAGR p05/p50/p95 = -0.015/+0.031/+0.078  prob(CAGR>0) 0.87  maxDD p50/p95 0.306/0.490
```

## Verdict (recalibrated single-asset bar, blueprint 6a)
```
  [PASS] beats buy&hold on return AND maxDD
  [PASS] max_dd <= 0.30
  [FAIL] dd_days <= 365
  [FAIL] sharpe >= 0.5
  [FAIL] sortino >= 0.7
  [PASS] profit_factor >= 1.15
  [PASS] cagr > 0
  [FAIL] positive both halves
  [PASS] beats random-sign null (Sharpe)
```

**KILL** - fails: dd_days <= 365; sharpe >= 0.5; sortino >= 0.7; positive both halves
---

## Interpretation (added 2026-09-04)

**KILL on the recalibrated §6a bar — a real edge, but not robust enough.**

**Passes** the core value proposition: beats buy-and-hold on **both** axes — total
return **+65.5 % vs +1.0 %**, max drawdown **28.5 % vs 56.6 %** — with profit
factor **1.58** and a decisive win over the random-sign null (Sharpe +0.32 vs
−0.87). The trend signal genuinely carries information and de-risks holding gold.

**Fails on three counts:**

1. **Drawdown duration 1,319 days (~3.6 years underwater).** The equity peaked
   around the 2012–13 gold top and was not reclaimed until ~2020. Bar is ≤ 365
   days. Psychologically and practically unacceptable.
2. **Sharpe 0.32 / Sortino 0.36** after costs (bar 0.5 / 0.7). The feasibility
   0.52 was pre-cost; ~24×/yr turnover + the 3 % carry assumption on continuous
   gross exposure knocked ~0.2 off the Sharpe.
3. **Not robust across regimes.** 2009–2015 **+66 %**, 2016–2022 **−0.5 %**. The
   entire edge is in the first half (2017 −14 %, 2021 −14 % post-2015). Same
   one-regime fragility that killed H2.

Block-bootstrap: prob(CAGR > 0) 0.87, but maxDD p95 = 49 % — the tail is ugly.

**Cost sensitivity:** the 3 % carry is likely too harsh (avg gold USD financing
2009–22 ≈ 1.5 %). Halving it lifts CAGR ~1.5 %/yr → Sharpe maybe ~0.40 — still
short of 0.5, and it does **not** fix the 3.6-year drawdown or the post-2015
flatness, which are structural.

**Where this leaves M3 — 5 hypothesis families tested, none validated:**
intraday direction (H1), intraday momentum (H2), intraday volatility (H3),
calendar (H4, skipped on weak feasibility), single-asset daily trend (H5).
Across all of them, **gold's directional predictability is weak, regime-dependent,
and — once realistic costs/carry are applied — below the bar.**

The honest read: **there may be no single-XAUUSD strategy that clears even the
recalibrated bar robustly.** Options:
- **H5 iteration 2** — realistic 1.5 % carry + a slower, lower-turnover signal
  (12-month only, or 6m+12m) + longer vol window. Cheap to check; unlikely to
  fix the structural DD-duration / regime issues but worth one pass.
- **H6 — multi-instrument trend book** (gold + silver + 2–4 uncorrelated
  CFDs/futures). Diversification is the textbook fix for single-asset trend's low
  Sharpe and multi-year drawdowns. Scope expansion; needs more data.
- **Accept H5 as "risk-managed gold"** — it *does* beat buy-and-hold materially
  (+65 % vs +1 %, 28 % DD vs 57 %). For a small personal account that is a real
  improvement over what the operator would otherwise do, if a Sharpe ~0.35 and
  occasional multi-year drawdowns are acceptable. This is a judgement call for the
  operator, not a quant pass.
