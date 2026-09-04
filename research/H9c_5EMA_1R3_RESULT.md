# H9c — the 5 EMA strategy, $5 stop / $15 target (1:3)

**Run:** 2026-09-04. `research/h9_5ema.py --tgt-d 15`. Same signal and rules as
H9 (`research/H9_5EMA_RESULT.md`) — only the target changed, from $10 (1:2) to
**$15 (1:3)**. Stop stays fixed $5. Third deliberate iteration on the 5-EMA
line (H9 fixed 1:2, H9b canonical candle-range 1:2, this = fixed 1:3).

---

## Result

| Book | n | win% | exp $/trade | PF | net $ | maxDD $ |
|---|---|---|---|---|---|---|
| Random-direction null | 1,603 | 33% | −0.63 | 0.78 | −1,005 | −1,010 |
| **5-EMA fade, 1:3** | 4,752 | 38% | −0.10 | 0.96 | −475 | −841 |
| in-sample 2009–2022 | 3,804 | 39% | −0.16 | 0.94 | −594 | −749 |
| 2023 (walk-fwd) | 257 | 37% | **+0.07** | 1.02 | **+17** | −145 |
| 2024–2026 (OOS spent) | 691 | 32% | **+0.15** | 1.04 | **+102** | −216 |

**In-sample vs the null: Welch t = +2.54, p = 0.011** — still a strong,
significant directional signal (H9's 1:2 version was t = 2.72), and the
1:3 payoff moves the strategy **closer to breakeven** than 1:2 did:

| | H9 (1:2) | H9c (1:3) |
|---|---|---|
| in-sample exp $/trade | −0.17 | **−0.16** |
| in-sample net vs 0 | t = −1.82, p = 0.068 | t = −1.53, p = 0.126 |
| in-sample PF | 0.93 | 0.94 |
| 2023 walk-forward | −$51 | **+$17** |
| 2024–2026 | −$141 | **+$102** |

Widening the payoff instead of the stop (the fix flagged after H9, since H9b's
"widen the stop" attempt made things worse) works in the right direction: the
walk-forward and already-spent OOS windows both turn **net positive**, and the
in-sample t-stat against zero drops from marginally-significant-negative to
not-significant. It is *not* yet a positive edge in-sample — still −$594 net,
39% win rate against breakeven of 25% needed at 1:3 is comfortably above
breakeven gross, but real cost (spread + $6/lot + slippage) still exceeds the
gross edge (+$1,174 gross vs +$1,768 cost, in-sample).

## Mechanism

- Exit mix shifted toward time: 2,252 stops (47%), only 532 targets (11%) hit
  the wider $15 target, 1,968 session-flat (41%, up from 34% at 1:2) — a lot of
  trades now run out the clock rather than resolving on the bracket, since a
  $15 move on a 5-min entry inside a single NY session is a big ask.
- Consistent losing years dominate in-sample (11 of 14, same pattern as H9),
  but 2023, 2024 and 2026 are individually positive — 2026 strongly so (+$213,
  n=174, a partial year).

## Verdict

**Still net negative in-sample — KILL as a standalone rule.** But this is
progress, not another dead end: widening the *target* (not the stop, which
H9b showed backfires) pushed the strategy from "loses more than it wins" toward
breakeven, turned both out-of-in-sample windows positive, and kept the
directional signal strongly significant (t = 2.54). The 5-EMA fade direction
is real; the remaining problem is that a large fraction of trades now time out
at session-flat rather than reaching the wider target, capping the upside that
the 1:3 payoff is supposed to capture.

Natural next question if you want to keep going: does letting winners run
further (trailing stop after some favourable move, or a longer time-stop
instead of a fixed 21:00 flat) convert more of those session-flat exits into
target hits — since the direction is already shown to be non-random?

Trade log: `research/h9_5ema_trades_sl5_tp15.csv`.
