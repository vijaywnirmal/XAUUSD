# Hypothesis H1 — New York opening-range breakout (XAUUSD)

**Drafted:** 2026-09-04
**Status:** DRAFT — awaiting sign-off, then run once end-to-end on in-sample (M3).
**Iteration:** 1 of ≤5. M3 = run once and record the result (pass or fail). No parameter tuning in M3 — that is M4 (walk-forward) and only if H1 shows promise.

---

## 1. Mechanism (why this could work)

The New York morning is the single largest concentration of directional order flow in the gold day:

- **US macro data** releases at 08:30 ET / **13:30 UTC** — NFP, CPI, PPI, retail sales, jobless claims. Gold is a primary rates/USD/real-yield expression, so these prints move it hard and with genuine information.
- **US equity/futures open** at 09:30 ET / 14:30 UTC pulls in US institutional and macro-fund flow.
- The first ~30 minutes after 13:30 UTC sets a range that reflects the initial repricing. A **clean break of that range**, once the range has formed, tends to *continue* in the break direction because (a) it signals the data/flow has a real directional lean, and (b) resting stops and breakout orders sit just beyond the extremes and get triggered, adding momentum.

Prediction: an order that goes with the first break of the 13:30–14:00 UTC range, entered during the liquid NY window, has **positive expectancy after costs** and **beats a same-time random-direction entry**.

This is a classic opening-range breakout (Crabel, 1990s) applied to the gold NY session. It is intraday and flat by session end, matching the charter.

---

## 2. Exact rules (all parameters fixed a priori)

| Item | Value | Rationale |
|---|---|---|
| Instrument / data | XAUUSD, Dukascopy canonical, **5-min bars**, in-sample split (2009-01 → 2022-12) | 5-min resolves a 30-min range and intraday stops without 1-min noise |
| **Opening range (OR)** | high & low of bars **13:30–14:00 UTC** (inclusive of the 13:30 bar, exclusive of the 14:00 bar) | straddles the 08:30 ET data window |
| OR validity filter | need ≥ 5 of the 6 OR bars present; skip the day otherwise | data completeness |
| Range-size filter | trade only if OR height is between **0.4× and 2.5×** the trailing 20-day median OR height | drop dead-flat days (no information) and blow-off news days (bad R, slippage) |
| Entry | **stop order**: buy at `OR_high + buffer`, sell at `OR_low − buffer`; `buffer = max(0.05 × OR_height, 3 ticks)` | avoid being tagged by the exact wick |
| Entry window | first break in **14:00 → 18:00 UTC**; one entry per day; no entry after 18:00 | only the liquid NY window; leave room before the flat |
| Direction | long and short |
| Initial stop | opposite side of the OR: long → `OR_low`; short → `OR_high` | natural invalidation; risk R ≈ OR_height + buffer |
| Target | **1.5 R** fixed (R = entry-to-stop distance) | modest, capital-preservation-friendly |
| Time / session exit | hard flat at **20:00 UTC** if neither stop nor target hit | before the thin post-NY-close hours |
| Re-entry | none — one completed trade per day, whatever the outcome |
| Sizing (stat test) | fixed **0.01 lot** — clean per-trade expectancy in $ and R |
| Sizing (equity-curve run) | `risk_pct = 0.5%` of equity, min-lot floored, $1,000 start — for the drawdown picture |
| Costs | engine default: real per-bar Dukascopy spread + 1 tick/side slippage + $6/lot commission |

Engine wiring: `stop_dist` = entry-to-OR-opposite distance, `target_dist` = 1.5 × that, `session_flat_hour_utc = 20`, `reverse_on_opposite = False`, `allow_short = True`. The stop-order entry (fill only if price trades through the level) is added as an H1 strategy function in `backtest/strategy.py` / `research/h1.py`.

---

## 3. Falsifiable predictions & pass criteria (in-sample)

H1 **passes M3** and proceeds to M4 only if **all** of:

| Metric | Threshold |
|---|---|
| Trade count | ≥ 300 (expected ~1,200–2,000) |
| Expectancy after costs | **> 0** in both $ and R; predict ≥ **+0.05 R/trade** |
| Profit factor | ≥ 1.25 |
| Beats the null | breakout mean-R exceeds the **null** mean-R (see §4) by **> 2 standard errors**, and the null's own expectancy is ≈ −cost (sanity that the null is a fair baseline) |
| Max drawdown (0.5%-risk run) | ≤ 20% |

**Kill H1** (record as a clean negative, move to H2) if any of:
- expectancy ≤ 0 after costs, or
- not statistically distinguishable from the null, or
- profit factor < 1.10, or
- the result depends entirely on ≤ 3 outlier trades (check via Monte-Carlo p50).

---

## 4. The null it must beat

Same universe (same days, same OR-size filter), but at **14:00 UTC** (OR close) open a position in a **random direction** (fixed seed, 50/50), with the **same** stop distance (OR_height + buffer), **same** 1.5 R target, **same** 20:00 UTC flat, one trade/day. This isolates "does the *break direction* carry information" from "is trading the NY window at this size profitable at all". A real edge shows breakout expectancy clearly above null; a spurious one shows them equal.

---

## 5. What M3 produces

1. `research/h1.py` — the H1 signal generator + a runner that prints the success-bar table, the null comparison, and Monte-Carlo.
2. `research/H1_RESULT.md` — the dated write-up: metrics, null comparison, verdict (PASS → M4, or KILL → H2), and any surprises. **Committed whether it passes or fails.**
3. No parameter sweeps. If H1 fails, H2 is drafted fresh — we do not "fix" H1 by trying 13:30 vs 14:30 anchors here (that would be iteration 2, a deliberate decision, not a reflex).

---

## 6. Known risks to this hypothesis

- ORB has decayed on US equity index futures over the last ~15 years; gold may or may not be different.
- 2009–2022 in-sample spans regimes where gold's macro driver flipped (QE bull, 2013 taper crash, 2015 bottom, 2019–20 easing, 2022 hikes) — a break-continuation edge could be regime-dependent. M3 will slice expectancy by year to check.
- The 13:30 UTC anchor assumes data-driven flow; on no-data days the range may be pure noise. The range-size filter is the (imperfect) guard.
