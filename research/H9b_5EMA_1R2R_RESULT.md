# H9b — the 5 EMA strategy, canonical bracket (candle range, 1:2)

**Run:** 2026-09-04. `research/h9b_5ema_1r2r.py`. Same signal as H9
(`research/h9_5ema.py`) — 5-min bars, candle fully detached from EMA5 = signal
candle, stop order at its extreme, NY window 13:00–20:00 UTC, one trade/day.
Deliberate second iteration per operator request, same discipline as H1→H1b:
run once, no further tuning after seeing the result.

**What changed from H9:** stop-loss = the signal candle's own opposite extreme
(its range), target = 2× that range — Pani's actual 1:2 rule, replacing H9's
fixed $5/$10.

---

## Result

| min signal-candle range | n | win% | in-sample exp $/trade | PF | t (net vs 0) | Welch t (vs null) |
|---|---|---|---|---|---|---|
| none (raw rule) | 4,357 | 38% | −0.199 | 0.81 | −5.12 | **+3.28** (p=0.001) |
| ≥ $1.00 floor | 3,805\* | 38% | ~ −0.20 | ~0.8 | −4.10 | +1.54 (p=0.123) |
| ≥ $2.00 floor | 2,760 | 36% | −0.304 | 0.84 | −3.34 | +1.57 (p=0.116) |

\* trade count differs by run; in-sample subset shown in each variant.

**Net loss in every variant, and it gets worse, not better, as the bracket
widens.** In-sample: −$756 (raw), −$575 (≥$2 floor) on 3,800–1,900 trades.

## Why the raw rule looked deceptively strong, and why it isn't

The unfiltered rule let signal candles with a **near-zero range** through — a
detached candle can be a near-doji. Those trades have a tiny stop *and* a tiny
target (2× the tiny stop), so the fixed ~$0.40–0.45 round-trip cost dominates
completely — one such trade blew up the mean R-multiple calculation to
−39,630,417,527 (division by a risk near zero) before a range floor was added.
That garbage tail is also what drove the headline **t = +3.28 vs the null** —
once a sane $1 floor removes the degenerate candles, the same signal-vs-null
comparison drops to **t = 1.54, not significant.** The strong H9 result (fixed
$5/$10, t = 2.72) does not carry over to the canonical variable bracket; H9's
edge was specifically about the *direction*, not about copying the candle's own
range as the stop.

## Mechanism, restated

- Exit mix (raw): 2,626 stops (60%), 1,614 targets (37%), only 117 session-flat
  (3%) — nearly every trade resolves on the bracket, as intended.
- Win rate 36–38% at a nominal 1:2 payoff needs 33% to break even gross — it
  clears that bar (gross positive, +$881 in-sample raw) — but real cost consumes
  it. Median risk is **~$1.2–2.6**, i.e. cost is 15–35% of the money risked per
  trade, worse than H9's fixed-$5 case (~9%). A stop sized off a 5-min candle's
  own range on gold is simply too tight for retail per-trade costs at any floor
  tested.
- Consistently negative: every one of 2009–2025 lost in-sample except 2013 and
  2009 (only at the ≥$2 floor); no era carries it.

## Verdict

**KILL.** The canonical Pani bracket (candle-range stop, 1:2 target) loses
money in-sample under every variant tried, and the appearance of a strong
directional signal in the raw run was an artifact of degenerate near-zero-range
signal candles, not a real edge surviving a sane cost floor. H9's fixed $5/$10
bracket remains the *better* of the two versions tested (t = 2.72 vs null, real
though sub-cost) — copying the candle's own range as the stop makes things
worse, not better, because gold's 5-min candle ranges are frequently smaller
than the fixed round-trip cost of a trade.

This closes the 5-EMA line: two brackets tried, both sub-cost, the natural
"widen the stop" idea (this one) went the wrong direction instead.

Trade log: `research/h9b_5ema_1r2r_trades.csv`.
