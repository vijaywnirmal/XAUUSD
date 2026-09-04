# H10 — the "200 EMA tap" strategy (trend-continuation pullback fade)

**Run:** 2026-09-04. `research/h10_ema200_tap.py`. 15-min Dukascopy bars, true
UTC, 2009-01 → (see note below). Engine costs: real per-bar spread + $6/lot
commission + 1-tick slippage.

## Spec (operator request + clarifications)

> "use 200 ema on 15 minute candle, where everytime a 15 candle taps the 200
> ema line, and if the candles are below the 200 ema line and when it taps
> the ema line, we sell"

- 15-min bars, **EMA200** of close.
- **Short setup:** downtrend context (candle closes below EMA200) whose high
  still reaches up to tap/cross the EMA — price pulled back into the average
  and closed back below it. Rest a sell-stop at that candle's low.
- **Long setup** (operator opted into the symmetric mirror): uptrend context
  (close above EMA200), low taps down to the EMA, closed back above it. Rest a
  buy-stop at that candle's high.
- **Stop-loss = the signal candle's own range; target = 2× that (1:2)** —
  operator's choice, consistent with the canonical 5-EMA bracket (H9b).
- **One trade per day**, no session filter (a 200-EMA context is a slower
  signal than the 5-EMA scalp, checked round the clock). Safety time-stop 200
  bars (~50h) if neither stop nor target fires.
- $1,000 account, 0.01 lot.

---

## Result — and an important caveat before the numbers

**The backtest stops generating trades after 4 in 2024.** This is not a data
gap — 15-min bars run cleanly to 2026-09. It is the engine's **ruin guard**:
cumulative losses cross **−$1,000 (the whole starting account) by early 2024**,
and the engine correctly refuses to open further trades once equity hits zero,
exactly as a real broker would margin-call the account. The strategy as specced
**would have wiped a $1,000 account before the walk-forward window even
finishes.** That is itself the headline result.

| Book | n | win% | exp $/trade | PF | net $ | maxDD $ |
|---|---|---|---|---|---|---|
| Random-direction null | 2,097 | 34% | −0.48 | 0.79 | −1,002 | −1,026 |
| **200-EMA tap** | 2,629 | 34% | −0.38 | 0.83 | **−1,000 (ruined)** | −1,021 |
| in-sample 2009–2022 | 2,455 | 34% | −0.38 | 0.83 | −924 | −957 |
| 2023 (walk-fwd) | 170 | 32% | −0.31 | 0.88 | −52 | −204 |
| 2024 (partial, pre-ruin) | 4 | 0% | −5.88 | 0.00 | −24 | −18 |

**In-sample vs the null: Welch t = +0.61, p = 0.541 — not distinguishable
from a coin flip.** Unlike the 5-EMA line (H9, consistently t ≈ 2.5–2.8 vs
null), the 200-EMA tap's choice of direction carries **no real information.**
The small in-sample gross edge (+$177 on 2,455 trades, ~7 cents/trade) is
statistical noise around zero, not a signal — it disappears entirely against
the null.

## Why

- 27,789 raw signal candles produce only 2,629 trades (one/day cap) — the
  setup fires constantly; a candle tapping its own 200-bar average from either
  side happens routinely, it isn't a rare or informative event on gold.
- Win rate 34% is barely above the 33% breakeven a 1:2 payoff needs — so close
  to exactly breakeven-gross that cost alone explains the loss; there's no
  edge for cost to erode, unlike H9 where a real signal existed and cost ate it.
- Median risk per trade $2.14 (a 15-min candle's own range) — a healthier cost
  ratio than H9b's 5-min version, but it doesn't matter because there's no
  gross edge to protect in the first place.
- Losing in 13 of 15 years, including every year 2009–2015 and 2020–2023 —
  not a regime-specific failure, it just doesn't work.

## Verdict

**KILL — cleanly, on both counts.** (1) No statistically real directional
signal: the 200-EMA tap's long/short choice performs identically to a random
coin flip (t = 0.61 vs null). (2) Even setting that aside, the strategy would
have **ruined a $1,000 account** by early 2024 at minimum lot size — this
isn't a "modest underperformer," it's a strategy that ends the account. Do not
trade this. No further iteration recommended: unlike the 5-EMA line, there is
no real signal underneath to fix by adjusting the exit — the entry itself
carries no information here.

Trade log: `research/h10_ema200_tap_trades.csv`.
