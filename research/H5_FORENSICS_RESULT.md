# H5 forensics — "reverse-engineer the winners, filter to good environments"

**Run:** 2026-09-04. The operator's idea: don't calibrate H5 down; instead study
which trades won, learn the environment they won in, and gate entries to only
those environments.

I did exactly that. Here is what happened.

---

## Step 1 — what separates H5's winning holding-periods from the losers?

143 holding-period trades, 36 % win rate, +70 % total (in-sample).

| Entry environment | trades | win % | mean ret | total |
|---|---|---|---|---|
| **vol regime < 0.8 × 1-yr median** (low vol) | 36 | 47 % | **+1.27 %** | **+53 %** |
| vol regime 0.8–1.0 × median (normal) | 59 | 34 % | −0.09 % | −6 % |
| vol regime 1.0–1.6 × median (elevated) | 38 | 26 % | 0.0 % | −3 % |
| vol regime > 1.6 × median | 9 | 33 % | +1.09 % | +9 % |

So the profit **concentrates in low-volatility entry regimes** (+53 % from 36
trades); "normal-vol" entries are a net drag. There is a plausible mechanism —
trends initiated out of a low-vol consolidation run cleaner; entries during
churn get whipsawed — and it has literature support (volatility-managed
momentum, Moreira–Muir 2017). By side: long ≈ short (no asymmetry). Efficiency
ratio: useless — a trend-flip entry has low trailing ER *by construction*.

This looks exactly like the "only trade perfect environments" filter the operator
wanted.

---

## Step 2 — turn it into a pre-committed gate and test it on held-out data

Gate: **only open a position when 20-day realised vol < its 1-year median.** Two
thresholds — 1.0× (the natural, non-arbitrary split) and 0.8× (the value the
forensics said was best).

| | Sharpe (in-sample) | maxDD (in-sample) | **Sharpe (walk-forward 2023–24)** |
|---|---|---|---|
| H5 base — no gate | 0.32 | 28.5 % | **0.65** |
| gate < 1.0× median (unfitted) | 0.35 | 26.1 % | **0.63** |
| gate < 0.8× median (fitted threshold) | **0.40** | **17.7 %** | **0.57** |

---

## The result

- The **fitted gate** (< 0.8×, chosen because the forensics showed that bucket
  won) improves the in-sample numbers a lot — Sharpe 0.32 → 0.40, drawdown
  28 % → **18 %**, which would *pass* the drawdown check.
- **On the walk-forward window it was never fitted to, the same gate makes things
  worse** — Sharpe 0.65 → 0.57. The in-sample gain was **fitting, not signal**.
- The **unfitted** threshold (< 1.0× median) does essentially nothing in either
  window — so there is no real vol-regime edge; the forensics only "found" one
  because it was allowed to pick the winning bucket.

This is the overfitting mechanism, demonstrated end-to-end on our own data:
inspect winners → build a filter → in-sample curve improves → **out-of-sample it
evaporates**. It is the same thing that killed H1b (adding "sensible" filters
collapsed the edge from t = 2.36 to t = 1.01).

**This is precisely why the blueprint reserves held-out data.** A filter learned
from trade outcomes — whether a hand-picked threshold or an ML model with many
features (which would overfit far worse) — cannot be trusted unless it survives
data it was never shown. This one did not.

---

## Bottom line

The "reverse-engineer the winners" approach has now been tried directly. It
produces an in-sample improvement that does not survive the walk-forward. There
is no reliable "perfect environment" filter for H5 in the vol / trend-quality /
whipsaw features examined.

Standing options unchanged: accept the negative result; test a genuinely
different premium (**carry**, cross-sectional relative value); or ship H5 as a
plain risk-managed-gold wrapper (adds no return, marginal drawdown help).
