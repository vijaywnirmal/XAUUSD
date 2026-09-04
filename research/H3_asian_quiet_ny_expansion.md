# Hypothesis H3 — Asian-quiet → NY range expansion (XAUUSD)

**Drafted:** 2026-09-04
**Status:** DRAFT — awaiting sign-off, then run once end-to-end on in-sample (M3).
**Iteration:** 1 of ≤5 for the H3 family.

Prior hypotheses — all KILLED:
- **H1 / H1b — NY opening-range breakout.** Thin, non-robust directional edge.
- **H2 — London→NY momentum continuation.** Falsified: London direction carries
  no information about NY direction (trend vs random Welch t = −0.49).

**Both were purely directional and failed the same way.** Gold's NY-session
*direction* looks close to a random walk at the 5-min / daily-session scale. H3
deliberately stops betting on direction: it bets on **whether a large move
happens**, and takes it whichever way it goes.

---

## 1. Mechanism (why this could work)

Volatility clusters and alternates between **contraction** and **expansion** — a
well-documented regularity (narrow-range days / NR7, Bollinger squeezes, ATR
contraction→expansion). Gold's quietest window is the **Asian session
(00:00–07:00 UTC)**.

Claim: **when the Asian session is unusually quiet, the NY session range expands.**
An unusually narrow Asian night means positioning is stale and no catalyst has
landed — conditions are *coiled*. When real liquidity and information arrive
(London 07:00 UTC, US data 13:30 UTC, US equity open 14:30 UTC) the compression
**releases as an expanded move** during the NY session.

The quiet night is a **precondition for a big range**, not a predictor of
direction. So the vehicle is **direction-neutral**: a two-sided straddle around
the Asian range. We do not guess up or down — we position to catch the expansion
either way, and rely on the opposite-side stop when it's a fake-out.

If H3 works it also yields a reusable **volatility filter** that could be bolted
onto revived directional ideas.

---

## 2. Exact rules (all parameters fixed a priori)

| Item | Value | Rationale |
|---|---|---|
| Instrument / data | XAUUSD, Dukascopy canonical, **5-min bars**, in-sample 2009-01 → 2022-12 |
| **Asian window** | 00:00–07:00 UTC (84 bars); need ≥ 67 present | the quiet reference night |
| `asian_range` | high − low over the window |
| `asian_range_norm` | `asian_range / ATR20d` (daily ATR, 5-min→daily OHLC, **shifted** so day *t* uses *t−20..t−1*) | "how quiet", regime-normalised |
| **Quiet precondition** | trade the day only if `asian_range_norm[t] ≤ 30th percentile of asian_range_norm over the prior 60 days` | "unusually quiet *for the recent regime*" — no absolute threshold. ~30 % of days (~1,096 in-sample). |
| **Straddle reference** | the Asian range itself | most faithful to "the coil breaks"; bigger box → fewer whipsaws than a tiny London box |
| Buffer | `max(0.05 × asian_range, 3 ticks)` |
| Entry | **OCO two-sided resting stop orders**: buy-stop at `asian_high + buffer`, sell-stop at `asian_low − buffer`. First side to trade through fills; the other is cancelled. One trade/day. | catch the expansion either direction |
| Entry window | first break in **08:00 → 16:00 UTC**; no entry after 16:00 | after a quiet night the release can come from the London open, the 13:30 data, or the 14:30 equity open — wide window on purpose |
| Initial stop | **opposite side of the Asian range** — long → `asian_low`, short → `asian_high`. R ≈ `asian_range + 2·buffer` (median ~$4.6 on quiet nights) | if price breaks up then reverses the entire Asian range, the "coil released up" thesis is dead |
| Target | **none** — capping a compression→expansion trade defeats the premise (H1's lesson) |
| Exit | **trailing stop**: activate at **+1.5 R**, then trail at **1.5 × asian_range** off the running close extreme. **Hard flat at 21:00 UTC** otherwise. | give the expansion room (looser than H1b's failed 1R / 1×); 21:00 = US futures close, later than H1/H2 because a post-quiet move can run into the NY afternoon |
| Re-entry | none — one completed trade per day |
| Sizing (stat test) | fixed **0.01 lot** |
| Sizing (equity-curve run) | `risk_pct = 0.5 %`, $1,000 start (R ~$4.6 → ~0.01 lot, so the risk fraction is roughly honoured for this idea) |
| Costs | engine default — real per-bar Dukascopy spread + 1 tick/side slippage + $6/lot commission |

Engine wiring: set BOTH `long_stop` and `short_stop` on every entry-window bar of
a quiet day (engine's one-position + `one_trade_per_day` gives OCO for free);
`stop_dist` = `asian_range + buffer`; `trail_dist` = `1.5 × asian_range`;
`trail_activate_r = 1.5`; `session_flat_hour_utc = 21`; `one_trade_per_day = True`;
no `target_dist`.

---

## 3. Falsifiable predictions & pass criteria (in-sample)

H3 **passes M3** and proceeds to M4 only if **all** of:

| Metric | Threshold |
|---|---|
| Trade count | ≥ 300 (expect ~700–900) |
| Expectancy after costs | **> 0** in $ and R; predict ≥ **+0.08 R/trade** (the premise is a *big* move, so the bar is higher than H1/H2) |
| Profit factor | ≥ 1.25 |
| **Conditional beats unconditional** | the *same straddle on all days* (no quiet filter) has **lower** expectancy_R than the quiet-conditioned version — the direct test of "does Asian-quiet predict NY expansion" |
| Beats the coin-flip straddle | a **one-sided** straddle (random side per day, same stop/exit) does **worse** — the two-sidedness must earn its place |
| Max drawdown (0.5 %-risk run) | ≤ 20 % |

**Kill H3** (clean negative → H4) if any of:
- expectancy ≤ 0 after costs, or
- **conditional ≈ unconditional** (the quiet precondition adds nothing), or
- indistinguishable from the coin-flip straddle, or
- profit factor < 1.10, or
- the result rides on ≤ 3 outlier trades or a single regime (Monte-Carlo p50 / by-year).

---

## 4. What M3 produces

1. `research/h3.py` — the H3 signal generator + runner: success-bar table, the
   **unconditional** (all-days) and **coin-flip straddle** comparisons,
   Monte-Carlo, expectancy by year, and a slice of realised NY range (18:00 UTC
   high−low) on quiet vs non-quiet days (a direct check of the mechanism,
   independent of the trade rules).
2. `research/H3_RESULT.md` — dated write-up: metrics, both comparisons, verdict
   (PASS → M4, or KILL → H4), surprises. **Committed pass or fail.**
3. No parameter sweeps. If H3 fails on a marginal number, the first *deliberate*
   iteration-2 lever is the quiet threshold (30 % → tighter) or the trigger box
   (Asian range → first-London-hour box), decided explicitly.

---

## 5. Known risks to this hypothesis

- This shares mechanics with H1 (ORB) — the defence is that it is (a) *conditioned*
  on a volatility precondition that is itself the thing being tested, and (b)
  **direction-neutral**, so it does not depend on the thin break-direction edge
  that H1's null-beat lived on.
- "Quiet → expansion" is a crowded idea; if it ever worked cleanly in gold it may
  be arbitraged. A weak-but-positive conditional-vs-unconditional gap would still
  be informative (keep the vol filter, drop the straddle).
- **Whipsaw risk:** on a quiet night the market can break the Asian range, stop
  out, then break the other way — the OCO only fires once/day, so a first-break
  fake-out is a full loss with no recovery. The by-`exit_reason` mix and the
  "stopped within 60 min" slice will show how often this bites.
- Both-sides-in-one-bar (a gap or a news spike through the whole Asian range on a
  single 5-min bar): the engine takes the long side by construction — rare,
  logged.
- Regime dependence: expansion edges may concentrate in high-macro-uncertainty
  years. Expectancy-by-year is the check; an edge that lives in 3 of 14 years is
  not robust.
