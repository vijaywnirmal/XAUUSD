# H8 — macro-conditioned gold (real yields + dollar)

**Run:** 2026-09-04. **Exploratory only** — the held-out data is spent, so this is
in-sample + a contaminated walk-forward, not a validation.

Idea: gold's textbook drivers are the **10-year real yield (DFII10)** and the
**broad USD index (DTWEXBGS)**. Gold should rise when both fall. Signal =
`−½(sign(Δ20d real yield) + sign(Δ20d dollar))`, vol-targeted, daily.

---

## The driver relationships ARE real — and did not weaken

Daily correlation of gold returns with:

| Period | vs Δ real yield | vs Δ dollar |
|---|---|---|
| 2009–2015 | −0.24 | −0.31 |
| 2016–2021 | −0.41 | −0.29 |
| **2022+** | **−0.49** | **−0.46** |

Contrary to the popular "the real-yield relationship broke" story, the *daily*
co-movement actually **tightened** in 2022+. (The "break" narrative is about
*levels over years* — real yields at +2 % with gold at record highs — driven by
record central-bank buying, not about daily changes.)

## But it does not forecast — and trading it loses

| | In-sample 2009–2022 | Walk-forward 2023–24 |
|---|---|---|
| H8 macro (Δ regime) | Sharpe **−0.12**, DD 47 %, 13.8-yr drawdown | Sharpe **−1.07** |
| H8 macro (level regime) | Sharpe +0.10 | Sharpe −0.62 |
| H5 price trend | Sharpe 0.32 | Sharpe 0.65 |
| buy & hold gold | Sharpe 0.07 | Sharpe 0.80 |

By sub-period (Δ regime): 2009–15 **−35 %**, 2016–21 −1 %, 2022+ +11 %.

## Why "understandable" ≠ "forecastable"

1. **The transmission is same-day.** Gold and real yields move together *on the
   same session*. By the time you observe the yield move, gold has already moved —
   there is no lead-lag to trade.
2. **To trade "yields will fall → gold will rise" you must forecast yields** —
   i.e. forecast the Fed and the bond market, which is at least as hard as
   forecasting gold directly.
3. **A momentum-of-drivers signal is just price momentum with extra noise** — and
   it was destroyed in 2023–24, when gold decoupled from the yield *level* on
   central-bank buying: the macro signal said "bearish" and gold ripped to records.
4. **News is priced in seconds.** Anything "publicly available to us" is already
   in the price.

**Conclusion:** macro/fundamental data lets you *explain* gold's moves after the
fact; it does not give a mechanical forecast. The one honest use is a
*discretionary* directional view acted on by hand — not mechanical, not
backtestable, poor retail track record, and outside the charter.

This closes the fundamental/macro angle. Every category — intraday price patterns,
trend, carry, technical indicators, and now macro — has been checked.
