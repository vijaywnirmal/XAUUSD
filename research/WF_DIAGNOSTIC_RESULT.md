# Walk-forward diagnostic — does trend momentum work in 2023–2024?

**Run:** 2026-09-04 · window **2023-01 → 2024-06** (~18 months, ~464 trading days) ·
signal warm-up from 2021-06 · **locked out-of-sample (2024-07 →) NOT touched**.

Purpose: H6's in-sample failure looked like a *regime* problem (2011–2020 was a
documented trend drought). This checks whether trend clears the bar in a recent,
trend-favourable window before we decide anything.

---

## Result

| | totRet | CAGR | **Sharpe** | Sortino | maxDD | DD days |
|---|---|---|---|---|---|---|
| **H5 trend (gold-only)** | +12.7% | 6.7% | **0.65** | 0.75 | 9.3% | 213 |
| gold **buy & hold** | +18.9% | 9.8% | **0.80** | 1.12 | 12.8% | 213 |
| **H6 trend book (14 inst)** | +9.1% | 5.8% | **0.49** | 0.82 | 14.4% | 375 |
| equal-weight **buy & hold basket** | +13.3% | 8.4% | **0.67** | 0.95 | 8.9% | 169 |
| random-sign book | −24.3% | −16.5% | −1.29 | −1.87 | 27.3% | 505 |

**The trend strategies did not clear the §6b bar (Sharpe ≥ 1.0) even in this
favourable window** — H5 0.65, H6 0.49. And in both cases **plain buy-and-hold
beat the trend strategy** on return *and* Sharpe.

The trend signal still beats *random* (H6 0.49 vs −1.29) — there is a faint
directional signal — but it does not beat *being long*, which is all that mattered
in a 2023–24 gold bull market.

**Why:** 2023–24 was a steady grind higher with shallow pullbacks. Buy-and-hold
captures 100 % of that. The trend strategy lags the entry (12-month confirmation),
scales down on rising vol, and gets whipsawed by the pullbacks. H5's entire
walk-forward edge is **one month** — March 2024, +11.8 %; it was flat-to-negative
through the choppy first three quarters of 2023.

---

## What this settles

The "2009–2022 was just a drought" explanation is **not supported**. Trend was
mediocre in 2023–24 too. The only thing that worked in the recent window was
**being long gold** — i.e. the bull market, not a systematic edge.

### M3 conclusion after 6 hypothesis families + this diagnostic

| Angle | Windows tested | Verdict |
|---|---|---|
| Intraday direction / vol / calendar (H1–H4) | 2009–2022 | no edge above cost |
| Single-asset gold trend (H5) | 2009–2022 **and** 2023–24 | real but weak; below bar; loses to buy-hold recently |
| 14-instrument trend book (H6) | 2009–2022 **and** 2023–24 | trend premium absent; below bar; loses to buy-hold |

**There is no systematic strategy in the space explored — intraday price
patterns, single- and multi-asset time-series trend — that clears even the
recalibrated bar on data outside the fitting window, with retail costs.** In the
one period where a strategy "worked", it was buy-and-hold.

This is a **negative result, and the blueprint process produced it on purpose** —
it stopped us deploying an overfit strategy. "Six hypothesis families tested
rigorously, none held up out of sample" is a real, useful finding: **do not risk
capital on these ideas.**

---

## Options from here

1. **Accept the negative result.** The disciplined action is to not trade
   systematically on what we've found. If the goal is gold exposure, the
   cost-minimising route is DCA into a physical-backed ETF and skip CFD
   spread/swap/leverage entirely.
2. **A different premium we have not tested** — e.g. **carry** (FX/commodity
   carry is a documented risk premium, roughly orthogonal to trend; a trend+carry
   book is the next standard step), or **cross-sectional** relative-value
   (long strongest / short weakest instrument) instead of time-series. Same
   "is the premium paid in our window" risk applies, but it is genuinely
   different machinery. Scope: more data, another 1–2 M3 cycles.
3. **Ship H5 as a pure risk wrapper** — accept it won't add return, and use the
   trend filter only to cap the worst drawdowns. Weak: in 2023–24 it barely
   helped (9 % DD vs 13 %), and in-sample it cost ~40 % of the return to shave the
   drawdown. Marginal value.

**Recommendation:** this is a legitimate stopping point to accept the negative
result. If you want one more distinct attempt, **carry (option 2)** is the
highest-value remaining idea — but with clear-eyed expectations after six kills.
