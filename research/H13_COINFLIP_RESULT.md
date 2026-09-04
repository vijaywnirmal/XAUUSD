# H13 — coin flip at the New York open, every day

**Run:** 2026-09-04. `research/h13_coinflip_ny_open.py`. 5-min Dukascopy bars,
true UTC, 2009–2026. Exactly what was asked: flip a coin at 13:00 UTC (NY
open) every day, heads = buy, tails = sell, 0.01 lot, **no stop-loss, no
take-profit**, hold to session-flat at 20:00 UTC. 4,568 flips available over
the period. 300 independent random-seed paths run to see the *range* of
outcomes, not just the average.

---

## Where we end up: broke, reliably

| | |
|---|---|
| Final equity (started at $1,000) | mean **−$2.9**, median **−$4.5**, range −$94.9 to +$819.1 |
| Paths ending below $1,000 | **100%** |
| Paths ending below $500 | **99.7%** |
| Paths that survive all 4,568 flips without hitting $0 equity | **0%** |
| Trades executed before the account runs out of money | mean **2,063 of 4,568 (45%)** — median 1,847 |
| Worst single-path drawdown | **−$1,806** (more than the entire starting account) |
| Mean per-trade net | **−$0.64** |

**Every one of 300 independent random paths blows the $1,000 account before
reaching the end of the 17-year test window** — on average less than halfway
through it (trade ~1,850 of 4,568, roughly 2016–17 if it ran in real time).

## Why — two separate effects, not one

1. **Cost is a steady, guaranteed headwind.** A coin doesn't know anything
   about gold, so the *gross* P&L of each flip is unbiased — genuinely 50/50.
   But every trade still pays spread + $6/lot commission + slippage, averaging
   **−$0.64/trade** here (a touch higher than the ~$0.40–0.50 seen elsewhere
   in this project, because holding the full NY session with no exit until
   20:00 tends to cross wider spread regimes than a quick scalp). Over ~4,500
   trades that alone is a **~$2,900 bill** on a $1,000 account — cost alone
   guarantees ruin eventually, with certainty, no randomness required.
2. **No stop-loss means unbounded per-trade risk.** Every other strategy in
   this project (H1–H12) paired every entry with a stop, precisely because a
   single trade's loss needs a ceiling. Here there is none: a position held
   for a full NY session (up to 7 hours) can lose far more than a few dollars
   if gold makes a real move against it — the worst path's drawdown (−$1,806)
   is larger than the whole account, which is only possible because a losing
   trade can run past the account's own equity before the next day's entry
   is blocked. That's what turns "slow cost bleed" into "gone within a few
   years" instead of "gone eventually, gradually, after decades."

## Bottom line

This confirms, very directly, the thing this entire project has been
demonstrating one hypothesis at a time: **direction without an edge is worth
exactly $0 before cost, and negative after it — and without a stop, the
account doesn't get to lose slowly, it gets to lose all at once.** It's the
cleanest possible restatement of why every real script here required (a) a
real, tested signal to overcome the guaranteed −$0.64/trade cost drag, and
(b) a stop-loss on every single entry, no exceptions.

Not a strategy candidate — an illustration, run once as asked.

---

## Follow-up: same coin flip, with a $5 stop / $10 target (1:2)

**Run:** 2026-09-04. `python -m research.h13_coinflip_ny_open --stop-d 5 --tgt-d 10`.
Identical setup, but every flip now carries a **fixed $5 stop-loss and $10
take-profit** (the session-flat 20:00 UTC becomes a backstop for the rare
trade that hits neither). 300 seeds again.

| | no SL/TP | **$5 SL / $10 TP** |
|---|---|---|
| Paths ending below $1,000 | 100% | 100% |
| Paths that never hit $0 equity | 0% | **1.0%** |
| Trades survived before ruin | mean 45% of 4,568 | mean **63%** of 4,568 |
| Worst drawdown | −$1,806 | **−$1,187** |
| Mean per-trade net | −$0.64 | **−$0.38** |

**Still ruins essentially every time (99–100%), just more slowly and less
violently.** Bounding the risk per trade helps exactly the way it's supposed
to: the worst-case drawdown shrinks by a third, and the account survives
roughly 40% more trades on average before running out. But it doesn't change
the outcome, because the two things that guarantee ruin are still both
present:

- **The direction is still a coin flip** — nothing about adding a bracket
  gives the entry any real information. With a 1:2 payoff, breakeven needs
  a 33% win rate; a fair, undirected coin against a symmetric-ish price
  process lands almost exactly there (win rate observed ≈33%, gross P&L
  ≈breakeven) — as it should, sanity-checking the engine.
- **Cost is still there and still adds up.** −$0.38/trade × ~4,500 available
  trades is still a ~$1,700 bill on a $1,000 account. A stop-loss caps how
  much *one* trade can lose; it does nothing about the fact that *every*
  trade has a small guaranteed cost and there's no edge to pay it back with.

**The lesson a stop-loss actually teaches here:** it converts "the account
can be wiped by a single bad session" into "the account bleeds out slowly,
predictably, at the rate of transaction cost" — a real improvement in *how*
you lose, not *whether* you lose. Turning that into *not losing* still
requires an actual edge, which a coin doesn't have and never will.

