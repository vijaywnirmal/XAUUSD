# H2 result - London->NY momentum continuation (in-sample 2009-2022)

_run 2026-09-04 09:57 UTC - 5min bars, Dukascopy canonical_

## Headline (fixed 0.01-lot)
```
  n_trades                   656
  win_rate                   42.68292682926829
  expectancy_usd             -0.08882903627731002
  expectancy_r               -0.04839678901684301
  profit_factor              0.9792026021902405
  avg_win_usd                9.7986065235006
  avg_loss_usd               -7.451812963771501
  avg_bars_held              79.58384146341463
  total_cost_usd             296.800847797918
  gross_pnl_usd              238.5290000000025
  net_pnl_usd                -58.27184779791537
  cost_drag_pct_of_gross     124.42967010213218
  exit_reason_mix            {'session_flat': 460, 'stop': 196}
```

## 0.5%-risk run ($1,000)
```
  final_equity               941.7281522020845
  total_return_pct           -5.8271847797915495
  max_drawdown_pct           33.426611752742296
  max_dd_duration_days       3207.402777777778
  sharpe                     -0.0160712263011431
  sortino                    -0.013040660086235148
```

## Success bar
```
              metric     value op  threshold pass
    max_drawdown_pct   33.4266 <=      20.00 FAIL
max_dd_duration_days 3207.4028 <=      95.00 FAIL
       profit_factor    0.9792 >=       1.25 FAIL
              sharpe   -0.0161 >=       1.00 FAIL
             sortino   -0.0130 >=       1.50 FAIL
      expectancy_usd   -0.0888  >       0.00 FAIL
            n_trades  656.0000 >=     300.00 PASS

  ALL PASS: False
```

## H2 (trend) vs baselines — per-trade R
```
  TREND   n= 656  mean R = -0.0484   expectancy $ = -0.0888   PF = 0.979
  RANDOM  n= 653  mean R = +0.0746   expectancy $ = -0.3208   PF = 0.900
  FADE    n= 648  mean R = -0.2959   expectancy $ = -0.4901   PF = 0.764
  Welch t  TREND vs RANDOM = -0.49   TREND vs FADE = +0.91   (>|2| = distinguishable)
```

## Data-reversal slice (stopped <= 90 min after entry)
```
  fast stop-outs: 40 of 656  (6%)  mean net $ = -9.368
  everything else: 616  mean net $ = +0.514
```

## Monte-Carlo (resample trade order)
```
  final_equity_p05         442.60742874168943
  final_equity_p50         942.2660297635681
  final_equity_p95         1446.8879312405209
  prob_profit              0.42
  max_dd_pct_p50           31.30465565701141
  max_dd_pct_p95           65.40373516486936
```

## Expectancy by year
```
       n  exp_usd  exp_R  win_rate
year                              
2009  67   -0.610 -0.067    49.254
2010  51    0.729  0.061    47.059
2011  68    2.177  0.132    44.118
2012  36   -1.627 -0.164    44.444
2013  44    5.666  0.362    59.091
2014  48   -1.391 -0.145    35.417
2015  43   -0.651 -0.092    41.860
2016  37   -0.381 -0.021    43.243
2017  32   -1.333 -0.187    40.625
2018  57   -2.133 -0.334    24.561
2019  45    0.362 -0.001    40.000
2020  38    0.191 -0.011    47.368
2021  40   -1.357 -0.119    42.500
2022  50   -1.790 -0.151    40.000
```

## Verdict

**KILL** - success bar not all-PASS; vs random t=-0.49; PF 0.979 < 1.25; expectancy <= 0 after costs
---

## Interpretation (added 2026-09-04)

**KILL — a clean, decisive negative. The mechanism is falsified, not the tuning.**

1. **The London move direction carries essentially no information about the NY
   session direction.** TREND mean R −0.048 vs RANDOM mean R +0.075 → Welch
   **t = −0.49**: trading with the London trend is *indistinguishable from a coin
   flip* (and, this seed, marginally worse). It is also not a reversion signal —
   the FADE is the worst of the three (−0.30 R).

2. **Closer to break-even than H1, but for the wrong reason.** Gross PnL +$239
   (+~0.03 R/trade), cost $297 → net −$58, cost drag "only" 124 %. The strategy is
   near-zero because it is *near-random*, not because it has an edge that costs
   just barely eat.

3. **Rides on one regime.** Net expectancy_R is strongly positive only in 2011
   (+0.13) and 2013 (**+0.36**, 44 trades, +$5.67/trade). 2013 alone carries much
   of the P&L; strip it and H2 is plainly a loser. 2017 (−0.19), 2018 (−0.33),
   2021 (−0.12), 2022 (−0.15) are badly negative. MC prob(profit) = 0.42, median
   final equity $942 (< start).

4. Fast data-reversal stop-outs (≤ 90 min) are only 6 % of trades (−$9.4 each);
   the other 94 % average just +$0.51 — the problem is the whole distribution, not
   a tail.

**Conclusion:** London→NY directional continuation does not exist in gold at the
5-min / daily-session scale on 2009–2022. No iteration warranted — the hypothesis
itself is falsified. → **H3.**

### Meta-note after H1 + H2

Two purely-directional intraday session hypotheses (breakout, continuation) have
now failed the same way: near-break-even gross edge, no robust directional
information, indistinguishable from random once costs and the null are applied.
Gold's NY-session *direction* looks close to a random walk at this scale. H3
should move away from pure direction — candidates: a **volatility / range**
pattern (e.g. is a quiet Asian session followed by an expanded NY range?), a
**mean-reversion** setup at a finer (intra-hour) scale, or a **calendar / event**
effect (day-of-week, pre/post FOMC) — something where the edge is not "guess the
next 6 hours of direction".
