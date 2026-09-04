# Hypothesis H4 — Turn-of-month drift (XAUUSD)

**Drafted:** 2026-09-04
**Status:** DRAFT — awaiting sign-off, then run once end-to-end on in-sample (M3).
**Iteration:** 1 of ≤5 for the H4 family.

Prior hypotheses — all KILLED (`research/H{1,1b,2,3}_RESULT.md`):
- **H1/H1b** NY opening-range breakout — thin, non-robust directional edge.
- **H2** London→NY momentum continuation — no directional information (t=−0.49 vs random).
- **H3** Asian-quiet → NY range expansion — mechanism reversed (gold intraday vol persists).

H4 conditions on the **calendar date**, not on price or volatility structure.

> **Charter note.** The turn-of-month effect is inherently a **multi-day** (overnight-
> inclusive) phenomenon — a quick check shows only ~2.5 bps of the ~26 bps window
> drift lands inside the NY session. So H4 as specified holds positions overnight,
> which crosses from the charter's "intraday first" phase toward the swing phase.
> This is deliberate: the intraday-direction, intraday-vol, and intraday-calendar
> angles are now exhausted, and the calendar signal only exists at the multi-day
> scale. If H4 also fails, that is a clear mandate to design a proper swing edge.

---

## 1. Mechanism (why this could work)

Recurring, **calendar-locked institutional flows** cluster around month-end:
pension / insurance portfolio rebalancing, salary-linked contributions,
ETF / index rebalancing, and options-expiry hedge unwinds. These are largely
**non-discretionary** and executed during liquid hours. The net historical effect
in equities is a well-documented **turn-of-the-month (TOM) drift** — the last day
or two of a month plus the first few days of the next tend to be positive.

Claim: **gold shares a (weaker) turn-of-month up-drift**, for the same reason —
mechanical month-end flows — and because gold sits in many of the same balanced /
risk-parity / multi-asset mandates that rebalance on the calendar. Because the
driver is a flow, not a price pattern, it is less prone to being arbitraged away.

---

## 2. Feasibility already checked (in-sample 2009–2022)

| Measure | Result |
|---|---|
| TOM **window** return (last 2 + first 3 trading days, summed log-ret) | mean **+26.5 bps**, median +30.4, **58 %** of windows positive, n = 168 |
| vs 0 | t = **+1.69**, p = 0.093 (one-tailed marginal, two-tailed no) |
| vs random 5-day non-TOM blocks (+3.7 bps) | t = +1.32, p = 0.19 |
| NY-session-only slice of the drift (13:30–20:00 UTC) | only +2.5 bps (t = 0.95) — most of the drift is overnight |
| By window day (NY session, bps) | −2: +4.0 · −1: −1.2 · **+1: +8.7** · +2: +1.9 · +3: −5.3 |
| By half | 2009–15 weak-positive, 2016–22 weak-positive (not a decayed-away effect, but never strong) |

**This is a weak signal.** It is the strongest of the calendar cuts checked
(day-of-week ANOVA across the NY session: F = 1.08, p = 0.36 — dead). H4 is run to
settle whether even this survives the full success bar; the honest prior is that
it does **not**, and that H4 is the last intraday-family test before a swing pivot.

---

## 3. Exact rules (all parameters fixed a priori)

| Item | Value | Rationale |
|---|---|---|
| Instrument / data | XAUUSD, Dukascopy canonical, **daily bars built from 5-min** (UTC-date close), in-sample 2009-01 → 2022-12 |
| **TOM window** | the **last 2 trading days** of a calendar month **+ the first 3 trading days** of the next month (5 trading days) | standard TOM definition |
| "Trading day" | a UTC date with a usable session in the bar store |
| The trade | **long** at the **close of the last-2nd trading day**, exit at the **close of the 3rd trading day** of the new month. One position per monthly window (~168 in-sample). Held across ~5 trading days incl. weekends. | capture the whole window drift, not a slice |
| Stop | **disaster stop only** at **−2.5 × ATR20d** from entry (ATR of daily true range, prior 20 days). Rarely hit; present for capital preservation, not as part of the thesis. | a calendar-drift trade with a tight stop tests path, not the hypothesis |
| Direction | **long only** (the hypothesis is an up-drift). Short and a per-window-day breakdown are reported for context. |
| Sizing (stat test) | fixed **0.01 lot** — clean per-window expectancy in $ and R |
| Sizing (equity-curve run) | fixed **0.01 lot** on $1,000 (the 2.5 ATR stop makes R ~$40; `risk_pct` would floor to min lot anyway — reported honestly) |
| Costs | engine default — real Dukascopy spread + 1 tick/side slippage + $6/lot commission. **Swap/financing on the ~5-day hold is added explicitly** (Vantage XAUUSD swap ≈ −$0.08/lot·point long; ~5 nights) |

Also run an **intraday-only variant** for comparison: same TOM days, long at
13:30 UTC, flat at 20:00 UTC, one trade per TOM day (~840 trades) — to confirm (as
feasibility suggests) that the intraday slice alone is not tradeable.

---

## 4. Falsifiable predictions & pass criteria (in-sample)

H4 (multi-day) **passes M3** and proceeds to M4 only if **all** of:

| Metric | Threshold |
|---|---|
| Window count | ≥ 120 (have 168) — relaxed from 300 because a calendar window is one observation; the effective independent N is the window count |
| Mean window return after all costs (incl. swap) | **> 0** in $ and R; predict ≥ **+10 bps/window** net |
| **TOM vs non-TOM** | mean window return significantly > random non-TOM 5-day blocks, **Welch t > 2** |
| Profit factor (window-level) | ≥ 1.25 |
| Robust across halves | net-positive in **both** 2009–2015 and 2016–2022 |
| Not concentrated | not driven by ≤ 3 windows / one year (Monte-Carlo p50, by-year) |
| Max drawdown ($1,000 fixed-lot run) | ≤ 20 % |

**Kill H4** (clean negative) if any of:
- mean window return ≤ 0 after costs, or
- not distinguishable from random non-TOM blocks (t ≤ 2), or
- net-positive in only one sample half, or
- profit factor < 1.10, or
- the result rides on ≤ 3 windows / one year.

---

## 5. What M3 produces

1. `research/h4.py` — daily-bar TOM engine: window-level stats (mean, t vs 0, t vs
   random non-TOM blocks, month-clustered / block-bootstrap p-value), by-window-day
   breakdown, by-year and by-half, Monte-Carlo, plus the intraday-only variant.
2. `research/H4_RESULT.md` — dated write-up + verdict (PASS → M4, or KILL → swing
   pivot). Committed pass or fail.

---

## 6. Known risks

- **Weak prior (p ≈ 0.09–0.19).** H4 is a long shot; the value of running it is a
  clean, documented answer on the last intraday-family angle.
- Only 168 windows over 14 years — an anomaly this size (+26 bps) is well within
  what noise produces; the block-bootstrap p-value is the real test.
- TOM is documented mainly for equities; gold's version is study-dependent and
  weaker.
- Overnight hold adds **weekend gap risk** and **swap cost** not present in
  H1–H3 — both are modelled.
- If H4 fails, the intraday hypothesis space (direction, volatility, calendar) is
  exhausted for now → **M3 continues with a swing / daily-bar hypothesis** (trend
  or long-run drift), which is a larger design shift to be drafted fresh.
