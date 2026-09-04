# NFP breakout straddle — backtest result

**Run:** 2026-09-04. `research/nfp_straddle.py`. Dukascopy 5-min bars, true UTC,
**212 NFP releases with a usable pre-release box, 2009-02 → 2026-08.**
Engine costs: real per-bar spread + $6/lot commission + release-window slippage.

Spec (operator request: *"backtest all NFP events, take a stoploss of $30 and set
a trade limit on both buy and sell side"*):

- On each NFP release (first Friday, DST-adjusted 12:30 UTC summer / 13:30 winter),
  measure the pre-release 30-min box (high/low of 12:00–12:30 or 13:00–13:30).
- Place an OCO pair: **buy-stop at box-high + $0.50**, **sell-stop at box-low − $0.50**.
  Whichever fills first within 90 min is the trade; the other is cancelled.
- **$30 fixed stop-loss.** No take-profit by default; exit session-flat at 20:00 UTC.
- One trade per NFP day, 0.01 lot, $1,000 notional account.

---

## Headline

| Book | n | win% | exp $/trade | PF | net $ | maxDD $ |
|---|---|---|---|---|---|---|
| **Random-direction null** (same days, coin-flip side) | 212 | 46% | **+0.32** | ~1.0 | +68 | — |
| **NFP breakout straddle** (3-tick slip) | 212 | 57% | **+3.19** | 1.69 | +676 | −121 |
| in-sample 2009–2022 | 168 | 57% | **+1.79** | 1.47 | +301 | −121 |
| 2023 | 12 | 75% | +9.29 | 3.30 | +111 | −30 |
| 2024–2026 (OOS window, already spent) | 32 | 53% | +8.25 | 1.93 | +264 | −121 |

The strategy beats its random-direction null by **~10×** on both per-trade
expectancy and net P&L. That is the first time anything in this project has
cleanly beaten its own null outside the fitting window.

Per-trade t-test vs zero:

| window | n | mean $ | t | p |
|---|---|---|---|---|
| in-sample 2009–2022 | 168 | +1.91 | **+1.87** | 0.064 |
| all 2009–2026 | 212 | +3.11 | +2.34 | 0.020 |

In-sample t = **1.87** — below the project's t > 2 "distinguishable" bar, but
close, and it is positive in **both** in-sample halves (2009–15 +$174, 2016–22
+$148) with only 5 losing years out of 18.

---

## What the edge actually is

The $30 stop is almost never hit: **13 of 212 trades** exit on the stop, 199 exit
at the 20:00 flat. So this is not really a "straddle with a $30 stop" — it is:

> *catch the direction of the NFP break, ride it to the US session close, with a
> wide disaster stop.*

That maps directly onto the descriptive [NFP study](NFP_STUDY_RESULT.md), which
found a **mild post-spike continuation** — the knee-jerk move keeps running to
session end (+11 bps mean, t = 2.24), it does **not** reverse. The breakout entry
is just a mechanical way to pick the side of that continuation. avg win $13.70,
avg loss −$10.78, avg hold 80 five-min bars (~6.7 h).

## Sensitivity

| variant | in-sample exp $/trade | in-sample PF |
|---|---|---|
| base, 3-tick slip | +1.79 | 1.47 |
| 20-tick slip ($0.20) | +1.45 | 1.36 |
| **50-tick slip ($0.50)** | **+0.85** | **1.20** |
| add 1.5R take-profit (20-tick slip) | +1.39 | 1.35 |
| buffer $0.20 (20-tick slip) | +1.91 | 1.51 |
| buffer $1.00 (20-tick slip) | +1.42 | 1.36 |

- **Slippage is the binding risk.** NFP is exactly when a retail CFD broker gives
  worst fills — 2–5× spread blow-out, requotes, stop slippage. At $0.50 of adverse
  fill the in-sample edge falls to **+$0.85/trade, PF 1.20** — still positive, but
  thin. On the interbank Dukascopy feed the release spread only widens 1.2–1.4×;
  a real Vantage fill will be worse and must be measured, not assumed.
- **A take-profit hurts** — capping the winner removes the session-continuation
  payoff that is the whole edge.
- Tighter entry buffer looks slightly better, but that is in-sample tuning; don't
  trust the $0.20 number.

## Caveats

- **Small absolute size.** ~12 trades/year × ~$1.8 in-sample = **~$20/year on a
  0.01-lot / $1,000 account ≈ 2%/yr**, against a −$121 (12%) drawdown. It scales
  with lot size and so does the drawdown.
- **Recent strength is partly an artifact.** 2023–2026 shows +$7–9/trade vs +$1.8
  in-sample, but gold's price roughly doubled over that span, so a fixed 0.01-lot's
  *dollar* move roughly doubled for the same *percentage* move. Normalise by price
  before believing the strategy "got better".
- In-sample t = 1.87 does not clear the t > 2 bar. One NFP family, tested once.
- OOS window (2024-07 → 2026-09) is already spent on H7; the 2024–2026 row here is
  reported for completeness, not as a held-out confirmation.

## Verdict

**Marginal positive — the first non-negative result in the project.** It beats its
random-direction null ~10×, is positive across both in-sample halves and 13 of 18
years, and rests on a mechanism (post-NFP continuation) that was independently
documented before this backtest. But the in-sample edge is **~$1.80/trade at
optimistic slippage, ~$0.85 at realistic slippage**, roughly 2%/yr at minimum lot,
with a 12% drawdown, and t just under the significance bar.

Not deployable as a standalone edge. Defensible use: a **small satellite overlay**
(one trade a month, fixed tiny size) *after* paper-trading ~6–12 live NFP releases
to measure the actual Vantage fill quality — if real slippage lands near the
$0.50 case, there is nothing left.

Trade log: `research/nfp_straddle_trades.csv`.
