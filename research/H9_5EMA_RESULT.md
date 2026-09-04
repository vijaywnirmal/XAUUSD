# H9 — the "5 EMA" strategy, mechanised

**Run:** 2026-09-04. `research/h9_5ema.py`. 5-min Dukascopy bars, true UTC,
2009-01 → 2026-08. Engine costs: real per-bar spread + $6/lot commission +
1-tick slippage.

## Spec (operator request)

Subasish Pani's 5 EMA fade, with the operator's fixed bracket:

- 5-period EMA of close on 5-min bars.
- **Short setup:** a candle whose entire range sits above the EMA (low > EMA)
  → rest a sell-stop at that candle's low.
- **Long setup:** a candle whose entire range sits below the EMA (high < EMA)
  → rest a buy-stop at that candle's high.
- The resting order refreshes to the newest signal candle each bar; a candle
  touching the EMA cancels it.
- **Fixed $5 stop / $10 target** (keeps Pani's 1:2), **one trade per day** —
  the first fill inside the NY window 13:00–20:00 UTC. Safety exit 21:00 UTC.
- 0.01 lot, $1,000 account.

---

## Result

| Book | n | win% | exp $/trade | PF | net $ | maxDD $ |
|---|---|---|---|---|---|---|
| Random-direction null (same entry bars) | 1,599 | 35% | −0.63 | 0.77 | −1,000 | −1,010 |
| **5-EMA fade** | 4,752 | 40% | −0.18 | 0.94 | −832 | −991 |
| in-sample 2009–2022 | 3,804 | 41% | −0.17 | 0.93 | −640 | −867 |
| 2023 | 257 | 39% | −0.20 | 0.93 | −51 | −146 |
| 2024–2026 | 691 | 37% | −0.20 | 0.94 | −141 | −223 |

**In-sample vs the null: Welch t = +2.72, p = 0.007.** That is the single
strongest raw directional signal found anywhere in this project — the 5-EMA
fade direction is genuinely non-random, comfortably clearing the earlier
"distinguishable" bar (t > 2) that H1's opening-range break only brushed
(t = 2.36) and H2 failed outright (t = −0.49).

**But it still loses money.** In-sample gross is positive (+$1,103, +$0.29/trade
— the win rate of 41% is above the ~33% breakeven for a 1:2 payoff) but real
cost (+$1,667 even at **zero** extra slippage — just spread + $6/lot commission)
exceeds it. Net in-sample: **−$0.17/trade, PF 0.93.**

This is the same shape as H1 (ORB): a real, statistically detectable edge that
is smaller than the fixed cost of taking the trade. The reason it's worse here
than H1 is scale — a **$5 stop is tiny**. Spread + commission (~$0.40–0.45 per
round trip at 0.01 lot on Dukascopy-quality spreads; a real Vantage fill will be
worse) is **~9% of the $5 risked**, versus a low single-digit percentage on a
wider ORB-style stop. High trade frequency (4,752 trades in 17 years, ~280/yr)
compounds a small per-trade cost into a large total ($2,297 over the run — more
than 2.5× net loss).

- Consistent negative sign across most years (12 of 18 losing, including every
  year 2015–2021). Not a single-year artifact like H2.
- Exit mix: 2,160 stops (46%), 981 targets (21%), 1,611 session-flat (34%) —
  the setup does resolve mostly on the intended bracket, not on timeouts.
- `research/h9_5ema_trades.csv` has the full trade log.

## Verdict

**KILL as specified.** The fade direction carries real information (p = 0.007
vs the null) — the strongest raw signal this project has found — but a fixed
$5/$10 bracket at retail cost is sub-scale: cost eats roughly 60% of the gross
edge even with zero added slippage. Do not trade this exact spec.

**What would be worth one more look, if you want it:** the *signal* (5-EMA
detachment direction), not this bracket. A wider stop/target (diluting the fixed
$0.40–0.45 cost as a fraction of risk — the same lesson H1 taught) or
risk-based position sizing instead of a fixed $5 risk could turn a real t=2.7
signal into something cost survives. That would be a genuine H9b iteration
(one more deliberate try, same discipline as H1→H1b), not a re-run of this one.
