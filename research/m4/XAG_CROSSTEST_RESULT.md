# Cross-instrument test — primary lead on XAG/USD  (2026-09-10)

Silver was never used in this project, so its full Dukascopy history is a clean,
independent read.  This ran the **frozen** primary-lead rule
(`research/m4/LAYER_C_ADDENDUM_primary_lead.md`) on silver with **no re-tuning**.

- Data: `data_pipeline/fetch_xag_dukascopy.py` → PG table `bars_15min_xag`,
  **284,129** 15-min bars, **2014-09 → 2026-09** (~12 years; Dukascopy XAG/USD
  M15 starts Oct 2014).
- One necessary adaptation (not a signal change): the frozen `SIGMA_FLOOR`
  (0.4199) is an absolute *gold* price and would drop 98 % of silver bars.  The
  instrument-agnostic form of that data-hygiene rule — "this instrument's own
  ATR14 1st percentile" — is **0.0149** for silver.  Every signal parameter
  (RV20=20, tercile=1/3, A3 lookback=96, cooldown=16, horizons {32,96},
  friction 0.30σ) is unchanged.
- Code: `research/m4/xtest_primary_lead.py`.

## Result — the pattern reproduces, weaker

**Frozen rule (LOW-vol regime only, as the collector would trade), 12 y, ~118 signals/yr:**

| book | n | gross | **net** | boot CI (net) | win % (net) |
|---|---|---|---|---|---|
| 8h  | 1,416 | +0.298σ | **−0.002σ** | [−0.253, +0.244] | 45.4 % |
| 24h | 1,416 | +0.499σ | **+0.199σ** | [−0.189, +0.583] | 50.6 % |

**Regime contrast on ALL new-96-bar extremes (24h hold):**

| regime | n | net | | (XAU, for comparison) |
|---|---|---|---|---|
| LOW (gate open) | 1,429 | **+0.17σ** | | +0.45σ |
| MID | 1,652 | −0.11σ | | −0.33σ |
| HIGH | 2,183 | −0.24σ | | −0.22σ |

## Read

**Supporting, not confirming.**

- The **qualitative structure holds on a fully independent instrument**: win rate
  is ~flat across regimes (43–51 %), the edge is in payoff not hit rate, and the
  continuation is **monotone in the vol regime** — positive only when the market
  has been quiet, negative in normal/chaotic regimes.  This is the same shape as
  XAUUSD and makes a gold-only-artifact explanation less likely — there is
  probably a real mechanism (calm market → a genuine breakout carries).
- **But the magnitude is ~half** (24h net +0.20σ vs gold's +0.45σ), and silver's
  24h net **confidence interval includes zero** — silver on its own would not
  clear the addendum's PASS bar.  8h is breakeven, as on gold.

## Status

- This does **not** change the XAUUSD forward-paper test or its frozen verdicts.
  It is historical cross-sectional evidence, not an out-of-sample PASS.
- It raises prior confidence that the primitive is real, while flagging that its
  size is instrument-dependent and modest.
- `bars_15min_xag` is a standalone PG table; it does not touch any XAUUSD table
  or the frozen research splits.  No new tuning was done and none is licensed by
  this result.
