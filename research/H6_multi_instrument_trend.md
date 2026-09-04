# Hypothesis H6 — Multi-instrument trend book (managed-futures style)

**Drafted:** 2026-09-04
**Status:** DRAFT — awaiting sign-off, then run once end-to-end on in-sample (M3).
**Iteration:** 1 of ≤5 for the H6 family.
**Bar:** measured against the **portfolio bar (blueprint §6b — the original bar)**:
Sharpe ≥ 1.0, Sortino ≥ 1.5, max DD ≤ 20 %. Now legitimate, because H6 is a
diversified book, not a single asset.

Prior: H1–H5 KILLED. H5 (single-asset gold trend) *had a real edge* — beat
buy-and-hold on return and drawdown, PF 1.58, beat the random-sign null — but
failed on Sharpe (0.32), drawdown duration (3.6 years), and regime robustness
(all the edge in 2009–2015). **Those three failures are exactly what
diversification fixes**, and the operator has lifted the XAUUSD-only constraint.

---

## 1. Mechanism (why this should work where H5 didn't)

Time-series (trend) momentum is not a gold fact — it is a **cross-asset** fact.
Moskowitz–Ooi–Pedersen (2012) documented it across **58 instruments** in equities,
bonds, currencies and commodities, ~1985–2009; Hurst–Ooi–Pedersen extend it to
~140 years and ~130 markets. Every instrument's stand-alone trend edge is weak
(Sharpe ~0.2–0.4). The **portfolio** works because the strategy returns across
instruments are only mildly correlated (ρ ≈ 0.1–0.2 for trend), so a risk-weighted
basket **diversifies away the idiosyncratic noise while keeping the common trend
premium**:

> portfolio Sharpe ≈ single-instrument Sharpe × √( N / (1 + (N−1)·ρ) )

With N = 14, ρ = 0.15 → multiplier ≈ 2.4 → a 0.35 single-instrument Sharpe becomes
**~0.8**. Better instruments / lower ρ push it toward 1.0.

It also fixes H5's **drawdown-duration** problem directly: when gold chops
sideways for four years (2016–2020, which killed H5), crude, the dollar, equities
and rates are usually trending — so the *book's* equity curve does not sit
underwater for 3.6 years even though the gold sleeve does.

This is the entire economic basis of the managed-futures / CTA industry. It is the
best-evidenced systematic strategy that exists.

---

## 2. The basket (14 instruments, 5 asset classes)

All available on **Dukascopy** (daily bars) and tradable as spot CFDs on
**Vantage**. History depth is verified on fetch; instruments that don't reach
2009 enter the book when their data starts (the risk-weighting handles a varying
instrument count).

| Class | Instruments |
|---|---|
| Metals (3) | **XAUUSD** (gold), XAGUSD (silver), Copper |
| FX majors (4) | EURUSD, GBPUSD, USDJPY, AUDUSD |
| Equity indices (4) | S&P 500, Nasdaq 100, DAX 40, Nikkei 225 |
| Energy (3) | WTI crude, Brent crude, Natural gas |

Gold is one sleeve of ~14 — its stand-alone weakness (H5) is diluted, its trend
contribution kept. FX and indices are the main diversifiers vs the
metals/energy commodity block.

---

## 3. Exact rules (all parameters fixed a priori — identical trend logic to H5)

| Item | Value | Rationale |
|---|---|---|
| Data | Dukascopy **daily** OHLC per instrument, UTC dates, in-sample 2009-01 → 2022-12 |
| **Trend signal** (per instrument *i*) | `sᵢ = ½·[ sign(Pᵢ/Pᵢ₋₆₃ − 1) + sign(Pᵢ/Pᵢ₋₂₅₂ − 1) ]` → {−1 … +1} | same 3m + 12m blend as H5 — isolates "does diversification fix it" |
| Realised vol (per *i*) | 20-day stdev of daily log-returns × √252, lagged 1 day | no look-ahead |
| **Per-instrument position** | `wᵢ = sᵢ · ( σ_inst / σᵢ )`, capped at `|wᵢ| ≤ 4` per instrument | equal risk per sleeve; `σ_inst` set so the pre-scaling book targets ~a sensible gross vol |
| **Portfolio vol target** | scale the whole book daily by `k = min( σ_port_target / σ̂_port , 3 )`, where `σ̂_port` = 20-day realised vol of the *un-scaled* portfolio return, `σ_port_target = 0.12` (12 % annualised) | accounts for correlation — when everything trends together, book vol rises and `k` cuts exposure |
| Rebalance | daily at close, position held next day | no look-ahead |
| Exit | none explicit — signal flip is the exit; vol-target caps risk; **no stops** (standard CTA) |
| Costs (per instrument, per rebalance) | `\|Δwᵢ·k\| · equity` notional turned over × class round-trip cost: **FX 0.6 bp · metals 1.5 bp · indices 1.5 bp · energy 4 bp** (Vantage Raw ECN representative) |
| Financing / carry | **2 %/yr** drag on **gross** exposure, both directions (conservative; real per-instrument swap varies) — documented estimate |
| Idealised run | fractional exposure — measures true risk-adjusted properties |
| Realistic-account note | a 14-instrument vol-targeted book needs meaningful capital (min-lot granularity × 14 sleeves). On $1 k it is not runnable as designed; ~$10–25 k is realistic. Reported honestly, not scored. |

---

## 4. Evaluation — pass criteria (portfolio bar §6b, in-sample idealised run)

H6 **passes M3** and proceeds to M4 only if **all** of:

| Metric | Threshold |
|---|---|
| Sharpe / Sortino (daily equity) | ≥ **1.0** / ≥ **1.5** |
| Max drawdown | ≤ **20 %** |
| Max drawdown duration | ≤ ~6 months |
| CAGR after all costs incl. carry | > 0, and Sharpe-competitive |
| Robust across regimes | net-positive in **both** 2009–2015 and 2016–2022 |
| Genuinely diversified | no single instrument contributes > 40 % of total PnL; leave-one-out — removing any one instrument does not drop Sharpe below 0.8 |
| Beats a random-sign book | same 14 instruments, random daily signs, same vol-targeting → clearly lower Sharpe (the *trend* signal must add value, not just the diversification) |

**Kill H6** if any of: Sharpe < 1.0 · max DD > 20 % · CAGR ≤ 0 after costs ·
positive in only one half · one instrument drives > 40 % of PnL · a single
leave-one-out breaks it · indistinguishable from the random-sign book.

---

## 5. What M3 produces

1. `research/fetch_basket.py` — pulls Dukascopy **daily** OHLC for the 14
   instruments → `basket/<name>.parquet` (small, fast).
2. `research/h6.py` — the multi-instrument trend engine: portfolio equity, full
   metrics vs §6b, per-instrument PnL contribution + strategy-return correlation
   matrix, by-year / by-half, leave-one-out Sharpe table, block-bootstrap CAGR/DD,
   and the comparisons: equal-weight buy-and-hold basket, gold-only H5, random-
   sign book.
3. `research/H6_RESULT.md` — dated write-up + verdict (PASS → M4, or KILL → next).

No parameter sweeps. If H6 misses on a margin, the first deliberate iteration-2
lever is the instrument set (add agri / rates for more breadth) or the portfolio
vol target — decided explicitly.

---

## 6. Known risks

- **Trend-following had a hard 2011–2020** — the "CTA winter". In-sample includes
  most of it, which is the honest test. If H6 clears the bar *through* that
  period, that is strong evidence.
- **Dukascopy CFD-index / commodity history** may not all reach 2009; the book
  runs with a varying instrument count and equal-risk weighting handles it, but
  early years will be thinner (fewer sleeves → less diversification → the
  by-half check matters).
- **Cost & carry are estimates.** Class-level bp costs and a flat 2 % carry are
  conservative stand-ins for real Vantage swap schedules; a borderline pass would
  need the real numbers before M4.
- **Capital.** This is not a $1 k strategy — 14 vol-targeted sleeves with 0.01-lot
  minimums need ~$10–25 k. That is a real constraint on *implementation*, separate
  from whether the *edge* is valid. If H6 validates, the operator's funding plan
  (and possibly a reduced 6–8 instrument sub-book) becomes the M4/M7 discussion.
- **Correlation spikes in crises** — in 2008/2020-style events trend books can
  take a fast drawdown as everything de-risks together. The portfolio vol-target
  and the max-DD / DD-duration checks are the guard.
