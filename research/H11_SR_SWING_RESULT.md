# H11 — intraday support/resistance swing fade, with risk sizing

**Run:** 2026-09-04. `research/h11_sr_swing.py`. 15-min Dukascopy bars, true
UTC. Engine costs: real per-bar spread + $6/lot commission + 1-tick slippage.
New family (not related to the 5-EMA or 200-EMA lines).

## Spec (operator request + clarifications)

- 15-min bars. **Support/resistance = prior 96-bar (24h) swing extremes** —
  the lowest low / highest high of the preceding 24 hours, computed causally.
- **Fade the level** (not a breakout): a candle that taps the level and closes
  back on the other side of it is the signal candle. Rest a stop order at
  that candle's opposite extreme (buy-stop at its high off a support tap,
  sell-stop at its low off a resistance tap).
- **Structure stop**: placed just beyond the level itself (support − $0.50,
  resistance + $0.50) — if the level truly breaks, the trade thesis is wrong.
- **Trail once +1R in favour** (same mechanic as H9d, the best result in the
  project) — no fixed target.
- **Position size: risk 1% of current equity per trade** (`size_mode=
  "risk_pct"` in the engine) — lot size derived from the stop distance,
  scaling with the account instead of a fixed 0.01 lot.
- One trade/day, 24h (no session filter), safety time-stop 200 bars (~50h).

---

## Result: ruined in 5 years, and the direction carries no information at all

| Book | n | win% | exp $/trade | PF | net $ |
|---|---|---|---|---|---|
| Random-direction null | 987 | 36% | −1.01 | 0.67 | −1,001 |
| **S/R swing fade** | 1,007 | 35% | −1.00 | 0.69 | −1,002 (ruined) |

**Welch t = +0.06, p = 0.953 — the closest to a pure coin flip anything in
this project has measured.** Every other kill still had *some* separation
from its null (H10's 200-EMA tap was the previous "no signal" case at t=0.61);
this is flatter still. Fading a 24-hour swing high/low on gold carries
**zero** detectable directional information.

**The account is wiped by 2013 — five years in, the fastest ruin of any
strategy tested**, faster than H10 (2024) or H9e (2018). The risk-based
sizing (1% of equity per trade) is not the cause of the loss — it's a
multiplier on a loss that was already there: 35% win rate against a ~1.26:1
average win/loss ratio is a clear negative-expectancy bet regardless of size,
and risking a fixed % of equity just compounds that faster than a fixed lot
would (each loss shrinks the risk base, each near-miss before ruin still
trades an outsized position relative to the shrunken account).

## Why

- 16,380 raw signal candles (7,073 long + 9,307 short) → only 1,007 trades
  survive the one-trade/day cap before ruin — the setup is extremely common
  (a 24h swing gets tapped-and-rejected on 15-min gold routinely), which is
  itself evidence it isn't a rare, informative structural event.
- **1,006 of 1,007 trades exit on the stop** — the trail almost never
  activates. Once a fade against a 24h high/low is wrong, it tends to be wrong
  immediately, not marginally; the "let it run" mechanic that helped H9d never
  gets the chance to engage here.
- Every single year (2009–2013, before ruin) is a loser, no exceptions.

## Verdict

**KILL — the most decisive negative result in the project.** No directional
signal whatsoever (t = 0.06 vs null) and a five-year ruin. Fading a rolling
24-hour swing extreme on gold is, as tested, indistinguishable from picking a
random direction and paying cost. Two possible reasons, not run: (1) fading
level touches may simply be the wrong idea on an instrument this liquid — a
24h high/low on gold isn't a scarce, defended level the way it might be on a
thinner market; (2) the specific 96-bar lookback and $0.50 buffer are
unfitted first guesses, not surveyed — but a t-stat this flat leaves little
reason to expect a parameter tweak would surface a real signal underneath.

Trade log: `research/h11_sr_swing_trades.csv`.
