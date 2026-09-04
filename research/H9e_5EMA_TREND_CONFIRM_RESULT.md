# H9e — the 5 EMA fade, with a higher-timeframe trend confirmation

**Run:** 2026-09-04. `research/h9e_5ema_trend_confirm.py`. Same entry/exit as
H9d (the best-performing bracket in the 5-EMA line: 5-min EMA5 detachment
fade, $5 stop, trail $5 once +1R, session-flat 21:00 UTC, NY window
13:00–20:00 UTC, one trade/day) — reopened for **one deliberate, pre-registered
test**, per operator request, of whether a trend confirmation improves it.

## What was added

A classic "buy dips in an uptrend, sell rallies in a downtrend" filter:

- 15-min **EMA200** (same definition as H10), attached to every 5-min bar
  causally — from the last **fully closed** 15-min bar as of that bar's start,
  via `merge_asof`, no look-ahead.
- A **short** fade (candle spiked above EMA5) is only taken if price is
  **below** the 15-min EMA200 — selling a rally inside a downtrend.
- A **long** fade (candle dropped below EMA5) is only taken if price is
  **above** the 15-min EMA200 — buying a dip inside an uptrend.
- Disagreeing setups are skipped entirely, not traded a different way.

This combines H9's independently-real signal (5-EMA fade direction, t ≈ 2.7–2.8
vs null) with H5's finding that gold trend carries *some* real information —
the one theoretically defensible version of "double confirmation" flagged
after the operator's question, as opposed to filtering with H10's 200-EMA-tap
signal, which had already been shown to carry none.

---

## Result: the confirmation made it worse, not better — and ruined faster

| Book | n | win% | exp $/trade | PF | net $ |
|---|---|---|---|---|---|
| Random-direction null | 1,972 | 40% | −0.51 | 0.78 | −1,001 |
| **5-EMA fade + trend confirm** | 2,697 | 40% | −0.37 | 0.83 | **−1,000 (ruined)** |

**The $1,000 account is wiped by 2018** — nine years in, *faster* than H10's
ruin (2024) and far faster than the unconfirmed H9d, which never ruined at
all. Trading stops generating after that (same ruin-guard mechanic as H10;
see its write-up for why that's correct behaviour, not a bug).

**The directional signal that made H9/H9c/H9d real disappears under this
filter:** in-sample vs the null, **Welch t = +0.85, p = 0.394** — down from
H9d's t = +2.79 on the *unconfirmed* version of the identical entry/exit rule.
Requiring HTF trend agreement did not sharpen the edge; it **destroyed** it.

| | H9d (unconfirmed) | H9e (+ trend confirm) |
|---|---|---|
| in-sample exp $/trade | −$0.09 | **−$0.37** |
| in-sample t vs 0 | −0.96 (p=0.335) | **−3.58 (p<0.001)** |
| signal vs null | t=+2.79 (p=0.005) | **t=+0.85 (p=0.394)** |
| account survives in-sample? | yes | **no — ruined by 2018** |

## Why

Only 36–42% of the raw 5-EMA setups pass the trend filter — most detachment
candles happen when price is chopping around the 200 EMA, not clearly on one
side of it, which on 5-min gold is most of the time. What the filter mostly
did was select for a *specific*, apparently lower-quality subset of the
original signal (candles that detach from EMA5 while ALSO clearly trending on
the 15-min chart) while providing no compensating edge. This matches the
project's two earlier filter experiments exactly:

- H1b added a "confirmation" filter to H1's real signal → t collapsed 2.36→1.01.
- H5-forensics gated H5 to its own past winners' regime → helped in-sample,
  hurt walk-forward.
- **H9e adds a filter to H9's real signal → t collapsed 2.79→0.85, and the
  account now ruins nine years earlier than the unconfirmed version.**

Three for three: every confirmation/filter tried in this project has reduced
or destroyed the underlying signal rather than sharpening it. This isn't bad
luck — a fixed post-hoc rule that shrinks the sample by 60%+ needs to bring
real new information to be worth its cost in trades, and on gold's 5-min/
15-min structure, "is the higher timeframe also trending" turned out to be
close to noise conditional on the 5-EMA setup already having fired.

## Verdict

**KILL, decisively — and closes the double-confirmation question.** Combining
the 5-EMA fade with a 15-min 200-EMA trend filter does not produce a better
strategy; it produces a worse one that ruins the account faster than either
ingredient alone. The unconfirmed H9d result (breakeven, real signal) remains
the best of the whole 5-EMA line and stays declined per the operator's earlier
"accept it as still no" decision. No further filter combinations are
recommended on this signal.

Trade log: `research/h9e_5ema_trend_confirm_trades.csv`.
