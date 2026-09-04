# M3 conclusion — the edge search

**Date:** 2026-09-04
**Status:** search phase complete. Locked out-of-sample spent (one touch, on H7).

---

## What was tested

| # | Hypothesis | Angle | Verdict |
|---|---|---|---|
| H1 / H1b | NY opening-range breakout | intraday direction | KILL — thin break-direction edge (beat null t=+2.36) but sub-cost; sharpening it collapsed the edge |
| H2 | London→NY momentum continuation | intraday direction | KILL — London direction carries no info about NY direction (t=−0.49 vs random) |
| H3 | Asian-quiet → NY range expansion | intraday volatility | KILL — mechanism runs backwards; gold intraday vol persists, doesn't expand |
| H4 | Turn-of-month drift | calendar | not run — feasibility weak (window drift p≈0.09–0.19; DoW ANOVA p=0.36) |
| — | short-horizon reversion after >2.5σ moves | intraday reversion | dead — −0.13 bps at 5 min, ~1/10 of cost |
| — | NFP-day behaviour | event | empty — elevated vol, no directional edge, no pre-drift |
| H5 | Long/short vol-targeted daily trend on gold | single-asset trend | KILL — real edge (beat buy-hold +65% vs +1%, PF 1.58) but Sharpe 0.32, 3.6-yr drawdown, all edge in 2009–2015 |
| — | H5 + "trade only good environments" filter | meta / regime filter | KILL — fitted filter improved in-sample, made walk-forward worse; unfitted did nothing |
| H6 | 14-instrument trend book | multi-asset trend | KILL — Sharpe 0.19, *worse* than gold alone; trend premium was absent industry-wide 2011–2020 |
| — | 19 classic indicator rules, default params | technical indicators | KILL — none beat buy-and-hold + survive multiple-testing (Bonferroni), in-sample or walk-forward |
| H7 | G7 FX carry | carry premium | KILL — dead 2009–2022 (ZIRP), Sharpe 1.00 on the 2023–24 walk-forward, **Sharpe −0.01 out-of-sample** (rate convergence + the Aug-2024 yen unwind; skew −1.12) |

**Windows:** in-sample 2009-01 → 2022-12; walk-forward 2023-01 → 2024-06;
out-of-sample 2024-07 → 2026-09 (touched once, on H7). Costs modelled from the
real Dukascopy spread + commission + slippage + swap/carry throughout. Every
hypothesis dated and specified before running; ≤5 iterations per family; results
recorded pass or fail.

---

## The finding

**No systematic strategy in the space that could be tested — intraday price
patterns, single- and multi-asset time-series trend, technical indicators, FX
carry — robustly clears even the recalibrated single-asset bar (Sharpe ≥ 0.5,
beats buy-and-hold on return and drawdown) on data it was not fitted to, at
retail costs.**

The two ideas with any life — **trend** and **carry** — are both genuine
risk premia that were **not being paid** during the long 2009–2022 in-sample
window (a zero-rate, low-trend "premia drought"), appeared to revive in the
2023–24 rate-normalisation window, and **did not hold up in the 2024–26 out-of-
sample** as rates converged again. Their viability is entirely contingent on a
macro regime we cannot forecast, and carry's crash tail materialised out of
sample.

This is consistent with market-structure reality (see `research/` notes and the
"why can't I copy the money movers" discussion): a small retail account, high
costs, no meaningful leverage, ~20 correlated instruments, free daily data, and
retail latency is close to the hardest possible setup for extracting a systematic
edge — especially in gold, one of the most-analysed instruments in the world.

---

## What was built (keeps its value regardless)

- **M1 — data foundation.** `data_pipeline/` + `./canonical/` + `./bars/`:
  a true-UTC, cleaned, QA'd Dukascopy tick/bar store, 2009→2026, with frozen
  splits and a touch-once out-of-sample guard. `download_dukascopy_ticks.py`
  keeps it current.
- **M2 — research harness.** `backtest/`: an event-driven backtester with
  realistic fills and a validated cost model (a no-edge strategy loses exactly its
  costs), plus a metrics + success-bar + Monte-Carlo module.
- **Research log.** `research/H*_RESULT.md` — every hypothesis, its mechanism,
  its result, and why it failed. A negative result, documented, is a real output:
  it says *do not fund these ideas*.

---

## Recommendation

1. **Do not deploy systematic capital** on any strategy tested here. The process
   worked — it stopped ~10 backtests that looked good in some window from being
   traded live.
2. **For gold exposure specifically:** dollar-cost-average a physical-backed gold
   ETF. No spread, no swap, no leverage decay. H5 tried to beat this with a trend
   overlay and could not do so robustly.
3. **If the search continues later**, the honest options are all *harder*, not
   easier: options-volatility selling (needs an options account + tail hedging),
   a genuinely broad futures trend book (needs a futures broker + 50+ markets),
   or discretionary macro (not mechanical). None fit the original charter
   (mechanical, XAUUSD, small account).
4. **Revisit trend/carry only if** the macro regime clearly favours them (wide
   rate dispersion, strong cross-asset trends) AND with a hard, pre-committed
   stand-down rule when those conditions fade — accepting that this is regime
   timing, which is itself an edge nobody reliably has.
