# H9f — the 5 EMA fade, with the OPPOSITE trend filter

**Run:** 2026-09-04. `research/h9e_5ema_trend_confirm.py --counter-trend`.
Same H9d entry/exit (5-min EMA5 detachment fade, $5 stop, trail $5 once +1R,
session-flat 21:00 UTC, NY window, one trade/day). Operator's question — "do
the opposite of what we're doing" — tested as: instead of H9e's filter (only
take the fade when it *agrees* with the 15-min 200-EMA trend), only take it
when it **disagrees** — a pure counter-trend fade with no HTF backing at all
(sell an overextension *inside an uptrend*, buy a dip *inside a downtrend*).

---

## Result: better than H9e, still worse than doing nothing

| | H9d (no filter) | H9e (trend-agree) | **H9f (trend-disagree)** |
|---|---|---|---|
| in-sample exp $/trade | **−$0.09** | −$0.37 | −$0.10 |
| in-sample t vs 0 | −0.96 (p=0.335) | −3.58 (p<0.001) | −1.07 (p=0.285) |
| signal vs null (t) | **+2.79 (p=0.005)** | +0.85 (p=0.394) | +1.77 (p=0.077) |
| in-sample PF | 0.96 | 0.83 | 0.96 |
| account ruins in-sample? | no | **yes, by 2018** | no |
| 2023 walk-forward | +$88, PF 1.13 | no trades (ruined) | +$1, PF 1.00 |
| 2024–2026 | −$14 (flat) | no trades (ruined) | **−$420, PF 0.82** |

The counter-trend filter is a real improvement **over H9e** — it doesn't ruin
the account, and the signal-vs-null t-stat partially recovers (0.85 → 1.77,
though still short of significance). But it is **not better than the
unfiltered H9d** on any dimension that matters: weaker signal (t 1.77 vs
2.79), worse in-sample expectancy (−$0.10 vs −$0.09, about the same), and
markedly worse in the already-spent OOS window (−$420 vs −$14).

## What this settles

Both directions of the trend filter — agree (H9e) and disagree (H9f) — **make
the base signal worse than leaving it alone.** That's the informative result:
the 5-EMA fade's real edge (t ≈ 2.79 vs null, unfiltered) doesn't depend on
the 15-min 200-EMA trend context one way or the other. Splitting the sample by
it in either direction just removes trades and adds noise; it isn't isolating
a better sub-population, because the higher-timeframe trend isn't where the
signal lives. Filtering the input around a real signal, in *both* directions
tested, underperforms not filtering at all — as decisive a "the base signal
doesn't want this ingredient" result as the project has produced.

## Verdict

**KILL.** Confirms and completes H9e: the 5-EMA fade's edge is independent of
15-min trend context, in both directions. The unconfirmed H9d result remains
the best of the line, and stays declined per the operator's "accept it as
still no" decision. No further trend-filter variants are worth testing on
this signal — both halves of the obvious split have now been tried.

Trade log: `research/h9f_5ema_counter_trend_trades.csv`.
