# M4 Run 1 — fingerprint-grid ledger  (2026-09-10)

Protocol: `research/CONDITIONAL_RESEARCH_PROTOCOL.md` v1.1 (frozen).
Code: `research/m4/build_events.py` → `events.parquet` → `research/m4/run1.py` →
`research/m4/ledger.csv`.  Instrument: XAUUSD 15-min, 2009-01 → 2026-09.

**This is a map, not a strategy.** Per §7 the grid was computed in full and the
single FDR correction applied before any cell was read.

## Method notes (run-1 choices, all inside the frozen protocol)

- σ = ATR14(15m) at the anchor bar for all normalisation (daily-RV alternative deferred).
- Data hygiene: dropped anchor events with ATR14 in the bottom 1% (near-zero-range
  degeneracy — same artifact flagged all through M3); winsorised forward return /
  excursion at ±20σ.
- Standard errors: **analytic** (delta-method for means / dispersion / skew / kurt;
  normal-approx for quantiles), each widened by the autocorrelation inflation
  factor √(1+2Σρ_k) capped at 10.  Full moving-block bootstrap = a v2 upgrade.
- Matched control (§2G): same anchor, same block, same session; **not** in the
  cell's bucket.  Day-of-week and month-of-year are the two OPTIONAL dims and were
  RELAXED for run 1 (noted here as required).
- Event-state (E1–E3) look-ahead shift test is a no-op (calendar is exogenous) —
  those cells have `shift_delta = 0` by construction; treat their shift result as
  "not tested" rather than "passed".

## Grid result

| step | count |
|---|---|
| cells with finite p | **12,782** |
| FDR-significant (Benjamini–Hochberg, q = 0.10, over the whole grid) | 1,689 |
| …also block-stable (Cochran Q p > 0.10, I² < 0.50, leave-one-block-out) | 619 |
| …also look-ahead-shift-robust  ⇒  **A = YES** | **305** |

`A = YES` cells, by state class / anchor / horizon:

| class | A=YES | | anchor | A=YES | | horizon | A=YES |
|---|---|---|---|---|---|---|---|
| MARKET (M1–M5) | 142 | | A1 reference | 158 | | 30m | 49 |
| EVENT (E1–E3) | 116 | | A2 σ-displacement | 22 | | 1h | 41 |
| TEMPORAL (T2) | 47 | | A3 new 1-day extreme | 47 | | 2h | 43 |
| TEMPORAL (T1) | **0** | | A4 session open | 42 | | 4h | 51 |
| | | | A5 release / A6 impulse-res | 0 | | 8h | 59 |
| | | | | | | 24h | 62 |

## What Run 1 establishes

**1. The new research unit works.** ~2.4 % of the frozen grid clears all three
gates — well above FDR noise, stable across P1 2009-15 / P2 2016-22 /
P3 2023-24 / P4 2024-26, and robust to a 1-step data shift (for the states where
that test is meaningful).

**2. The structure is almost entirely in the *shape* of the forward
distribution, not its *centre*.**  Of 305 A=YES cells, **291 are non-directional**
— dispersion ratios, tail probabilities, realised-vol-path, the *timing* of the
largest excursion (`E_t_mfe` / `E_t_mae`), and quantile fans.  The directional
metrics (`location`, `location_dir`, `race_*`) clear gate A only **14 times**.

- **Event proximity (E1 FOMC / E2 NFP / E3 CPI)** robustly compresses forward
  dispersion in the 4–24 h *before* a release and widens it — fatter both tails,
  later time-to-peak-excursion — in the 0–4 h *after*.  Stable in all four blocks.
  Non-directional.  Economic verdict: MATTERS-AT-L-ONLY / NON-DIRECTIONAL — a real
  primitive for sizing / event-avoidance / a volatility instrument, not a retail
  directional trade.
- **Market-vol regime (M1), distance-from-200d (M4)** widen the multi-hour
  forward distribution and fatten its tails when vol is high or price is
  stretched.  Stable, non-directional.
- **T2 (failed-attempt count)**: when there have been no recent failed pushes
  through a nearby level, price is ~12 pp more likely to revisit the session
  open within a few hours; when there have been failed attempts, less likely.
  Stable, non-directional, MATTERS-AT-L-ONLY.

**3. One directional primitive clears conservative retail friction (Scenario R,
≈0.30σ):**

> **A new 1-day price extreme (anchor A3) that occurs while the 20-day realised-
> vol regime is LOW (M1 bucket 0) shows stable forward *continuation* in the
> extreme's direction:**
> +0.25σ @ 4 h → **+0.42σ @ 8 h** → **+0.85σ @ 24 h**
> (block estimates at 24 h: P1 +0.44 / P2 +1.03 / P3 +1.42 / P4 +0.72;
> Cochran p = 0.68, I² = 0, shift Δ = 0.11; n = 3,354, ≈190 events/yr).

A handful of weaker relatives point the same way — trend-persistence regime
= MEAN-REVERTING (M3) at a new extreme, H 32 (+0.38σ, R); price FAR-ABOVE the
200-day mean (M4 Q5) at a new extreme, H 32 (+0.48σ, R, but P4 weak); dollar-FLAT
(M5) at a σ-displacement, H 32 (+0.38σ, R, but P4 ≈ 0).  All at the **new-extreme
/ displacement anchors around the 8-hour horizon**, all "quiet / stretched market
breaks a level → it runs."

This is invisible to every barrier-based strategy test in M1–M3 because none
conditioned on the *daily* volatility or displacement regime.

**4. T1 (unresolved-duration after an impulse) cleared nothing.**  151 of its
429 cells were FDR-significant but not one survived block-stability + shift.  The
"slow confirmation" lead from the continuation study is now also negative as a
distributional primitive.

## Run 1 inference — v2 block-bootstrap replication (DONE, `run1_v2boot.py`)

Run 1 used analytic SEs (delta-method + normal-approx quantiles × ACF inflation);
protocol §4.1 specifies a block bootstrap.  **v2 re-did the inference for the 305
A=YES cells with a moving-block bootstrap** (B = 400, block ≥ H bars,
block×session-stratified; strata > 1400 events systematically thinned for the
resample — the primary lead has ≈210/stratum so it is un-thinned).  Full result:
`research/m4/RUN1_V2_SUMMARY.md`, `ledger_v2.csv`.

| gate | Run 1 (analytic) | v2 (block bootstrap) |
|---|---|---|
| FDR-significant | 1,689 | 1,613 |
| + block-stable | 619 | 522 |
| + shift-robust ⇒ A=YES | **305** | **215** |

**215 of 305 survive** (70 %); 90 drop; 0 newly qualify (validation only).
Surviving A=YES: **204 non-directional, 11 directional.**  The dominant finding —
market/event states reshape the *shape* of the forward distribution, essentially
never its centre — is unchanged under the stricter inference.

## Frozen research state (2026-09-10)

| primitive | status |
|---|---|
| **T1 unresolved-duration** | **RETIRED** (0 stable primitives; slow-confirmation lead closed) |
| Event proximity (E1/E2/E3) → distribution shape | **VALIDATED NON-DIRECTIONAL** (provisional inference) |
| M1 vol regime → distribution shape | **VALIDATED NON-DIRECTIONAL** (provisional) |
| M4 distance-from-200d → distribution shape | **VALIDATED NON-DIRECTIONAL** (provisional) |
| T2 failed-attempt count → path / reversion probability | **VALIDATED NON-DIRECTIONAL** (provisional) |
| **M1 LOW-vol regime + new 1-day extreme (A3) → forward continuation** | **PRIMARY LEAD — BLOCK-BOOTSTRAP VALIDATED in-sample.** Survives v2 at H = 4h / 8h / 24h (p_boot 3e-3 / 3e-4 / 1e-5); effect +0.25σ → +0.42σ → +0.85σ, monotone; Cochran p 0.58 / 0.90 / 0.43, I² = 0, LOO ok; per-block incl. the spent OOS window P4 = +0.30 / +0.43 / +0.72. H = 30m/1h/2h do **not** survive (shift-fragile). ~190 events/yr. **Forward-paper validation is the only test left.** |
| the other ~7 directional A=YES survivors (m3/m4/m5 at new-extreme / σ-displacement, H≈32) | **SECONDARY — DO NOT PROMOTE.** Pass the gates but the P4 (spent-OOS) block is weak or sign-flipped in most; no post-hoc ranking. |
| interactions (state × state) | **PROHIBITED** |
| Layer C (extraction / strategy) | **DEFERRED** |

## Stage progress

- **Step 1 — v2 block-bootstrap replication: DONE.**  215/305 A=YES survive; the
  primary lead survives at H = 4h / 8h / 24h (control-differenced).  See above.
- **Step 2 — frozen Layer-C addendum: DONE.**
  `research/m4/LAYER_C_ADDENDUM_primary_lead.md` (2026-09-10) +
  `research/m4/primary_lead_signal.py` (frozen deterministic generator).
  Executable horizons scoped to **8h and 24h** (4h's *absolute* net is −0.11σ
  after 0.30σ friction — passed gate A on the control-differenced metric but not
  as a trade).  Operative pre-registration (frozen generator, full history):
  8h net **+0.074σ** CI [−0.10, +0.25] (weak — likely INCONCLUSIVE forward);
  24h net **+0.448σ** CI [+0.15, +0.74] (the real candidate).  Fixed 0.01 lot,
  no stop, fixed-horizon exit, no tuning.  Verdicts (PASS / FAIL / INCONCLUSIVE)
  pre-registered; min 150 signals/book.
- **Step 3 — forward paper: PENDING.**  Run
  `python -m research.m4.primary_lead_signal --since <F>` from the addendum start
  date onward; it appends to `research/m4/paper_primary_lead.csv` and prints the
  running verdict.  This is the only out-of-sample test left.

Engine architecture this run establishes:
`market state → conditional-distribution fingerprint → is the information
directional / volatility / tail / timing / path? → only then consider extraction.`
