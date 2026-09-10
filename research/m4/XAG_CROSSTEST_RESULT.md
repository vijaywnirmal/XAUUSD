# Cross-instrument prior check — primary lead on silver + 6 FX majors  (2026-09-10)

Pre-registered batch (set before seeing results): **XAG/USD + EURUSD, GBPUSD,
USDJPY, AUDUSD, USDCAD, USDCHF**.  None was ever used in this project.

- Data: `data_pipeline/fetch_xag_dukascopy.py` + `fetch_fx_dukascopy.py` → PG
  tables `bars_15min_xag`, `bars_15min_{eurusd,gbpusd,usdjpy,audusd,usdcad,usdchf}`.
  Silver 2014-09→2026-09; FX 2007/2012→2026-09 (Dukascopy start dates vary).
  Standalone tables — no XAUUSD table or frozen split touched.
- Ran the **frozen** rule (`primary_lead_signal.py`, every constant unchanged),
  `research/m4/xtest_primary_lead.py`.  Two data-hygiene adaptations, not signal
  changes: (a) per-instrument σ-floor = ATR14 1st percentile over non-flat bars
  (the frozen 0.4199 is an absolute *gold* price); (b) per-event σ returns
  winsorised at ±20 — Dukascopy pads illiquid FX periods with ~6 % flat
  (high==low) bars, which `run1.py` also winsorised for.  M1's daily boundary
  stays 00:00 UTC (FX has no true daily close — a caveat, not a change).

## Result — the LOW-vol / breakout-continuation effect is NOT general

**24-hour book, LOW-vol regime, net σ after 0.30σ friction:**

| instrument | 24h LOW net | 95 % CI | signals/yr | LOW>MID>HIGH monotone |
|---|---|---|---|---|
| **XAUUSD (reference, already-touched)** | **+0.448σ** | — | 190 | yes |
| XAG/USD (silver) | **+0.205σ** | [−0.16, +0.57] | 118 | yes |
| USD/JPY | **+0.173σ** | [−0.11, +0.44] | 147 | yes |
| USD/CHF | −0.201σ | [−0.46, +0.06] | 203 | yes |
| EUR/USD | −0.293σ | [−0.55, −0.04] | 149 | yes |
| AUD/USD | −0.337σ | [−0.56, −0.13] | 219 | yes |
| USD/CAD | −0.380σ | [−0.66, −0.10] | 189 | no |
| GBP/USD | −0.382σ | [−0.70, −0.06] | 148 | no |

**0 of 7** have a LOW-regime 24h net CI that excludes zero on the positive side.

## Read

- **Positive only in trending assets.**  Gold clearly (+0.45σ), silver weakly
  (+0.20σ, CI still spans 0), and **USD/JPY** leans positive (+0.17σ) — JPY being
  the most trend-/carry-driven major.  That is a coherent pattern: a genuine
  breakout out of a calm range *extends* in assets that trend.
- **Negative — a FADE — in EUR, GBP, AUD, CAD** (−0.29 to −0.38σ, three of four
  with CI excluding zero on the *negative* side), borderline-negative in CHF.
  In those pairs a calm-regime new-extreme breakout mean-reverts, exactly as
  expected for range-bound FX.
- The "monotone LOW>MID>HIGH" count (5/7) is a weak indicator here — for the
  negative pairs it just means LOW is the *least bad*, not good.

## Effect on the prior — mildly cautionary, not supportive

- This is **not** "the mechanism generalises," which would have been strong
  support.  It is "the effect is specific to trending assets (metals + JPY)."
- That is consistent with two explanations: (i) a real but narrow behavioural
  regularity, or (ii) a **trend-era artifact** — gold trended hard 2009–2026 and
  breakouts-from-quiet happened to extend.  The FX batch cannot separate these
  and slightly favours caution.
- Silver + JPY leaning positive is a thin thread of independent support; 4/7
  clearly negative is the dominant signal.

## Status — unchanged

The XAUUSD forward-paper test and its pre-registered verdicts are **not affected**.
This batch does not license any tuning.  It lowers rather than raises confidence
that the primary lead is a robust cross-asset phenomenon; the XAUUSD forward
paper remains the only thing that can settle whether it is real for gold.
