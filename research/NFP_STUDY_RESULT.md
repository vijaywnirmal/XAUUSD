# How XAUUSD behaves around NFP — descriptive study

**Run:** 2026-09-04. `research/nfp_study.py`. 5-min canonical bars, true UTC,
**210 NFP releases, 2009-02 → 2026-08.** NFP = first Friday of the month, 08:30 ET
= **12:30 UTC in US summer / 13:30 UTC in US winter** (handled per date).
Descriptive — *not* a strategy backtest. Full history used (behaviour, not
strategy selection).

---

## 1. The release spike — NFP roughly DOUBLES gold's short-term move

| Window after release | NFP median | NFP p90 | normal Friday median |
|---|---|---|---|
| 0–5 min (in ATR units) | **0.25** | 0.72 | 0.08 |
| 0–15 min | 0.27 | 0.83 | 0.09 |
| 0–30 min | 0.25 | 0.93 | 0.12 |
| **0–30 min in bps** | **\|30\|** | \|108\| | \|15\| |
| worst single release | | \|225\| bps | |

- The reaction is **near-instant** — the 5-minute move is essentially the whole
  30-minute move (0.25 ATR at both).
- Typical NFP: ~30 bps in 30 min (≈ $13 on gold near $4,300). Fat tail: 1 in 10
  is 100+ bps; the biggest was 225 bps.
- **Stable across eras** (0.22–0.26 ATR in 2009–14, 2015–21, 2022–26) — NFP has
  not lost its punch.

## 2. Direction is a coin flip

Distribution of the **signed** 0–30 min move on NFP days:

| p5 | p10 | p25 | **p50** | p75 | p90 | p95 |
|---|---|---|---|---|---|---|
| −117 | −79 | −29 | **+1 bps** | +30 | +77 | +95 |

Median +1 bps, roughly symmetric (slight negative skew). **You cannot predict
which way the spike goes.**

## 3. No tradeable pre-NFP drift

| | mean | median | t vs 0 |
|---|---|---|---|
| NFP days, 08:00 UTC → release | −3.5 bps | −2.6 | −1.45 |
| other Fridays | −0.4 bps | +1.9 | −0.23 |

A weak tendency for gold to soften slightly into the print — **not significant**
(t = −1.45), smaller than trading cost, and it has decayed: −11 bps/print in
2009–14 → ~0 in 2015–21 → **+2.7 bps (flipped positive) in 2022–26.**

## 4. Mild continuation after the spike (not reversal)

Move from the +30 min mark, **signed in the direction of the initial spike**:

| Window | mean | median | t vs 0 | % positive |
|---|---|---|---|---|
| +30 → +120 min | +2.9 bps | +2.6 | +1.03 | 55 % |
| +30 → +210 min | +4.1 bps | +7.6 | +1.02 | 55 % |
| +30 → session end (+390 min) | +10.9 bps | +4.2 | **+2.24** | 54 % |

The knee-jerk tends to **keep running**, not reverse — the run-to-session-end is
marginally significant (t = 2.24). But +11 bps mean at a 54 % hit rate, entered
*after* the spike, is **too thin to trade after cost** (~15–30 bps round trip).

## 5. Slight positive session bias, not significant

| NFP session (13:00 → 20:00 UTC) | mean | median | t | std |
|---|---|---|---|---|
| NFP days | +5.5 bps | **+16.9** | +1.03 | 76 |
| all days | −0.4 bps | +0.7 | −0.36 |

Gold *usually* drifts up on NFP days (median +17 bps), but the mean is dragged
down by fat left-tail days — **not statistically significant** (t = 1.03).

## 6. Spread blow-out is modest (on this data)

| | median | p90 | max |
|---|---|---|---|
| NFP release (× pre-release spread) | **1.2×** | 1.4× | 2.8× |
| other Fridays | 1.0× | | |

On the Dukascopy (interbank-style) feed the spread only widens ~20–40 % at the
release. **A retail broker will typically be worse** (2–5×, plus requotes and
stop slippage) — verify on your own account before assuming the spike is
accessible.

---

## Bottom line

**NFP is a volatility event, not a directional edge.** It reliably makes gold
move about **2× more for the first 30 minutes** (median ~30 bps, fat tail to
100–225 bps), the reaction is essentially instant, and it has not faded over 17
years. But:

- **Which way it goes is unpredictable** (median signed move +1 bps).
- The pre-drift (−3 bps), post-spike momentum (+11 bps to session end), and
  session bias (+17 bps median) are all **below statistical significance and
  below trading cost**.

If you could trade *volatility* directly (buy a straddle before NFP, close after),
the ~2× expansion is real and stable — but there is no gold-options product on a
retail CFD account, and a synthetic two-sided breakout straddle around NFP would
need the post-release move to clear the straddle width **plus** costs, and the
median 30-min move (~30 bps) sits right on that break-even line. It is the H3
straddle idea concentrated onto NFP days — borderline, and given every other
result in this project, most likely ≈ break-even.

Per-release detail: `research/nfp_days.csv`.
