# H1b result - H1 iteration 2 (close-confirmed break + daily bias + trail)

_run 2026-09-04 09:49 UTC - 5min bars, in-sample_

## Headline (fixed 0.01-lot)
```
  n_trades                   2405
  win_rate                   42.91060291060291
  expectancy_usd             -0.20828702145676062
  expectancy_r               -0.05086019873204764
  profit_factor              0.9040831166784665
  avg_win_usd                4.575208532420991
  avg_loss_usd               -3.8037476271390904
  avg_bars_held              32.63659043659044
  total_cost_usd             1034.0096616035114
  gross_pnl_usd              533.079375000002
  net_pnl_usd                -500.9302866035093
  cost_drag_pct_of_gross     193.96917421603632
  exit_reason_mix            {'stop': 1595, 'session_flat': 810}
```

## 0.5%-risk run ($1,000)
```
  final_equity               392.01634589492176
  total_return_pct           -60.79836541050783
  max_drawdown_pct           70.6162457555787
  max_dd_duration_days       5035.263888888889
  sharpe                     -0.4038622925505497
  sortino                    -0.6323825405707101
```

## Success bar
```
              metric     value op  threshold pass
    max_drawdown_pct   70.6162 <=      20.00 FAIL
max_dd_duration_days 5035.2639 <=      95.00 FAIL
       profit_factor    0.9041 >=       1.25 FAIL
              sharpe   -0.3852 >=       1.00 FAIL
             sortino   -0.5753 >=       1.50 FAIL
      expectancy_usd   -0.2083  >       0.00 FAIL
            n_trades 2405.0000 >=     300.00 PASS

  ALL PASS: False
```

## H1b vs NULL (random dir, same days, same trailing exit)
```
  H1b  trades= 2405  mean R = -0.0509  expectancy $ = -0.2083  PF = 0.904
  NULL trades= 2560  mean R = -0.0869  expectancy $ = -0.3910  PF = 0.829
  Welch t (per-trade R): t = +1.01   (>|2| = distinguishable)
```

## Monte-Carlo (resample trade order)
```
  final_equity_p05         51.283675360563926
  final_equity_p50         498.15179306684377
  final_equity_p95         963.3877553866904
  prob_profit              0.038
  max_dd_pct_p50           59.095813059153784
  max_dd_pct_p95           99.71726975384111
```

## Expectancy by year
```
        n  exp_usd  exp_R  win_rate
year                               
2009  167   -0.447 -0.147    40.719
2010  182    0.394  0.101    45.604
2011  186   -0.464 -0.120    41.398
2012  177    0.084  0.028    45.763
2013  164    0.292  0.034    42.073
2014  152   -0.172 -0.045    40.789
2015  166   -0.305 -0.075    42.169
2016  169   -0.505 -0.100    42.604
2017  181    0.086  0.087    45.304
2018  175   -0.541 -0.234    39.429
2019  165    0.291  0.061    44.242
2020  177   -1.102 -0.194    39.548
2021  176   -0.838 -0.162    40.909
2022  168    0.366  0.058    50.000
```

## Verdict

**KILL** - success bar not all-PASS; null t=+1.01; PF 0.904 < 1.25; expectancy <= 0 after costs
---

## Interpretation (added 2026-09-04)

**KILL — and the more important finding: the "improvements" destroyed the edge.**

| | H1 (iter 1) | H1b (iter 2) |
|---|---|---|
| trades | 3,267 | 2,405 (−26%) |
| gross PnL | +$724 | +$533 (−26%) |
| costs | $1,410 | $1,034 |
| net expectancy | −0.049 R | −0.051 R |
| **Welch t vs random-direction null** | **+2.36 (distinguishable)** | **+1.01 (NOT distinguishable)** |
| avg win / avg loss | 4.83 / −4.09 | 4.58 / −3.80 |

1. **The filters removed signal, not noise.** Close-confirmed break + daily-bias
   alignment cut trade count ~26% and cut gross PnL ~26% — *proportionally*. The
   trades we excluded (late breaks, counter-daily-trend breaks) carried just as
   much edge as the ones we kept. Being "selective" here threw away the thing that
   beat the null.
2. **The trailing exit did not let winners run.** avg win actually *fell*
   ($4.83 → $4.58); the 1×OR-height trail gets tagged on ordinary pullbacks before
   any big continuation. 810 session-flats (vs 990 in H1) and zero targets.
3. **Net effect: t-stat collapsed 2.36 → 1.01.** H1b is statistically
   indistinguishable from a coin flip at the same time and size.

**Conclusion for the H1 / ORB family:** the H1 null-beat was real but *thin and
non-robust* — it lived only in the undifferentiated aggregate of all NY-open
breaks, and every attempt to sharpen or extend it removed it. This is the
p-hacking cliff the charter warns about. **Stop the ORB line** (2 of 5 iterations
used, iteration 2 made it worse). Both H1 and H1b recorded as clean negatives.

**Decision: proceed to H2** (London→NY momentum continuation) — a different
mechanism.
