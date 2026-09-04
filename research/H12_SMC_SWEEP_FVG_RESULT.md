# H12 — "Smart Money Concepts": sweep → displacement → FVG → equilibrium entry

**Run:** 2026-09-04. `research/h12_smc_sweep_fvg.py`. 5-min Dukascopy bars,
true UTC. Engine costs: real per-bar spread + $6/lot commission + 1-tick
slippage. Source: operator-supplied SMC/ICT recipe (see script docstring for
the full mechanical translation of each discretionary term — sweep,
displacement, FVG, equilibrium — into a fixed, non-fitted rule).

## Spec summary

Previous-day high/low (PDH/PDL) → sweep-and-reject candle (wicks through,
closes back) that also qualifies as a **displacement** candle (range ≥1.5×
the 20-bar average, closing in the outer 25% of its range) → confirmed
**Fair Value Gap** on the standard 3-candle ICT definition → market entry the
bar after price returns to the gap's **midpoint** (approximating the source's
"limit order at 50% equilibrium" — the engine only supports market/stop
fills, so this is filled one bar later at the open, if anything a slightly
*worse*, more conservative fill than a true limit) → active only in the
stated London/NY session windows → stop beyond the sweep candle's wick,
**fixed 1:2 R:R** target, one trade/day.

---

## Funnel and result

**5,394 displacement candles → 3,017 valid FVGs → 1,529 touched the
midpoint → 1,100 actual trades.** Each stage of the recipe survives roughly
half the prior stage — the full chain is a real filter, not vacuous.

| Book | n | win% | exp $/trade | PF | net $ | maxDD $ |
|---|---|---|---|---|---|---|
| Random-direction null | 1,100 | 36% | −0.46 | 0.74 | −504 | −525 |
| **SMC sweep/FVG** | 1,100 | 36% | −0.20 | 0.88 | −221 | −367 |
| in-sample 2009–2022 | 877 | 36% | −0.35 | 0.75 | −308 | −332 |
| 2023 (walk-fwd) | 70 | 34% | −0.37 | 0.76 | −26 | −41 |
| 2024–2026 (OOS spent) | 153 | 38% | +0.74 | 1.26 | +114 | −49 |

**In-sample vs the null: Welch t = +0.68, p = 0.495 — not statistically
distinguishable from a coin flip.** In-sample net expectancy is clearly
negative on its own terms (t = −3.57 vs zero, p < 0.001) — this isn't a
"real but sub-cost" result like H1 or H9; it's negative expectancy full stop,
losing in 10 of 14 in-sample years.

No ruin this time — drawdown stays contained (−$332 in-sample, well inside
the $1,000 account), because the fixed 1:2 bracket and one-trade/day cap keep
position risk bounded regardless of signal quality.

## Why

- 36% win rate against a 1:2 payoff needs ~33% to break even gross — it does
  clear that (+$75 in-sample gross on 877 trades, ~9 cents/trade) but real
  cost (spread + $6/lot + slippage, $383 in-sample) is roughly 5× the gross
  edge, same story as most kills here: whatever tiny directional information
  might exist is smaller than what it costs to act on it.
- Exit mix: 700 stops (64%), 384 targets (35%), 16 time-stops — the bracket
  resolves cleanly, not on timeouts; the mechanics work as designed, they
  just don't carry an edge.
- The 2024–2026 window is the only positive stretch (+$114, PF 1.26,
  153 trades) — reported per the project's convention for completeness, not
  as evidence: it's the already-spent OOS window, and 153 trades is too few
  to treat as confirmation on its own even if it weren't.

## Verdict

**KILL.** The full ICT/SMC chain — liquidity sweep, displacement filter, Fair
Value Gap, equilibrium re-entry, session timing — produces a mechanically
sound, well-behaved backtest (no ruin, clean exit mix, funnel that actually
filters) but **no real directional signal** (t = 0.68 vs null) and a net
in-sample loss. This is a different failure mode than H10/H11 (zero signal,
fast ruin) or H9 (real signal, sub-cost) — here the many discretionary
"confirmation" layers (sweep + displacement + FVG + session timing) behave
exactly as every other multi-condition filter has in this project: they
narrow the sample a lot (1,100 trades from potentially thousands of raw
sweeps) without adding real information. Consistent with H9e/H9f's finding
that stacking confirmations tends to remove signal, not sharpen it.

Trade log: `research/h12_smc_sweep_fvg_trades.csv`.
