# H9d — the 5 EMA strategy, let winners run (trail instead of a fixed target)

**Run:** 2026-09-04. `research/h9d_5ema_trail.py`. Same entry as H9/H9c —
5-EMA detachment fade, 5-min bars, NY window 13:00–20:00 UTC, one trade/day,
$5 initial stop. Fourth deliberate iteration on the 5-EMA line.

**What changed:** no fixed target. Once a trade is **+$5 (1R) in favour**,
the stop ratchets to **$5 behind the running close-based extreme** and keeps
trailing. Exit is stop, trail, or the 21:00 UTC session-flat — whichever comes
first. This directly answers the question H9c raised: the fixed $15 target
was rarely reached (11% of trades) because 41% timed out at the session flat
first: does removing the cap let more of those capture a bigger move?

---

## Result

| Book | n | win% | exp $/trade | PF | net $ | maxDD $ |
|---|---|---|---|---|---|---|
| Random-direction null | 1,763 | 38% | −0.57 | 0.77 | −1,002 | −1,008 |
| **5-EMA fade, trail** | 4,751 | 44% | **−0.059** | 0.98 | −283 | −673 |
| in-sample 2009–2022 | 3,803 | 44% | **−0.094** | 0.96 | −357 | −601 |
| 2023 (walk-fwd) | 257 | 46% | **+0.343** | **1.13** | **+88** | −107 |
| 2024–2026 (OOS spent) | 691 | 40% | −0.020 | 0.99 | −14 | −328 |

**Best result in the 5-EMA line so far, and the best of any intraday
hypothesis tested since H1.**

| | H9 (fixed 1:2) | H9c (fixed 1:3) | H9d (trail) |
|---|---|---|---|
| in-sample exp $/trade | −0.17 | −0.16 | **−0.09** |
| in-sample t vs 0 | −1.82 (p=0.068) | −1.53 (p=0.126) | **−0.96 (p=0.335)** |
| in-sample PF | 0.93 | 0.94 | **0.96** |
| 2023 walk-forward | −$51 | +$17 | **+$88, PF 1.13** |
| 2024–2026 | −$141 | +$102 | −$14 (essentially flat) |
| signal vs null (in-sample) | t=+2.72 | t=+2.54 | **t=+2.79 (p=0.005)** |

In-sample is now **statistically indistinguishable from breakeven** (t = −0.96,
p = 0.335 — not the "real but sub-cost" shape of H1 or H9/H9c any more, just
noise around zero). The 2023 walk-forward window is outright positive with a
PF above 1. The already-spent 2024–2026 window is a rounding error from flat
(−$14 on 691 trades). And the directional signal itself is as strong as it's
ever been (t = 2.79 vs the null).

## Mechanism

- Win rate rose to 44% (from 38–39% at fixed targets) — the trail locks in
  many small wins that a $10–15 fixed target would have missed or a stop
  would have given back.
- Exit mix simplified to two buckets: **3,242 stops (68%)**, **1,509
  session-flat (32%)** — the trail never lets a position sit at a fixed target
  waiting; once it activates it's either stopped out on the give-back or still
  running into the 21:00 flat. avg win $5.57 / avg loss −$4.39 — a much
  tighter win/loss ratio than the fixed-target versions, compensated by the
  higher win rate.
- Year-by-year is still mixed — 2010, 2011, 2016, 2018–2021, 2024 losing;
  2009, 2012, 2013, 2022, 2023, 2026 winning — but the losing years are
  smaller and the winning years comparable, which is what moved the aggregate
  toward zero.

## Verdict

**Still not net positive in-sample — technically another KILL under the
project's own bar** (needs to clear cost with room to spare, not sit at
statistical zero). But this is the closest anything intraday has come to
clearing that bar since the project started, and it did so by following the
data: H9 showed the direction was real but sub-cost; H9b showed widening the
stop is wrong; H9c showed widening the target helps but leaves money on the
table at the session cutoff; H9d removes that cutoff-driven cap and lands at
breakeven with a genuinely significant directional signal underneath.

**This is now four iterations on one family** (H9→H9d), at the edge of what
the project's own discipline allows before a result this close to the bar
needs to be either accepted as "still no", or checked once against the spent
out-of-sample window as a final confirmatory look rather than a fifth tuning
pass. Recommend stopping *tuning* here regardless of which way you want to
take it next — any further parameter change (a different trail distance,
activation R, or entry-window edit) risks curve-fitting to noise that already
sits at t≈1.

Trade log: `research/h9d_5ema_trail_trades.csv`.
