# Hypothesis H2 — London→NY momentum continuation (XAUUSD)

**Drafted:** 2026-09-04
**Status:** DRAFT — awaiting sign-off, then run once end-to-end on in-sample (M3).
**Iteration:** 1 of ≤5 for the H2 family. M3 = run once, record the result. No parameter tuning in M3.

Prior hypotheses: **H1 / H1b (NY opening-range breakout) — KILLED.** H1 had a real
but sub-cost edge (beat a random-direction null, Welch t = +2.36); H1b's attempts
to sharpen it collapsed the t-stat to +1.01 — the ORB edge was thin and
non-robust. H2 tests a different mechanism.

---

## 1. Mechanism (why this could work)

Gold's trading day has a repeatable liquidity structure:

- **Asian** (00:00–07:00 UTC) — thin, mostly positioning noise.
- **London** (07:00–12:00 UTC) — real institutional liquidity arrives; Europe
  prices the overnight news flow and sets the day's first genuine directional lean.
- **London/NY overlap** (12:00–16:00 UTC) — peak liquidity; US desks and
  momentum/CTA flow come in.
- **NY afternoon** (16:00–21:00 UTC).

Claim: **when London establishes a *decisive* directional move, that move tends to
persist through the NY session.** Because —

1. A decisive London move reflects a real macro catalyst / institutional
   repositioning, not chop.
2. NY desks arrive, see the established trend, and momentum flow extends it.
3. US data at 13:30 UTC more often *confirms* than reverses a fresh European move —
   data surprises that move gold usually align with the rates/USD narrative London
   already began pricing.

The edge should exist **only when the London move is large relative to a normal
day's range** — a small London drift is noise and mean-reverts. That conviction
gate is intrinsic to the hypothesis, fixed a priori (see §2), **not** a post-hoc
filter. (H1's lesson: filters chosen after seeing results removed signal, not
noise.)

---

## 2. Exact rules (all parameters fixed a priori)

| Item | Value | Rationale |
|---|---|---|
| Instrument / data | XAUUSD, Dukascopy canonical, **5-min bars**, in-sample 2009-01 → 2022-12 |
| **London window** | 07:00–12:00 UTC (60 bars) | the session that sets the day's lean |
| Window validity | need ≥ 48 of 60 London bars present; else skip the day |
| `london_move` | `close(11:55) − open(07:00)`, signed |
| `london_range` | `high − low` over the window |
| **Decisiveness gate** (both must hold) | `\|london_move\| ≥ 0.4 × ATR20d` **and** `\|london_move\| / london_range ≥ 0.5` | move is a real fraction of a normal day's range **and** directional (not chop). ~18 % of days (~656 trades in-sample). |
| ATR20d | 20-day SMA of daily true range, built from 5-min → daily OHLC, **shifted** so day *t* uses days *t−20..t−1* | no look-ahead |
| Entry | **market at the 12:00 UTC bar open**, in the **direction of `london_move`**; one trade/day; no entry if the gate fails | act on the completed London window immediately |
| Initial stop | **opposite end of the London range** — long → `london_low`, short → `london_high` | if price reverses the entire London range, the continuation thesis is dead. R ≈ `london_range` (median ~$11) |
| Target | **none** | H1 showed a fixed target caps the winners a trend-day trade exists to capture |
| Exit | **hard flat at 20:00 UTC** if the stop is not hit | test the core claim ("persists through the NY session") with the minimum machinery — no trail in iteration 1 |
| Re-entry | none — one completed trade per day |
| Sizing (stat test) | fixed **0.01 lot** — clean per-trade expectancy in $ and R |
| Sizing (equity-curve run) | `risk_pct = 0.5 %`, min-lot floored, $1,000 start |
| Costs | engine default — real per-bar Dukascopy spread + 1 tick/side slippage + $6/lot commission |

Engine wiring: `long_entry` / `short_entry` set on the 11:55 UTC bar (fills at
12:00 open); `stop_dist` = `\|london_ref_close − opposite London extreme\|`;
`target_dist` unset; `session_flat_hour_utc = 20`; `one_trade_per_day = True`;
`trail_activate_r = None`; `allow_short = True`.

---

## 3. Falsifiable predictions & pass criteria (in-sample)

H2 **passes M3** and proceeds to M4 only if **all** of:

| Metric | Threshold |
|---|---|
| Trade count | ≥ 300 (expect ~600–700) |
| Expectancy after costs | **> 0** in $ and R; predict ≥ **+0.05 R/trade** |
| Profit factor | ≥ 1.25 |
| Beats the random-direction null | breakout mean-R exceeds the null (§4) by **> 2 standard errors** |
| Continuation, not reversion | with-trend expectancy > the **fade** expectancy (§4) |
| Max drawdown (0.5 %-risk run) | ≤ 20 % |

**Kill H2** (clean negative → H3) if any of:
- expectancy ≤ 0 after costs, or
- not distinguishable from the random null, or
- the **fade** version does as well or better (→ the NY session *mean-reverts*
  the London move — note it as a candidate hypothesis, not a rescue of H2), or
- profit factor < 1.10, or
- the result rides on ≤ 3 outlier trades (Monte-Carlo p50).

---

## 4. The baselines it must beat

Both use the **same decisive-London days** and the same stop / 20:00 flat / one-per-day:

1. **Random-direction null** — enter at 12:00 UTC in a coin-flip direction (fixed
   seed). Isolates "does the London *direction* predict the NY direction" from "is
   holding through the NY session at this size/stop profitable at all".
2. **Fade** — enter *opposite* to the London move. If continuation is real, H2
   beats both the random null and the fade. If the fade wins, the signal is
   reversion — a different hypothesis (H3).

---

## 5. What M3 produces

1. `research/h2.py` — the H2 signal generator + runner: success-bar table, the
   random-null and fade comparisons, Monte-Carlo, expectancy by year, and a slice
   of expectancy by "stopped out within 90 min of entry" (to size the cost of
   13:30 UTC data-reversal days).
2. `research/H2_RESULT.md` — dated write-up: metrics, both baselines, verdict
   (PASS → M4, or KILL → H3), surprises. **Committed pass or fail.**
3. No parameter sweeps. If H2 fails on trade count or a marginal number, the
   a-priori `k = 0.4` gate is the first thing a *deliberate* iteration 2 would
   revisit — not a reflex here.

---

## 6. Known risks to this hypothesis

- London→NY continuation is well documented in FX majors and may be arbitraged /
  decayed in gold.
- The `k = 0.4 × ATR20` gate is a judgement call; too strict starves the test, too
  loose lets in noise days. ATR-relative (not absolute) at least makes it
  regime-adaptive.
- **13:30 UTC US data can violently reverse a fresh London move.** The full-London-
  range stop is the only guard; those days will hurt. M3 reports the stopped-
  within-90-min slice to quantify it.
- Continuation edges are regime-dependent — strong in trending macro years
  (2011, 2019–20, 2022), weak in rangebound ones (mid-2013 to 2017). Expectancy-
  by-year will expose this; a strategy that only works in 3 of 14 years is not
  robust.
- R is large (~$11 median). On a $1,000 account at 0.5 % risk that is ~0.005×1000 /
  11 ≈ 0.0045 lot → **floored to the 0.01 min lot**, i.e. the equity-curve run
  actually risks ~1 %/trade, not 0.5 %. Reported honestly; it is the charter's
  small-account constraint, not a bug.
