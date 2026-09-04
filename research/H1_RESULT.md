# H1 result — NY opening-range breakout (in-sample 2009–2022)

_run 2026-09-04 09:43 UTC · 5min bars · Dukascopy canonical_

## Headline (fixed 0.01-lot run)
```
  n_trades                   3267
  win_rate                   43.495561677379854
  expectancy_usd             -0.21002016707608975
  expectancy_r               -0.04913858724066388
  profit_factor              0.9090845800529435
  avg_win_usd                4.82817272538099
  avg_loss_usd               -4.088282409861307
  avg_bars_held              31.859504132231404
  total_cost_usd             1409.7176733375927
  gross_pnl_usd              723.5817875000076
  net_pnl_usd                -686.1358858375852
  cost_drag_pct_of_gross     194.8249247964354
  exit_reason_mix            {'stop': 1329, 'session_flat': 990, 'target': 948}
```

## 0.5%-risk run (drawdown picture, $1,000 start)
```
  final_equity               228.0866118905584
  total_return_pct           -77.19133881094416
  max_drawdown_pct           93.92604706244627
  max_dd_duration_days       5036.215277777777
  sharpe                     -0.14627303361160576
  sortino                    -0.1909466691667998
```

## Success bar
```
              metric     value op  threshold pass
    max_drawdown_pct   93.9260 <=      20.00 FAIL
max_dd_duration_days 5042.2014 <=      95.00 FAIL
       profit_factor    0.9091 >=       1.25 FAIL
              sharpe   -0.2421 >=       1.00 FAIL
             sortino   -0.3326 >=       1.50 FAIL
      expectancy_usd   -0.2100  >       0.00 FAIL
            n_trades 3267.0000 >=     300.00 PASS

  ALL PASS: False
```

## H1 vs NULL (same-time random-direction entry)
```
  H1   trades= 3267  mean R = -0.0491   expectancy $ = -0.2100   PF = 0.909
  NULL trades= 2311  mean R = -0.1179   expectancy $ = -0.4336   PF = 0.811
  Welch t (H1 vs NULL, per-trade R): t = +2.36   (>|2| = distinguishable)
```

## Monte-Carlo (resample trade order, fixed-lot)
```
  final_equity_p05         -196.94590204182714
  final_equity_p50         322.9341281246086
  final_equity_p95         810.379246583836
  prob_profit              0.014
  max_dd_pct_p50           75.42761070137755
  max_dd_pct_p95           122.63868725977508
```

## Expectancy by year (fixed-lot)
```
        n  exp_usd  exp_R  win_rate
year                               
2009  225   -0.661 -0.159    40.000
2010  234   -0.403 -0.119    41.026
2011  241   -0.518 -0.046    44.398
2012  234   -0.281 -0.043    44.444
2013  222    0.281  0.055    49.099
2014  229   -0.301 -0.085    40.611
2015  232    0.234  0.058    46.983
2016  240   -0.264 -0.063    41.250
2017  235   -0.020 -0.025    43.830
2018  235   -0.332 -0.169    40.000
2019  236    0.057  0.004    45.763
2020  239   -0.803 -0.130    40.167
2021  233   -0.279 -0.016    44.635
2022  232    0.385  0.055    46.983
```

## Verdict

**KILL** — does not clear the M3 bar. Recorded as a clean negative; draft H2.

Reasons: success bar not all-PASS; PF 0.909 < 1.25; expectancy ≤ 0 after costs; MC median not profitable
---

## Interpretation (added 2026-09-04)

**KILL — but an *informative* negative, not a nothing.**

1. **The breakout direction carries real information.** H1 beats the same-time
   random-direction null: mean R −0.049 vs −0.118, Welch **t = +2.36** (> 2). And
   **gross PnL is +$724** over 3,267 trades ≈ **+0.22 $/trade ≈ +0.05 R/trade
   before costs**. The core mechanism (break of the 13:30–14:00 UTC range tends to
   continue) is not noise.

2. **The edge is smaller than the transaction cost.** Gross ≈ +0.05 R/trade vs
   cost ≈ **−0.10 R/trade** ($1,410 total ≈ $0.43/trade). Net −0.049 R. Cost drag
   is **195 % of gross profit** — this strategy is a machine for paying spread.

3. **No stable regime.** Net expectancy_R is positive only in 2013, 2015, 2019,
   2022; worst in 2020 (−0.13 R, COVID chop). Trend-continuation off the NY open
   is not a persistent gold feature at this frequency.

4. Exit mix: 41 % stopped, 29 % hit the 1.5 R target, 30 % timed out at 20:00 UTC.
   Win rate 43.5 % with a ~1.18 : 1 win/loss size ratio → just short of break-even
   even before costs.

**What this rules out / suggests:**
- A high-frequency (one-per-day), tight-target ORB on 5-min gold does **not** clear
  the cost hurdle and should not be pursued further as specified.
- If an ORB-family idea is revisited (a *deliberate* iteration 2, not a reflex), it
  would need **far fewer, higher-conviction entries** (so cost drag collapses)
  and/or a **much larger average win** (wide target or trail-to-flat) to clear
  ~0.10 R of cost. That is a different hypothesis, to be drafted and dated as such.

**Decision:** record H1 as killed. Proceed to **H2** (London→NY momentum
continuation) unless a targeted H1 iteration is explicitly chosen.
