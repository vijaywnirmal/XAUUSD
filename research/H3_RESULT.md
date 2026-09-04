# H3 result - Asian-quiet -> NY range expansion (in-sample 2009-2022)

_run 2026-09-04 10:08 UTC - 5min bars, Dukascopy canonical_

## Mechanism check (independent of trade rules)
```
  n_quiet                    1095
  n_nonquiet                 2508
  ny_norm_median_quiet       0.79
  ny_norm_median_nonquiet    0.889
  ny_norm_mean_quiet         0.889
  ny_norm_mean_nonquiet      1.006
  -> quiet nights SHOULD show a larger realised NY range (ny_norm) than non-quiet
```

## Headline (fixed 0.01-lot, quiet days, two-sided)
```
  n_trades                   1088
  win_rate                   39.52205882352941
  expectancy_usd             -0.3389946588974558
  expectancy_r               -0.02890728722640847
  profit_factor              0.8902248790395663
  avg_win_usd                6.95583222742288
  avg_loss_usd               -5.106130770018648
  avg_bars_held              81.27573529411765
  total_cost_usd             491.9324888804333
  gross_pnl_usd              123.1063000000014
  net_pnl_usd                -368.8261888804319
  cost_drag_pct_of_gross     399.5997677457837
  exit_reason_mix            {'stop': 764, 'session_flat': 324}
```

## 0.5%-risk run ($1,000)
```
  final_equity               631.0423688429208
  total_return_pct           -36.895763115707915
  max_drawdown_pct           41.09419391547716
  max_dd_duration_days       4980.388888888889
  sharpe                     -0.27910441217292475
  sortino                    -0.4075304173295464
```

## Success bar
```
              metric     value op  threshold pass
    max_drawdown_pct   41.0942 <=      20.00 FAIL
max_dd_duration_days 4979.3854 <=      95.00 FAIL
       profit_factor    0.8902 >=       1.25 FAIL
              sharpe   -0.2877 >=       1.00 FAIL
             sortino   -0.4029 >=       1.50 FAIL
      expectancy_usd   -0.3390  >       0.00 FAIL
            n_trades 1088.0000 >=     300.00 PASS

  ALL PASS: False
```

## H3 vs comparisons - per-trade R
```
  H3 (quiet, two-sided)     n=1088  mean R = -0.0289   expectancy $ = -0.3390   PF = 0.890
  UNCONDITIONAL (all days)  n=3475  mean R = +0.0119   expectancy $ = +0.1633   PF = 1.047
  COIN-FLIP straddle        n= 804  mean R = +0.0144   expectancy $ = +0.0925   PF = 1.031
  Welch t  H3 vs UNCOND = -0.80   H3 vs COINFLIP = -0.61
  PASS needs: H3 mean R > UNCOND mean R  AND  H3 mean R > COINFLIP mean R
```

## Whipsaw slice (stopped <= 60 min after entry)
```
  fast stop-outs: 51 of 1088 (5%)  mean net $ = -5.389
```

## Monte-Carlo (resample trade order)
```
  final_equity_p05         212.04170965682152
  final_equity_p50         624.5267315090534
  final_equity_p95         1062.5812757338533
  prob_profit              0.076
  max_dd_pct_p50           47.33397610459889
  max_dd_pct_p95           82.6623117752297
```

## Expectancy by year
```
       n  exp_usd  exp_R  win_rate
year                              
2009  44   -1.100 -0.226    36.364
2010  78   -1.679 -0.364    28.205
2011  82   -0.108 -0.048    36.585
2012  81   -1.338 -0.187    37.037
2013  88    0.443  0.169    38.636
2014  73    0.471  0.070    41.096
2015  75    1.683  0.520    57.333
2016  81   -0.118  0.030    39.506
2017  88   -0.598 -0.174    39.773
2018  80    0.037  0.025    43.750
2019  84   -0.033 -0.046    42.857
2020  72   -1.419 -0.184    33.333
2021  82   -0.809 -0.030    37.805
2022  80   -0.516 -0.033    40.000
```

## Verdict

**KILL** - success bar not all-PASS; does NOT beat unconditional (H3 R -0.0289 <= all-days R +0.0119) -> quiet gate adds nothing; does NOT beat coin-flip straddle (H3 R -0.0289 <= +0.0144); PF 0.890 < 1.25; expectancy <= 0 after costs; MC median not profitable
---

## Interpretation (added 2026-09-04)

**KILL — the most decisive falsification of the three. Fails at every level.**

1. **Core mechanism is backwards.** NY range (ATR-normalised, independent of any
   trade rule): mean **0.889 after quiet Asian nights vs 1.006 after non-quiet**.
   A quiet Asian night is followed by a *smaller* NY range. **Gold's intraday
   volatility persists across sessions — it does not contract-then-expand.** The
   NR7 / squeeze intuition (which works on *daily* bars in equities) does not
   transfer to the intra-day session scale here.

2. **The quiet gate is actively harmful.** The *same straddle traded on ALL days*
   (unconditional) has mean R **+0.012 / expectancy +$0.16 / PF 1.05** — better
   than the quiet-conditioned H3 (mean R −0.029 / −$0.34 / PF 0.89). Conditioning
   on "quiet" selects the wrong days. It also loses to a coin-flip one-sided
   straddle. Welch t vs both comparisons is negative.

3. Rides on 2015 alone (+0.52 R); MC prob(profit) 0.076.

**Side note:** the *unconditional* always-on Asian-range straddle (trail to 21:00)
is the least-bad thing found so far — roughly break-even (expectancy +$0.16/trade,
PF 1.05 over 3,475 trades). It still fails the success bar comfortably (needs
PF ≥ 1.25, expectancy ≥ +0.08 R) and is thin noise near zero, not an edge — but
it is the first non-negative number in the M3 log.

---

## M3 status after H1 + H2 + H3

Three hypotheses, all killed:

| | Idea | Why it died |
|---|---|---|
| H1/H1b | NY opening-range **breakout** | thin break-direction edge (t=+2.36), smaller than cost; non-robust to any sharpening |
| H2 | London→NY momentum **continuation** | London direction carries *no* info about NY direction (t=−0.49 vs random) |
| H3 | Asian-quiet → NY range **expansion** | mechanism reversed — gold intraday vol *persists*, doesn't expand; gate is counter-productive |

**Through-line:** at the 5-min / daily-session scale on gold 2009–2022, with
realistic costs (~0.10 R/trade), the classic intraday session structures
(breakout, momentum, volatility-cycle) do **not** contain an extractable
directional edge. Costs are a hard wall for anything trading ~once/day at modest R.

**Decision point for the operator:**
- **Continue intraday** with a genuinely different angle — **H4 = calendar / event**
  (turn-of-month gold strength, day-of-week, pre/post-FOMC 19:00 UTC drift,
  NFP-day behaviour). Last untested category; some have academic support.
- **Or reconsider the intraday premise** — 3 fair tests of NY-session direction
  have failed; a swing / daily-bar trend or drift system (charter's "later" phase)
  may be where the edge actually is.
