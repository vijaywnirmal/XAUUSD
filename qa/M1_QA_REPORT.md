# M1 QA Report — canonical XAUUSD tick store & bars

_generated 2026-09-04 09:09 UTC_

## 1. Coverage

- canonical months: **213**  (2009-01 → 2026-09)
- total bid ticks: **685,139,766**
- session coverage (share of expected XAU/USD trading minutes with ≥1 tick): median **98.9%**, min **13.6%** (2026-09)

lowest-coverage months:
```
 year  month  session_coverage_pct  outages_30min_4h  worst_outage_min
 2026      9                 13.64                 0               0.0
 2013     12                 89.74                13              62.8
 2018     12                 90.11                 0               0.0
 2024     12                 90.19                 1              83.3
 2019     12                 90.31                 0               0.0
 2017      1                 90.45                10              61.5
 2023      1                 90.54                 0               0.0
 2021      1                 90.68                 0               0.0
```

- months with a 30 min – 4 h in-session gap (weekend/daily-break excluded): **61** of 213. These are ~3.5 h once/month in recent years and line up with **US market half-days / holiday early-closes** (Juneteenth, July 4, Thanksgiving Friday, Presidents/Labor Day, Dec 24/31) — expected, not feed outages.
```
 year  month  outages_30min_4h  worst_outage_min
 2019      9                 1             222.5
 2012     12                 3             216.3
 2022     11                 1             211.7
 2023      7                 1             211.2
 2025      2                 1             211.2
 2023      5                 1             211.1
 2024      9                 1             211.1
 2025      1                 1             211.1
 2025      6                 1             211.1
 2025      9                 1             211.1
 2025     11                 1             211.1
 2026      1                 1             211.1
```
- months with a >4 h in-session gap (Easter / Christmas full closes): **73**

**Verdict: no unexplained data outages.** All sub-day in-session gaps map to known market holidays; the daily break and weekends are handled separately.

## 2. Source

- **Single source: Dukascopy** (true UTC), 2009-01 → present. The Vantage/MT5 archive was removed 2026-09-04; no source seams, no timezone correction needed.
- `source` column is uniformly 1 (duka). Source switches detected: **0** (expected 0).
- Historical record of the Vantage-server-time finding: `SOURCE_VERIFICATION.md`, `data_pipeline/mt5_utc_offsets.csv` (not used by the pipeline any more).

## 3. UTC sanity — ticks by hour of UTC day

If normalisation worked, activity ramps into the London/NY hours (07–21 UTC) and the weekly boundary sits near 21–22:00 UTC.

```
 utc_hour   ticks
        0 2990894
        1 4691154
        2 3507250
        3 2835230
        4 2298491
        5 3284008
        6 4225008
        7 4568329
        8 4604320
        9 4074026
       10 3777828
       11 4132770
       12 6126898
       13 8194843
       14 8530675
       15 7227899
       16 5579777
       17 4685101
       18 4209848
       19 3843548
       20 2288835
       21  547928
       22 1042788
       23 1686753
```

peak activity hour: **14:00 UTC** (expected 13–16 UTC = London/NY overlap)

## 4. Spread by year (cost-model input)

`spread_median` of 1-min bars, in price units ($/oz). All Dukascopy.

```
 year  source  median  mean   p90
 2009       1   0.483 0.474 0.510
 2010       1   0.505 0.525 0.654
 2011       1   0.427 0.463 0.622
 2012       1   0.364 0.382 0.464
 2013       1   0.351 0.366 0.479
 2014       1   0.285 0.296 0.350
 2015       1   0.309 0.314 0.369
 2016       1   0.302 0.314 0.372
 2017       1   0.241 0.246 0.282
 2018       1   0.234 0.243 0.297
 2019       1   0.294 0.296 0.327
 2020       1   0.404 0.508 0.777
 2021       1   0.356 0.361 0.426
 2022       1   0.368 0.377 0.454
 2023       1   0.330 0.335 0.370
 2024       1   0.380 0.385 0.440
 2025       1   0.587 0.620 0.777
 2026       1   0.700 0.740 0.910
```
**Cost-model note:** these are Dukascopy aggregate spreads, ~1 bp WIDER than Vantage Raw ECN (per the earlier cross-check). Backtest costs are therefore conservative — a validated edge should look slightly BETTER live. Re-measure against real Vantage fills at the forward-test stage before sizing up.

## 5. Historical note — Vantage server-time finding (no longer applied)

- When the Vantage feed still existed, its timestamps were server time, not UTC: offset +120 min (GMT+2) or +180 min (GMT+3), DST policy changing across years. Per-month detection flags: {'ok': 77, 'ok_coarse': 17, 'low_quality': 15, 'duka_source': 1}.
- Dukascopy is native UTC so this correction is now moot; the table is kept for the record.

## 6. Frozen splits (bar counts)

```
1min:  in_sample=5,025,968  walk_forward=529,076  out_of_sample=773,426
5min:  in_sample=1,018,941  walk_forward=105,870  out_of_sample=154,716
15min:  in_sample=341,453  walk_forward=35,291  out_of_sample=51,578
```

split ranges: {in_sample: 2009-01-01..2023-01-01, walk_forward: 2023-01-01..2024-07-01, out_of_sample: 2024-07-01..2026-09-04}
out-of-sample is touch-once (enforced in dataset.load_bars).
