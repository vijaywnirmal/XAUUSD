# H6 result - multi-instrument trend book (in-sample 2009-2022)

_run 2026-09-04 10:54 UTC - daily bars, Dukascopy - vs portfolio bar (blueprint 6b)_

## Headline (idealised, vol-targeted 12%)
```
  total_return   +0.2722
  cagr           +0.0168
  sharpe         +0.1909
  sortino        +0.2362
  max_dd         +0.2690
  dd_days        +1627.0000
  mean active instruments: 10.8  (range 0-14)
  mean strategy-return pairwise corr: +0.170
```

## Comparisons
```
                        totRet     CAGR  Sharpe  Sortino    maxDD
  H6 trend book          +0.27   +0.017   +0.19    +0.24    0.269
  equal-wt buy&hold      -0.27   -0.021   -0.09    -0.11    0.553
  random-sign book       -0.80   -0.105   -0.75    -1.02    0.878
  gold-only (H5-ish)     +1.07   +0.051   +0.43    +0.49    0.268
```

## PnL contribution by instrument
```
  XAUUSD   metal   +18.2%   loo_sharpe(drop XAUUSD)=0.04
  COPPER   metal   +13.8%   loo_sharpe(drop COPPER)=0.14
  NAS100   index   +10.9%   loo_sharpe(drop NAS100)=0.17
  SPX500   index    +9.8%   loo_sharpe(drop SPX500)=0.19
  AUDUSD   fx       +9.2%   loo_sharpe(drop AUDUSD)=0.22
  BRENT    energy   +9.0%   loo_sharpe(drop BRENT)=0.16
  WTI      energy   +7.7%   loo_sharpe(drop WTI)=0.17
  NIKKEI   index    +6.6%   loo_sharpe(drop NIKKEI)=0.21
  USDJPY   fx       +6.5%   loo_sharpe(drop USDJPY)=0.22
  EURUSD   fx       +5.2%   loo_sharpe(drop EURUSD)=0.23
  GBPUSD   fx       +5.1%   loo_sharpe(drop GBPUSD)=0.20
  NATGAS   energy   +2.2%   loo_sharpe(drop NATGAS)=0.19
  XAGUSD   metal    -1.6%   loo_sharpe(drop XAGUSD)=0.22
  DAX40    index    -2.5%   loo_sharpe(drop DAX40)=0.22
```

## Robustness
```
  half 2009-2015: +30.2%     half 2016-2022: -2.3%
    2009    +11.0
    2010     -2.4
    2011    -14.6
    2012     +2.2
    2013    +15.5
    2014     +8.9
    2015     +9.6
    2016    -17.3
    2017    +13.1
    2018     +0.5
    2019     -7.0
    2020    +15.8
    2021     -8.1
    2022     +5.0
  block-bootstrap: CAGR p05/p50/p95 = -0.036/+0.016/+0.078  prob(CAGR>0) 0.69   maxDD p50/p95 0.381/0.594
```

## Verdict (portfolio bar, blueprint 6b)
```
  [FAIL] sharpe >= 1.0
  [FAIL] sortino >= 1.5
  [FAIL] max_dd <= 0.20
  [FAIL] dd_days <= 183
  [PASS] cagr > 0
  [FAIL] positive both halves
  [PASS] no instrument > 40% of PnL
  [FAIL] leave-one-out keeps Sharpe >= 0.8
  [PASS] beats random-sign book (Sharpe)
```

**KILL** - fails: sharpe >= 1.0; sortino >= 1.5; max_dd <= 0.20; dd_days <= 183; positive both halves; leave-one-out keeps Sharpe >= 0.8
---

## Interpretation (added 2026-09-04)

**KILL — and, unexpectedly, the diversified book is *worse* than gold alone
(Sharpe 0.19 vs H5's 0.43).** That is the opposite of what the theory predicts,
and the reason matters.

**What did NOT go wrong:**
- Correlation is fine — mean pairwise strategy-return ρ = +0.17, right in the
  0.1–0.2 range the diversification math assumed.
- Not concentration — no instrument > 18 % of PnL; leave-one-out Sharpes are all
  0.04–0.23, i.e. *nothing* is carrying it.
- Not a data-coverage artifact — the failing half (2016–2022, −2.3 %) has the full
  14-instrument book.

**What did go wrong: the raw material.** The equal-weight buy-and-hold basket
**lost 27 %** over 2009–2022 (oil −70 % 2014–16, FX flat, only equities up). And
every sleeve's stand-alone trend edge in this window was weak-to-absent: 2016
−17 %, 2019 −7 %, 2021 −8 % for the book. **2011–2020 was the worst stretch for
trend-following in ~100 years** ("CTA winter" / the trend drought) — a documented,
industry-wide phenomenon, not a coincidence in our sample. You cannot diversify
your way to Sharpe 1.0 across 14 instruments when the trend premium is not being
paid on *any* of them. Diluting gold (the one half-decent sleeve here) to 1/14
made the risk-adjusted result worse.

**This is not evidence that trend momentum is fake** — it has 140 years of
out-of-sample support. It is evidence that **our in-sample window (2009–2022) is
one where the premium was largely absent, and our data does not reach the
1980s–2000s when it paid handsomely.**

---

## M3 status — 6 hypothesis families, none validated on 2009–2022

| | | Outcome |
|---|---|---|
| H1–H4 | intraday direction / vol / calendar | no edge above cost |
| H5 | single-asset gold trend | real edge, fails Sharpe / DD-duration / regime |
| H6 | 14-instrument trend book | trend premium absent in-sample; worse than H5 |

**The key open question is now a *regime* question, not a *strategy* question:**
does trend work on the **2023–2026** data (a strong trend period for gold and
commodities), which our splits reserved as walk-forward (2023-01 → 2024-06) and
out-of-sample (2024-07 →)?

- The **walk-forward** window is fair to look at now. Earlier feasibility already
  hinted at it: gold trend Sharpe 0.56–0.99 on 2023-H1 2024.
- If H6 clears the bar cleanly on 2023–2024, the honest conclusion becomes
  *"trend momentum works, it is regime-dependent, 2009–2022 was a drought, and we
  are currently in a payout regime"* — a legitimate (if caveated) basis to
  proceed to a live micro-deployment, with an explicit regime-risk acknowledgement.
- If it does **not** work on 2023–2024 either, then the honest project conclusion
  is that no systematic strategy in the tested space clears a meaningful bar, and
  the deliverable is **H5 as "risk-managed gold"** (beats buy-and-hold +65 % vs
  +1 %, DD 28 % vs 57 %) — a real improvement, not a Sharpe-1.0 system.

**Recommendation:** run H5 **and** H6 on the walk-forward window (2023-01 →
2024-06) as a diagnostic before deciding. Do not touch the locked out-of-sample.
