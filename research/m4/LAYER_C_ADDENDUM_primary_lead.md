# Layer C Addendum — Primary Lead  (FROZEN 2026-09-10)

Governed by `research/CONDITIONAL_RESEARCH_PROTOCOL.md` v1.1 §5 (Layer C =
*minimal deterministic extraction*, thresholds fixed a priori, validated only on
forward-paper time).  This addendum covers **one** discovered primitive.  No
other primitive is promoted.  No parameter here may be changed without a new,
separately dated addendum.

## 0. The primitive (what Run 1 + v2 established)

- **State:** M1 (20-day realised-vol regime) = **LOW** (bottom trailing tercile).
- **Anchor:** A3 = a new 1-day (96-bar) high **or** low on the 15-min series.
- **Object:** `E[ dir · r_H | M1=LOW, A3 ]` — expected forward return in the
  breakout's direction, in σ = ATR14(15m) units, at horizon H.
- **v2 block-bootstrap result (control-differenced, in-sample 2009–2026, all 4
  blocks stable):** +0.25σ @ 4h, +0.42σ @ 8h, +0.85σ @ 24h; p_boot 3e-3 / 3e-4 /
  1e-5; Cochran p 0.58 / 0.90 / 0.43; I² = 0; LOO ok; P4 (spent OOS) +0.30 /
  +0.43 / +0.72.  4h/8h/24h survived; 30m/1h/2h did not (shift-fragile).
- **Absolute conditional expectation** (what a trade actually captures, no control
  subtraction; 3,354 events, 2000× moving-block bootstrap):

  | H | E[dir·r \| LOW,A3] | 95% boot CI | net after Scenario-R friction (0.30σ) |
  |---|---|---|---|
  | 4h (16 bars) | +0.186σ | [+0.058, +0.311] | **−0.114σ** |
  | 8h (32 bars) | +0.372σ | [+0.167, +0.565] | **+0.072σ** |
  | 24h (96 bars) | +0.723σ | [+0.356, +1.059] | **+0.423σ** |

  Contrast — ALL-regime A3: +0.07 / +0.15 / +0.31σ.  The LOW-vol conditioning
  roughly doubles the continuation.

**Scoping decision (not tuning):** the executable horizons are **8h and 24h
only.**  4h cleared gate A on the *control-differenced* metric but its *absolute*
expectation is net-negative after conservative retail friction, so it is not
carried into the paper test.  This is recorded here once and is frozen.

---

## 1. Frozen definitions (all values = Run 1 `build_events.py`, no change)

### M1 — realised-vol regime
- Daily bars = UTC-day resample of the 15-min series (`close` = last 15-min
  close of the day).
- `r_i` = daily close-to-close simple return.
- `RV20` = sample stdev (ddof = 1) of the **20 most recently completed** `r_i`,
  as of the close of day **D−1**.
- Classification = expanding trailing terciles of `RV20`, using **only** `RV20`
  values from days strictly before D; **≥ 504 prior daily observations**
  required, else the day is *unclassified → no signal*.
- **M1 = LOW** iff day D−1's `RV20` is in the **bottom third** of that trailing
  distribution.  The label is constant for all of UTC day D.

### A3 — new 1-day extreme (15-min)
- Bar `i` is a **new-high anchor** iff `high_i == max(high_{i−95 … i})`
  (rolling 96-bar max, inclusive of bar `i`).
- Bar `i` is a **new-low anchor** iff `low_i == min(low_{i−95 … i})`.
- **Cooldown:** after a new-high anchor fires, the next new-**high** anchor is
  suppressed for **16 completed 15-min bars** (4h).  Independent cooldown per
  direction.
- `dir = +1` for a new-high anchor, `dir = −1` for a new-low anchor.

### σ (normalisation) and the data floor
- `σ` = ATR14 on the 15-min series at bar `i` (14-bar Wilder-style ATR, price units).
- **σ-floor (frozen):** bars with ATR14 < **0.4199** (Run 1's bottom-1 %
  exclusion) do not generate a signal.

---

## 2. The signal (deterministic — this IS the extraction mapping)

At the **close of 15-min bar `i`** a signal fires iff **all** of:

1. `M1 == LOW` for the UTC day of bar `i` (i.e. from day D−1's `RV20`), **and**
2. `M1` is classified (≥ 504 prior daily obs), **and**
3. bar `i` is an **A3 anchor** (new 96-bar high or low), respecting the 4h
   per-direction cooldown, **and**
4. `ATR14(i) ≥ 0.4199`.

`side = dir` (long on a new-high anchor, short on a new-low anchor).

**Nothing else.**  No indicator, no confirmation candle, no session/day filter,
no minimum breakout size, no RV20 threshold beyond the tercile, no news gate.

## 3. Timestamps

- **Information timestamp:** close of anchor bar `i` (M1 from D−1 daily close;
  the 96-bar high/low includes bar `i`'s own known high/low; ATR14 through `i`).
- **Decision / entry timestamp:** **open of bar `i+1`** (the next 15-min bar).
  The ≤ 1-bar gap between `close_i` (the measured reference) and `open_{i+1}`
  (the executed price) is absorbed into the friction scenario.

## 4. Holding horizons & exits

- Two parallel books: **H = 32 bars (8h)** and **H = 96 bars (24h)** after the
  anchor bar close.
- **Exit** = close of bar `i + H` (or the last available bar if the series ends
  first).  **No stop, no target, no trail.**  The validated object is a
  fixed-horizon mean; a stop/target changes the estimand and is explicitly a
  *future* iteration, not part of this validation.
- Position risk is bounded by size (§5), not by a stop.
- One position per signal per book.  Overlapping positions are allowed (a new
  signal while an older one is still open opens a second position).

## 5. Position sizing

- **Fixed 0.01 lot per signal per book.**  No vol scaling, no equity scaling, no
  Kelly.  A sizing map is a *future* iteration.
- Outcome is recorded and evaluated in **σ units** (`dir · (exit − entry) / σ`),
  so the fixed lot does not affect the statistical verdict; it only fixes the
  operational footprint.

## 6. Friction

- **Scenario R (conservative retail), frozen at 0.30σ round-trip.**  Deduct a
  flat **0.30σ** from every paper trade's gross `dir · r_H` to get net.
- Basis: 0.01-lot XAUUSD spread ≈ $0.34 + commission $6/lot + ~1-tick slip ≈
  $0.44, vs ATR14 ≈ $1.2–1.4.  This is a reference point, not a live-account claim.

## 7. No parameter tuning

Frozen at Run 1 values, all of them: RV20 window **20**, tercile cut **1/3**,
M1 warm-up **504 days**, A3 lookback **96**, A3 cooldown **16**, horizons
**{32, 96}**, σ-floor **0.4199**, friction **0.30σ**, size **0.01 lot**.
Changing any one requires a new dated addendum and re-starts the forward count.

## 8. Forward-paper procedure

- **Start date F** = the first UTC day *after* this file is committed.  Only
  bars dated ≥ F count — every earlier bar has been touched.
- Feed: live/near-live 15-min XAUUSD bars (`monitor` / `livebot` MT5 feed, or a
  daily batch from Postgres once it is topped up — either, provided the bars are
  dated ≥ F).  **Paper only.  No live orders.  Ever.**
- `research/m4/primary_lead_signal.py` is the frozen generator.  Each fired
  signal appends one row per book to `research/m4/paper_primary_lead.csv`:
  `anchor_ts, side, rv20_pctile, atr14, entry_px, book, exit_ts, exit_px,
  gross_sigma, net_sigma`.
- Report monthly: rolling mean `net_sigma` per book + its moving-block bootstrap
  95% CI, and the realised event rate.  **Do not act on interim readings.**
- **Minimum evaluation sample: 150 signals per book** (≈ 10 months at ~190/yr)
  before any verdict.

## 9. Pre-registered verdicts (decided now, before any forward data)

Per book (8h, 24h), once **n ≥ 150**:

| verdict | condition |
|---|---|
| **PASS** | forward mean `net_sigma` ≥ **+0.05σ** AND its 95 % bootstrap CI lower bound > 0 AND no single calendar quarter contributes > 60 % of cumulative net P&L |
| **FAIL** (retire the book) | forward mean `net_sigma` ≤ 0 AND its 95 % CI upper bound < **+0.10σ** |
| **INCONCLUSIVE** | positive but CI includes 0, or n < 150 — keep collecting, do not deploy, do not discard |

Additional retire trigger (either book): realised signal rate < **95/yr** or
> **285/yr** (i.e. < 50 % or > 150 % of the ~190/yr historical rate) for **two
consecutive quarters** — treated as regime / definition drift.

A **PASS earns only** "continue paper trading; a position-sizing study may now be
pre-registered."  It does **not** authorise live trading — live is out of scope
for this project.

## 10. Pre-registered expectation (operative — from the FROZEN generator)

`primary_lead_signal.py --reference` on the full already-touched history
(2009–2026, entry = open of bar i+1, exit = close of bar i+H, friction 0.30σ):

| book | n | gross E[dir·r] | **net** | 95 % iid-boot CI on net | win % (net > 0) |
|---|---|---|---|---|---|
| 8h  | 3,372 | +0.374σ | **+0.074σ** | **[−0.099, +0.249]** | 45.6 % |
| 24h | 3,372 | +0.748σ | **+0.448σ** | **[+0.151, +0.740]** | 50.2 % |
| signal rate | ~191 / yr | (addendum expects ~190; retire band 95–285) | | | |

(The §0 discovery-stage table used close[i] → close[i+H]; this table uses the
executable open[i+1] → close[i+H] and is the operative pre-registration.)

**Note, stated now:** the **8h book's historical net CI already straddles 0**
([−0.10, +0.25]) — it enters the forward test as the *weaker* book and is likely
to land INCONCLUSIVE.  **24h is the real candidate** (historical net +0.45σ, CI
excludes 0).  Both books are still run forward exactly as specified; this note
just records the a-priori expectation so a marginal 8h result is not
over-interpreted either way.

If a forward book's mean lands materially below its CI lower bound above, that is
a FAIL for that book even if the point estimate is still > 0.

---

## 11. Operational setup (2026-09-10)

- **Data currency:** `data_pipeline/topup_bars_pg.py` — fetches XAU/USD 15-min
  BID+ASK from Dukascopy since the last stored `bars_15min` timestamp (2-day
  overlap), DELETE-then-INSERTs that window (table has no unique key), marks rows
  `source = 2`, and refuses to write on an empty / non-newer / suspiciously-small
  fetch.  Ran once 2026-09-10 → `bars_15min` current to 2026-09-10.
- **Loader change (not a spec change):** `primary_lead_signal.py` now loads the
  full `bars_15min` via `load_bars("15min", split=None)` instead of the three
  frozen research splits (which cap at 2026-09-04).  The signal *logic* and every
  frozen constant are unchanged; this only lets the forward phase see bars after
  the research cap.
- **Schedule:** Windows Task `M4 primary-lead collector`, daily **00:20 UTC**
  (05:50 Asia/Kolkata), "run only when logged on".  Runs
  `research/m4/run_collector.cmd` → top-up, then
  `python -m research.m4.primary_lead_signal --since 2026-09-11`.  Output →
  `research/m4/paper_run.log`; resolved trades → `research/m4/paper_primary_lead.csv`.
- **State at setup:** 0 signals so far.  Gold's 20-day realised-vol regime is at
  the ~95th percentile (HIGH); the last historical signal fired 2025-12-29.  The
  rule is regime-gated and will stay idle until RV20 falls back into the bottom
  tercile.  The lumpy event rate is expected — evaluate the §9 rate-drift guard
  with that in mind.

---

## 12. Held-out data is EXHAUSTED — forward paper is the ONLY remaining test

There is **no clean walk-forward or out-of-sample window left** for this
hypothesis (or any other).  See `research/HELD_OUT_DATA_POLICY.md` for the
project-wide rule; the specifics for this lead:

- `walk_forward` (2023-01 → 2024-07) and `out_of_sample` (2024-07 → 2026-09) were
  **both consumed before M4** (H7 carry, H2 continuation — the touch-once guard
  overridden with `allow_oos=True` each time).
- **M4 Run 1 + v2 analysed the full 2009–2026 series as one dataset**, with those
  two windows as descriptive blocks **P3** and **P4**.  Every block — including
  P4 — was *inspected during discovery*.  The "stable across all four blocks /
  survives the block bootstrap" claim, and the per-block figures (P3 +1.42σ,
  P4 +0.72σ at 24h), are therefore **in-sample-flavoured, not independent
  confirmation**.
- **Consequence:** the primary lead has passed *in-sample statistical validation
  only*.  Its per-block persistence into 2023–26 is encouraging but does not
  count as a held-out test, because P3/P4 were part of the selection.
- The single genuinely untouched dataset is **forward time from F = 2026-09-11
  onward** — data whose timestamps post-date the freezing + commit of this
  addendum.  That is why this is a forward-paper collector, not a backtest.  The
  §9 verdicts are evaluated on that forward data alone.
