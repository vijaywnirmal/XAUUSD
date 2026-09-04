# H7 — G7 FX carry

**Run:** 2026-09-04. Rank EUR/GBP/JPY/AUD/NZD/CAD by 3-month interbank rate vs USD
(FRED OECD series). Long the 2 highest-carry currencies vs USD, short the 2
lowest. Monthly rebalance, vol-targeted 10 %. The rate differential is accrued
daily (that is the edge); FX spot move is the risk. 1 %/yr broker swap haircut +
0.6 bp turnover cost.

---

## Result

| Window | | totRet | CAGR | **Sharpe** | Sortino | maxDD | DD days | skew | worst month |
|---|---|---|---|---|---|---|---|---|---|
| **In-sample 2009–2022** | H7 carry | −16 % | −1.2 % | **−0.05** | −0.07 | 41 % | 2,802 (7.7 yr) | −0.02 | −8.7 % |
| | random-sign null | −51 % | −4.8 % | −0.38 | | 64 % | | | |
| | long-USD only | −3 % | −0.2 % | +0.04 | | 38 % | | | |
| **Walk-forward 2023-01→2024-06** | **H7 carry** | **+18 %** | **+11.2 %** | **+1.00** | **+1.74** | **7.2 %** | 105 | **+0.93** | −3.0 % |
| | random-sign null | +3 % | +1.7 % | +0.21 | | 20 % | | | |
| | long-USD only | +10 % | +6.6 % | +0.63 | | 9.5 % | | | |

In-sample by half: **2009–2015 +23 %, 2016–2022 −32 %.**

---

## Interpretation — the first non-negative result, but it is regime-contingent

**In-sample (2009–2022): dead.** Sharpe −0.05, a 7.7-year drawdown. The reason is
structural: **G7 short rates were compressed to near-zero from ~2012 to 2021** —
the mean rate differential we were trying to harvest was a fraction of a percent,
and it was swamped by FX spot noise. This is the well-known "carry is dead"
decade.

**Walk-forward (2023–24): Sharpe 1.00.** After 2022's rate normalisation, the
AUD/NZD-vs-JPY/EUR differential is 3–5 %, and carry works — with **positive skew
(+0.93)** and a shallow 7 % drawdown, which is unusually clean for carry (it
normally has a fat left tail). It beats the random-sign null (+0.21) and the
long-USD baseline (+0.63) decisively. Default parameters, no tuning — this is
**not an overfit**.

**This is the same shape as trend (H5/H6):** a real risk premium that was largely
not paid during the 2011–2021 zero-rate era and revived when rates normalised.
The strategy's viability is **entirely contingent on rate dispersion existing** —
if central banks cut back to a synchronised zero in the next recession, carry dies
again, exactly as it did 2016–2021.

---

## Status & next step

H7 carry is **the first strategy in the project to hit Sharpe ≥ 1.0 in any window**
(the 2023–24 walk-forward). It passes the walk-forward on the understanding that
the in-sample failure is a diagnosed regime effect (ZIRP), not a broken strategy.

Per the blueprint, a strategy that has cleared in-sample-context + walk-forward
earns **one** touch of the locked out-of-sample (2024-07 → 2026-09, ~26 months)
as the decisive independent test. H7 has earned it. If carry holds a Sharpe near
1.0 on the untouched OOS, that is real evidence — with the permanent caveat that
the edge switches off when rate differentials compress, and a live rule to stand
down when they do.

Trade only XAUUSD? No — this is FX carry, not gold. But the instrument constraint
was lifted, and this is the only thing that has worked.

---

## OUT-OF-SAMPLE TEST (locked window 2024-07 -> 2026-09) — run once, 2026-09-04

| | totRet | CAGR | **Sharpe** | maxDD | DD days | **skew** | worst month |
|---|---|---|---|---|---|---|---|
| **H7 carry (OOS)** | **-1.9%** | -0.8% | **-0.01** | 19.7% | 658 | **-1.12** | -9.5% |
| random-sign null | -33% | -16.3% | -1.44 | 42% | | | |
| long-USD only | -0.0% | 0.0% | +0.06 | 12% | | | |

By year: 2024 H2 **-8.8%**, 2025 +0.2%, 2026 +7.3%.

**H7 carry FAILS the out-of-sample test. Sharpe -0.01.**

The walk-forward Sharpe of 1.00 was the 2023–H1 2024 rate-divergence window and
**did not persist**. In the OOS:
- Central banks pivoted to **cutting** from Sept 2024 (Fed, ECB, BoE, RBNZ) →
  rate differentials compressed, the carry to harvest shrank.
- The **August 2024 yen carry unwind** — BoJ hiked, USDJPY fell ~162→142 in weeks.
  The book was short JPY vs USD (JPY the lowest-yielder), i.e. exactly the
  position that blew up. Skew **-1.12** — carry's characteristic left tail,
  which the 2023–24 window had (misleadingly) lacked, showed up here.

Carry is confirmed as the same thing as trend: a real premium that was not paid
2009–2022 (ZIRP), paid briefly in the 2023–24 divergence, and not paid again
2024–26 (convergence + the yen unwind). **Not a robust, deployable edge** — it is
regime-contingent to the point of needing perfect regime timing, and it carries a
crash tail that materialised out of sample.

**The locked out-of-sample is now spent (one touch, as designed). There is no
further held-out data.**
