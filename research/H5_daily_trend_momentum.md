# Hypothesis H5 — Long/short daily trend momentum on gold (vol-targeted)

**Drafted:** 2026-09-04
**Status:** DRAFT — awaiting sign-off, then run once end-to-end on in-sample (M3).
**Iteration:** 1 of ≤5 for the H5 family.
**Bar:** measured against the **recalibrated single-asset bar (blueprint §6a)** —
the operator accepted it 2026-09-04.

Prior hypotheses — H1/H1b/H2/H3 KILLED, H4 skipped. The intraday space (direction,
volatility, calendar) held no edge above the ~0.10 R cost wall. H5 is the first
**swing / daily-bar** hypothesis — the charter's "later" phase, brought forward.

---

## 1. Mechanism (why this should work)

**Time-series (trend) momentum is the single most-replicated anomaly in asset
pricing** — Moskowitz–Ooi–Pedersen (2012) across ~60 instruments and a century;
Hurst–Ooi–Pedersen extend it to ~140 years. It is the entire economic basis of
the managed-futures / CTA industry. Assets that rose over the past 3–12 months
tend to keep rising; assets that fell tend to keep falling. Drivers:

1. **Under-reaction** — investors anchor and digest gradual news slowly.
2. **Herding / over-reaction continuation** — flows chase performance.
3. **Mechanical feedback** — stop-losses, margin calls, and CTA / risk-parity /
   vol-target rebalancing all *sell into* falls and *buy into* rises, extending
   moves. This is non-discretionary flow, like H4's calendar flows but larger.

Gold is a canonical trend instrument — it trades in multi-year regimes (2009–11
QE bull, 2011–15 grind-down, 2019–20 bull, 2022 chop). A **long/short** trend rule
earns the up-regimes, is **short through the down-regimes** (e.g. +25 % in 2013
while buy-and-hold was −33 %), and sits small in choppy transitions. **Vol-
targeting** holds risk roughly constant so drawdowns do not balloon in high-vol
regimes.

For the capital-preservation charter this is the natural fit: *a risk-managed way
to hold gold* — capture the long-run drift when trend is up, step aside / go short
when it is down, keep the drawdowns well below buy-and-hold's ~45 %.

---

## 2. Feasibility already checked (in-sample 2009–2022)

| Variant (vol-targeted 12 %) | CAGR | Sharpe | max DD |
|---|---|---|---|
| Buy & hold | 4.1 % | 0.36 | −45 % |
| 12m long/flat | 4.1 % | 0.40 | −30 % |
| 12m long/short | 5.4 % | 0.40 | −35 % |
| **3m + 12m blend, long/short** | **5.9 %** | **0.52** | **−26 %** |
| SMA200 long/short | 4.4 % | 0.32 | −43 % |

Unscaled, the 3m+12m blend returns **+178 %** in-sample vs buy-and-hold **+107 %**,
with max DD −26 % vs −45 %, and is **positive in 10 of 14 years** (short during the
2013 crash and the 2015 bear). This clears the recalibrated §6a bar on the
feasibility numbers; H5 is the formal, cost-inclusive test.

---

## 3. Exact rules (all parameters fixed a priori)

| Item | Value | Rationale |
|---|---|---|
| Instrument / data | XAUUSD, Dukascopy canonical, **daily bars** (UTC-date close from 5-min), in-sample 2009-01 → 2022-12 |
| **Trend signal** | `s = ½·[ sign(P/P₋₆₃ − 1) + sign(P/P₋₂₅₂ − 1) ]` → {−1, −½, 0, +½, +1} | 3-month + 12-month, the AQR-standard pair; two horizons cut whipsaw vs a single MA (SMA200 whipsawed worst in feasibility) |
| Realised vol | 20-day stdev of daily log-returns × √252, **lagged 1 day** | no look-ahead |
| **Position** | `pos = s · min(0.12 / realised_vol, 3.0)` | vol-target 12 % annualised, leverage cap 3× |
| Rebalance | daily, signal on close of day *t*, position held day *t+1* | no look-ahead |
| Exit | **none explicit** — the signal flip *is* the exit; vol-target caps risk. No stop (a stop on a trend system cuts trades that would recover — standard CTA practice) |
| Direction | long **and** short |
| Costs per rebalance | `|Δpos| · equity` notional turned over × (daily mean spread + 1 tick slippage) / price + $6/lot commission on the lot turnover |
| **Financing / carry** | annualised **3 %** drag on **gross** exposure (`|pos|·equity·0.03/252` per day), charged **both** long and short (conservative — short carry is usually better) | gold financing ≈ USD rate over 2009–22; the account's real swap is unavailable, so this is a documented estimate |
| Sizing — idealised run | fractional exposure `pos · equity` (no min-lot rounding) — measures the strategy's true risk-adjusted properties |
| Sizing — realistic-account run | min lot 0.01 on $1,000 start. **Note:** 0.01 lot ≈ 1 oz ≈ $1.8 k notional ≈ 1.8× leverage — already *above* the 12 % vol target, so this run will show higher DD. The strategy really wants ~$3–5 k to run at a sane vol target with min-lot granularity. |

---

## 4. Evaluation — pass criteria (recalibrated §6a bar, in-sample)

H5 (idealised run) **passes M3** and proceeds to M4 only if **all** of:

| Metric | Threshold |
|---|---|
| **Core** | beats buy-and-hold XAUUSD on **both** total return **and** max drawdown |
| Max drawdown | ≤ 30 % |
| Max drawdown duration | ≤ ~12 months |
| Sharpe / Sortino (daily equity) | ≥ 0.5 / ≥ 0.7 |
| Profit factor (holding-period basis) | ≥ 1.15 |
| CAGR after all costs incl. carry | > 0 |
| Robust across regimes | net-positive in **both** 2009–2015 **and** 2016–2022 |
| Beats the random-sign null | vol-targeted random-daily-sign exposure (fixed seed) has lower Sharpe / worse DD — the *trend* signal must add information |

**Kill H5** if any of: does not beat buy-and-hold on both axes · Sharpe < 0.5 ·
max DD > 30 % · CAGR ≤ 0 after costs · positive in only one half · indistinguishable
from the random-sign null · rides on ≤ 2 years (by-year / block-bootstrap).

---

## 5. What M3 produces

1. `research/h5.py` — daily trend engine: equity curve, CAGR / Sharpe / Sortino /
   maxDD / DD-duration, holding-period "trades" and their PF, by-year and by-half,
   turnover and total cost breakdown (spread / commission / carry), a **block-
   bootstrap** (20-day blocks) distribution of CAGR & maxDD, and the three
   comparisons: buy-and-hold, long/flat (no short), random-sign null.
2. `research/H5_RESULT.md` — dated write-up + verdict (PASS → M4, or KILL → H6).

No parameter sweeps. If H5 misses on a margin, the first *deliberate* iteration-2
lever is the vol target (12 % → higher for more return / DD) or the signal pair
(add a 21-day fast leg), decided explicitly.

---

## 6. Known risks

- **Trend-following had a hard decade (~2011–2020)** — thin premia, several deep
  CTA drawdowns. The in-sample window contains it, which is the point.
- **Single-asset trend is structurally lower-Sharpe** than a diversified trend
  book — hence the recalibrated bar. Pushing toward Sharpe ≥ 1.0 is a *portfolio*
  problem (blueprint §11 secondary goal), not an H5 problem.
- **Small-account leverage:** min-lot 0.01 on $1 k ≈ 1.8× ≈ 27 % vol, above the
  target. The realistic-account run will look worse than the idealised one; both
  are reported. Funding to ~$3–5 k is likely needed to run H5 as designed.
- **Whipsaw** in range-bound years (2017, 2021 lost in feasibility) — the 3m+12m
  blend mitigates, does not eliminate.
- **Turnover ~15–25×/year** → costs and carry matter and are modelled explicitly;
  carry in particular is an *estimate* (3 %) pending a real broker swap schedule.
- **Regime dependence** cuts both ways — a trend system that only worked in 2013 +
  2019–20 would be as fragile as H2's 2013-only P&L. The by-half and by-year
  checks are the guard.
