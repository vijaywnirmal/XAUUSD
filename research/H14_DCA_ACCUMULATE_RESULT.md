# H14 — buy 0.01 lot every month, never sell, add $100 cash separately

**Run:** 2026-09-04. `research/h14_dca_accumulate.py`. Not a signal test — an
accounting simulation of the operator's literal spec (confirmed via
clarification): every month, buy a **fixed 0.01 lot** CFD position and hold
it forever; **separately**, add **$100 cash** to the account that month.
15-min Dukascopy bars, true UTC, 2009-01 → 2026-09 (213 months). Entry
friction only (half-spread + half round-trip commission) — no exit cost is
charged since nothing is ever sold.

---

## The headline number looks great — and is misleading on its own

| | |
|---|---|
| Cash contributed over 17.7 years | $21,300 |
| Lots accumulated | 2.13 (213 oz notional) |
| Gold price | $880 → $4,480 (+409%) |
| **Final notional exposure** | **$954,279** |
| **Final account equity** | **$605,989** |
| Return on cash contributed | **+2,745%** |

That number is real arithmetic, but it is the wrong headline. **Read the
year-by-year equity path first:**

| Year | Equity | Notional | Cash in | Lots |
|---|---|---|---|---|
| 2012 | $22,243 | $82,310 | $4,800 | 0.48 |
| **2013** | **−$1,054** | $75,060 | $6,000 | 0.60 |
| **2014** | **−$7,084** | $82,873 | $7,200 | 0.72 |
| **2015** | **−$13,317** | $89,408 | $8,400 | 0.84 |
| 2016 | −$3,871 | $112,566 | $9,600 | 0.96 |

**The account goes deeply negative for four straight years (2013–2016) —
this is not a hypothetical loss, it is the account going bust.** A real
broker liquidates a leveraged position when equity hits zero; it does not
let it run to −$13,317 and wait around for gold to recover in 2019–2025. This
backtest's headline +2,745% is a survivorship artifact of letting a real
margin call not happen. **In practice, this strategy would have wiped the
account by 2013–2014 and never seen a cent of the eventual gain.**

## Why it goes negative: unbounded, growing leverage

Buying a *fixed lot size* every month, independent of price or account size,
means the notional exposure grows every month **regardless of how much cash
has actually been contributed** — nothing ties position size to the account.
By 2015: $8,400 contributed, $89,408 notional — **10.6× leverage on cash in**,
and climbing every single month whether gold goes up or down. When the 2011
gold peak ($1,900) unwound to ~$1,050 by December 2015 (a real, well-known
~45% correction), that ~45% drawdown hit a *constantly growing* position, not
a fixed one — new lots kept adding exposure at the top of the range right
before the fall, with no mechanism to slow down, size down, or stop.

By the end of the whole run, leverage is still **1.6× equity and 44.8× the
cash actually contributed** — the strategy never stops adding leveraged
exposure, it just eventually got bailed out by gold nearly quintupling.

## Verdict

**Do not do this.** The mechanism ("buy the same size every month forever,
no matter what") has no risk control at all — no position sizing relative to
capital, no de-risking after a drawdown, nothing. It happened to work over
this particular 17-year window because gold had one of its best runs in
history, but the same mechanical rule would have **bankrupted the account
mid-way through**, in real trading, years before that run paid off. This
isn't a subtle backtest flaw — the equity curve going negative *is* the
result: a strategy whose own accounting shows it goes bust cannot be rescued
by whatever happens afterward.

## The thing that actually works: unleveraged dollar-cost-averaging

For contrast, if the $100/month had instead simply **bought $100 of gold**
each month (ounces = $100 / price that month — no lot mechanics, no leverage,
this is what "DCA a physical gold ETF," the project's actual standing
recommendation, means):

| | |
|---|---|
| Cash contributed | $21,300 |
| Ounces bought | 14.06 |
| Final value | $62,980 |
| Return | **+195.7%** |
| Worst-case equity | **never negative — the position can only be worth what was paid for it, at minimum $0 on the way to whatever gold is worth** |

Smaller headline return than the leveraged version's lucky outcome, but it
**cannot go bankrupt** — the maximum loss is capped at the cash contributed,
never amplified, and it never requires surviving a margin call to eventually
be right. This is the version worth actually doing, and it's the same
conclusion `M3_CONCLUSION.md` already reached.
