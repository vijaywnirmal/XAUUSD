# Conditional-Distribution Research Protocol  —  FROZEN 2026-09-10

Status: **frozen v1**. Supersedes the strategy-by-strategy method used in M1–M3.
Change log at the bottom; do not edit the body without a dated entry there.

M3 conclusion stands (no directional systematic edge on XAUUSD survived OOS at
retail cost, held-out window spent twice — see `M3_CONCLUSION.md`,
`memory/research-log.md`). This protocol is the **next phase (M4)**: we stop
asking "what strategy works?" and first build an empirical map of *which
observable states change the distribution of future market behaviour*.

---

## 0. The reframe

- **Old unit:** a setup → a 2R barrier → win/loss → expectancy → t-test vs a null.
- **New unit:** a `(state, anchor, horizon)` triple. For an observable state **S**
  knowable strictly before time *t*, at anchor timestamps within S, over forward
  horizon **H**, characterise the *entire* conditional forward-path distribution
  and compare it to a **calendar-matched control** (same period, not in S).
- The output of a study is a **distribution fingerprint**, not a number.
  Direction is one moment of that distribution and is often not the interesting one.
- The protocol does **not** assume an edge exists. A valid outcome is
  "no pre-registered state measurably alters the forward distribution."

Three conclusions are kept explicitly separate:

| Gate | Question | First-run scope |
|---|---|---|
| **A — Predictive** | Does S change the conditional distribution vs matched control? | **run** |
| **B — Economic** | Is the change large enough to matter under documented friction scenarios? | **run (for cells that pass A)** |
| **C — Tradable** | Can a minimal fixed decision capture it without destroying it? | **DEFERRED** — not run for the first several rounds |

---

## 1. Data

- XAUUSD 15-min bars, Postgres `bars_15min`, 2009-01 → 2026-09 (`ts, open, high,
  low, close, tick_count, spread_mean, volume_sum`). Daily via resample.
- Daily macro: `macro/gold_drivers.csv` (DFII10 10y real yield, DTWEXBGS broad
  USD; FRED, ~1 business-day publication lag — use values dated ≤ D−2).
- Event calendar: `monitor/calendar_history.py` (hardcoded FOMC 2009–2027 +
  first-Friday NFP + ~13th CPI, DST-adjusted).
- Cross-instrument parallel track: `basket/` 14-instrument daily bars (from H6).
- Cross-asset intraday (EURUSD/USDJPY M5, 2016–2026 only): `monitor/data/*_m5.parquet`
  — limited history, use only where a state explicitly allows a 2016-start.

**Time blocks** (fixed, disjoint):
`P1` 2009-01…2015-12 · `P2` 2016-01…2022-12 · `P3` 2023-01…2024-06 ·
`P4` 2024-07…2026-08. (P3 = the old `walk_forward`, P4 = the old `out_of_sample` —
**both are SPENT**, see `research/HELD_OUT_DATA_POLICY.md`. Used here only as
descriptive per-period blocks; a cell passing "stable across P1–P4" is
in-sample-flavoured, **not** independently confirmed. No pass/fail may rest on
P3 or P4. The only remaining out-of-sample test for any hypothesis is
forward-paper time.)

---

## 2. Layer 0 — State taxonomy (FROZEN — 10 states)

Every state variable is (i) leak-free, with an explicit **information timestamp**
(the last completed observation allowed); (ii) has a written mechanism; (iii) has
a **fully deterministic** definition — no free `N`, `M`, "if available", "near",
or thresholds to be chosen later; (iv) is on this frozen list. States are grouped
into three classes. Run 1 treats each state **in isolation** (no interactions,
§2F).

**Bucketing rule (applies to every state that uses quantiles):** cut points are
computed from an **expanding trailing window of the state variable's own prior
values only** — never the full study sample, never forward data. Each state
names its minimum warm-up; observations before it are *unclassified and excluded*.

---

### 2A. MARKET states  (daily resolution)

**Information timestamp:** computed from daily bars whose close is ≤ 00:00 UTC of
day D (the last fully completed UTC day). FRED series (M5) use the observation
dated ≤ D−2 calendar days (publication lag). The state is **constant for every
intraday anchor during UTC day D**.

**M1 — Realized-vol regime.**
- Input `RV20` = sample standard deviation of the last **20 completed** daily
  close-to-close simple returns `r_i = close_i/close_{i−1} − 1`, as of day D−1.
  Not annualised (scale is irrelevant for bucketing). **Not ATR.**
- Warm-up: 504 trading days.
- Buckets: **trailing terciles** of `RV20` → `LOW / MID / HIGH`.
- Mechanism: volatility clusters; forward-return dispersion and tail mass may
  differ by the volatility regime in force at entry.

**M2 — Volatility term structure.**
- Input `TS = log( RV5 / RV20 )`, `RV5` / `RV20` = sample std of the last 5 / 20
  completed daily close-to-close returns as of D−1.
- Warm-up: 504 trading days.
- Buckets: **trailing terciles** of `TS` → `SHORT_BELOW / NEUTRAL / SHORT_ELEVATED`.
- Mechanism: the relative level of short- vs long-horizon volatility *may* carry
  information about subsequent volatility persistence or normalisation. (Does
  **not** assume mean reversion is true.)

**M3 — Trend-persistence.**
- Input `AC1` = lag-1 Pearson correlation of the sign series `x_i = sign(r_i)`
  (values in {−1, 0, +1}) over the **40 most recently completed** daily returns
  as of D−1: with `x_1..x_40` those signs in order, `AC1 = corr(x_1..x_39,
  x_2..x_40)`. Zero-return days kept as `x_i = 0`. If the correlation is
  undefined (all signs equal), `AC1 = 0`.
- Warm-up: 504 trading days.
- Buckets: **trailing terciles** of `AC1` → `MEAN_REVERTING / RANDOM / TRENDING`.
- Mechanism: some regimes are momentum-like, others choppy; the same intraday
  anchor may resolve differently in each.

**M4 — Long-term displacement.**
- Input `DZ = ( close_{D−1} − SMA200_{D−1} ) / sigma20_price`, where
  `SMA200` = mean of the last 200 completed daily closes as of D−1, and
  `sigma20_price = stdev(last 20 completed daily close-to-close simple returns)
  × close_{D−1}` (20-day realised daily-return volatility in price units).
- Warm-up: 504 trading days.
- Buckets: **trailing quintiles** of the signed `DZ` distribution →
  `Q1 (most below) … Q5 (most above)`. Quintiles (not terciles) because this
  state is specifically about the tails.
- Mechanism: markets stretched far from a long-term anchor may carry asymmetric
  forward skew / tail risk.

**M5 — Cross-asset dollar stress  (XAUUSD-specific in Run 1).**
- Input `USD5` = trailing 5-business-day % change in the FRED broad
  trade-weighted USD index (DTWEXBGS, `macro/gold_drivers.csv`), using the most
  recent observation dated ≤ D−2 calendar days:
  `USD5 = DTWEXBGS_{≤D−2} / DTWEXBGS_{≤D−2, −5 bd} − 1`.
- Warm-up: 504 trading days.
- Buckets: **trailing terciles** of `USD5` →
  `USD_WEAKENING / USD_FLAT / USD_STRENGTHENING`.
- Mechanism: the broad dollar is gold's most robust contemporaneous driver (H8);
  a *recent* dollar move may predict a forward *distribution* shift even without
  a directional edge.
- **Scope:** M5's driver is chosen for XAUUSD specifically. Run 1 applies M5 to
  **XAUUSD only**. Extending M5 to the `basket/` requires a separate frozen
  mapping of one pre-registered external driver per instrument, defined before
  the basket run and never selected from results.

---

### 2B. TEMPORAL states  (15-min resolution)

**Information timestamp:** computed from 15-min bars completed at or before *t−1*;
the state is known at the open of anchor bar *t*.

**T1 — Unresolved duration after an impulse.**
- Impulse timeframe: non-overlapping 1-hour bars from the 15-min series (four
  15-min bars each; a 1h bar closes on the hour, UTC).
- Impulse σ: `sigma_1h` = sample std of the last **480 completed** non-overlapping
  1h close-to-close simple returns, as of the 1h bar's close.
- Impulse condition: a completed 1h bar `B` is an impulse iff
  `|close_B − open_B| / (sigma_1h × open_B) ≥ 2.0`. **Single threshold 2.0; no
  grid.** `dir = sign(close_B − open_B)`; leg `L = |close_B − open_B|` (price);
  origin `O = open_B`; extreme `X = close_B`.
- Resolution, checked on each later completed 15-min bar `k` (`dir=+1` shown;
  mirror for `dir=−1`):
  - **retraced** iff `close_k ≤ X − 0.5·L`
  - **extended** iff `close_k ≥ X + 0.5·L`
  - both on the same bar → classified **retraced** (conservative).
- Superseding impulse: a new impulse 1h bar while the current window is
  unresolved closes the current window as **superseded** at that 1h close and
  starts a fresh window. Superseded windows keep a duration value and are kept.
- Timeout: no resolution within **96 completed 15-min bars** (24h) → window
  closes **timed-out** at bar 96.
- `duration` = completed 15-min bars from the impulse 1h close to the
  resolution / supersession / timeout bar (integer 1…96).
- Anchor: the resolution / supersession / timeout bar (**A6**). The state value
  `duration` is known at that bar.
- Warm-up: 200 prior T1 events.
- Buckets: **trailing terciles** of the `duration` distribution →
  `FAST / MEDIUM / SLOW`.
- Mechanism: a long post-impulse stalemate suggests information not yet priced →
  a larger eventual move (magnitude, not necessarily direction). The reframed
  "slow confirmation" clue from the continuation study.

**T2 — Failed extreme-resolution count.**
- Level definition: the most recent **confirmed 1-day (96-bar) extreme**. A
  15-min bar `j` confirms an **upper** level `U = high_j` iff
  `high_j = max(high over bars j−95 … j)` **and** ≥ 3 completed bars have elapsed
  since `j`. Mirror for a **lower** level `Dn = low_j`. The *active* upper (lower)
  level at bar *t* is the most recent confirmed `U` (`Dn`) whose confirmation bar
  is within the last **192 completed bars** (48h). If no active level of a given
  side exists, that side contributes 0.
- Attempt (upper): a completed 15-min bar `b` in the window with `high_b > U`.
  **Failure:** that same bar also has `close_b ≤ U`. Mirror for lower.
- Window: the last **48 completed 15-min bars** (12h) ending at *t−1*.
- `fails` = failed upper attempts + failed lower attempts in the window.
- Buckets: **`0 / 1 / 2+`** (fixed; no grid). If neither an active upper nor an
  active lower level exists in the window, T2 is undefined at *t* → that anchor
  is skipped (not a bucket).
- Mechanism: repeated failed pushes through an established level = liquidity
  probing; the forward distribution afterwards may differ.

---

### 2C. EVENT states  (calendar — three separate states)

Release timestamps: DST-adjusted scheduled times from `monitor/calendar_history.py`
(FOMC statement 18:00/19:00 UTC; NFP 12:30/13:30 UTC; CPI 12:30/13:30 UTC). Each
event state is defined **relative to its own event type only**.

For anchor bar *t*, let `Δ` = signed hours from *t*'s open to the nearest release
of that event type (`Δ<0` before, `Δ≥0` after). Buckets, identical for all three:

| bucket | range |
|---|---|
| `PRE_24_4` | −24 ≤ Δ < −4 |
| `PRE_4_0` | −4 ≤ Δ < 0 |
| `POST_0_4` | 0 ≤ Δ < 4 |
| *(absent)* | Δ < −24 or Δ ≥ 4 — **not a bucket**; forms part of the control pool |

- **E1 — FOMC proximity.** Mechanism: pre-FOMC positioning compresses dispersion;
  the statement reprices.
- **E2 — NFP proximity.** Mechanism: NFP is a large scheduled volatility event
  (~2× gold's 30-min move, NFP_STUDY); pre/post distribution differs.
- **E3 — CPI proximity.** Mechanism: CPI became a primary gold macro driver
  post-2021; scheduled repricing.

Kept as three states (not one "event proximity") because the event dynamics are
not interchangeable.

---

### 2D. ANCHORS  (timestamps to measure forward from — NOT entries)

Condition-at-*t* only; **no forward filtering**. Every anchor has a frozen
cooldown to stop clustered firings being counted as independent experiments.

| id | exact definition | cooldown |
|---|---|---|
| **A1 reference** | every completed 15-min bar whose 0-based index in the full series has `idx mod 4 == 0` | none (deterministic subsample) |
| **A2 σ-displacement** | the completing 15-min bar of a non-overlapping 1h bar `B` with `|close_B − open_B| / (sigma_1h × open_B) ≥ 2.0` (`sigma_1h` = std of last 480 completed 1h returns). **Single threshold.** | after A2 fires, suppress the next A2 for **16 completed 15-min bars** (4h) |
| **A3 new 1-day extreme** | a completed 15-min bar with `high = max(high, last 96 completed bars)` (upper) or `low = min(low, last 96 completed bars)` (lower). **Single N = 96.** | suppress the next **same-direction** A3 for **16 completed 15-min bars** |
| **A4 session open** | the first completed 15-min bar at each UTC boundary 00:00 / 07:00 / 12:00 / 17:00 | none (one per session by construction) |
| **A5 scheduled release** | the 15-min bar whose `[open, close)` interval contains a DST-adjusted FOMC / NFP / CPI release time | none (≤ ~monthly per type) |
| **A6 impulse resolution** | the resolution / supersession / timeout bar of a T1 window | inherits A2's 4h suppression via the parent impulse |

### 2E. Frozen pairing grid

A study is one `(state-bucket, anchor, horizon, metric)` cell.

| state | anchors |
|---|---|
| M1, M2, M3, M4 | A1, A2, A3, A4, A5 |
| M5 (XAUUSD only) | A1, A2, A3, A4, A5 |
| T1 | A6 (intrinsic) |
| T2 | A1, A3 |
| E1, E2, E3 | A1, A4 |

× all 6 horizons (§3) × all fingerprint metrics (§3).

### 2F. Interactions — PROHIBITED in run 1

No `market × temporal`, `state × state`, or any 2-D slice discovered by
inspection. Interactions are a **separate later round**, each pre-registered with
a stated mechanism, and each must beat **both** marginals on the
incremental-information test *before* the claim is made. (The exact H2 failure
mode; enforce aggressively.)

### 2G. Control hierarchy  (mandatory — see also §4.4)

For a state-S observation at anchor bar *t*, the matched-control pool is every
observation of the **same anchor type** **not** in the same bucket of state S,
filtered to match *t* on the dimensions below. **[M]** = mandatory; if the
mandatory match leaves < 30 controls, relax optional dimensions **last-listed
first**, and record the relaxation in the ledger row.

1. same instrument **[M]**
2. same study block P1–P4 **[M]**
3. same anchor type **[M]**
4. same UTC session bucket (ASIA / LONDON / NY_AM / NY_PM); for A5, same event type **[M]**
5. same day-of-week (Mon–Fri) — optional
6. same calendar month-of-year (Jan–Dec) — optional

Effect = `stat(S) − stat(control)`, computed within each block then combined.
This stops a "state effect" from silently being a session / weekday / seasonal
effect.

---

## 3. Layer 1 — The distribution fingerprint

**Forward horizons:** `H ∈ {2, 4, 8, 16, 32, 96}` × 15m = 30m / 1h / 2h / 4h / 8h / 24h.

**Normalisation:** forward returns and excursions in σ units, σ = `ATR14` at *t*
(price units) unless the state is daily-defined, in which case σ = daily-RV-implied
15m σ. Both documented per run.

**Metrics** per `(state-bucket, anchor, H)`:

- **Location** — mean forward return (σ)
- **Dispersion** — `std[r|S] / std[r|control]`; forward-RV path = `RV([t, t+H]) / RV([t−H, t])`
- **Shape** — skew; excess kurtosis; `P(r > +2σ)`, `P(r < −2σ)`
- **Path** — `E[MFE]`, `E[MAE]` (σ); `E[time-to-MFE]`, `E[time-to-MAE]` (bars);
  `P(MFE before MAE)`; `P(+1σ before −1σ)`, `P(+2σ before −1σ)`, `P(+1σ before −2σ)`
- **Fair-value** — `P(cross SMA20_d within H)`; `P(cross session-open within H)`;
  `P(return to the pre-impulse origin O within H)` (A2 and A6 only)
- **Terminal quantiles** — 5 / 25 / 50 / 75 / 95th pctile of `r(t, H)`

**Control construction:** see **§2G** — the matched-control pool is same-anchor,
not-in-S, matched mandatorily on instrument / block / anchor-type / session (and
optionally weekday / month-of-year). `Effect = stat(S) − stat(control)`, computed
per block then combined. This removes calendar / regime / session confounds (the
"gold trended so everything looked OK" problem, and the "2h-pre-FOMC is really
just the NY afternoon" problem).

---

## 4. Layer 2 — Artifact defences

Each tied to a failure actually hit in M1–M3.

1. **Block bootstrap** (block length ≥ H bars) for every CI. Report **effective
   n** = `n / (1 + 2 Σ ρ_k)` (k up to lag H), not raw n. — *inflated significance
   from overlapping windows + clustered anchors (5-EMA "t=3.28" was degenerate).*
2. **Pre-registered grid + one FDR control.** Benjamini–Hochberg at **q = 0.10**
   across the *entire* grid (all states × anchors × horizons × metrics). Report
   the total number of hypotheses tested. — *multiple testing.*
3. **Per-block estimation, mandatory.** Compute the effect separately in P1–P4
   with block-bootstrap CIs; **always print the per-block table**. Stability
   requires **all three** of:
   - Cochran's Q across the four blocks with **p > 0.10**, and
   - **I² < 50%** (no significant heterogeneity indicating the effect changes
     mechanism across blocks), and
   - **leave-one-block-out robustness** — dropping any single block leaves the
     pooled effect the *same sign* and within *50%* of the full-sample pooled
     magnitude (no single block carries the result).

   A block whose CI comfortably includes zero is **underpowered, not
   contradicting**, and does not by itself fail stability. There is **no
   "same sign in all four blocks" requirement**, no "every CI excludes zero"
   requirement, and no "identical magnitude" requirement. — *the pooling artifact
   killed H2, H5, H7; a single spectacular block carrying a pooled positive
   killed the H2 OOS read.*
4. **Matched control, always** (see §2G — mandatory on instrument / block /
   anchor-type / session). — *regime & session confound.*
5. **No unregistered interactions** (see §2F). — *H2 deep×slow.*
6. **Cost-ratio decomposition** on every economic claim: split any improvement
   into numerator (better hit / bigger favourable excursion) vs denominator
   (bigger σ / R). Denominator-only improvements are flagged "cost-ratio
   artifact," not signal. — *the ATR-expansion / structural-stop "improvements."*
7. **+1-bar look-ahead shift test** on every state: re-run with all state inputs
   shifted one extra bar; the effect must not materially change. — *the Donchian
   AUC-0.81 leak.*
8. **No forward selection in anchors.** — *survivorship in the anchor.*

---

## 5. Layer 3 — Gates A and B (C deferred)

### A — Predictive  → `YES / NO`

For a `(state, anchor, H, metric)` cell, **A = YES** iff **all three** hold:
1. the effect vs matched control (§2G) is significant at **global FDR q ≤ 0.10**
   (Benjamini–Hochberg over the entire grid);
2. it **survives the +1-bar look-ahead shift test** (pooled effect magnitude
   changes by < 25%);
3. it is **stable across blocks** under the full §4.3 criterion — Cochran Q
   p > 0.10, I² < 50%, **and** leave-one-block-out robust.

Every block estimate is reported regardless of the verdict. **Direction is not
required** — a pure dispersion, tail, skew, or path-ordering shift counts
("state S widens the forward 4h distribution by 30%, stable" is a predictive
fact). Identical magnitudes across blocks are **not** required; every block CI
excluding zero is **not** required; **no single block may carry the pooled
effect**.

### B — Economic  → `MATTERS-AT-R / MATTERS-AT-L-ONLY / NEGLIGIBLE`

For cells with A = YES, construct the **best-case frictionless per-event effect**
implied by the fingerprint (documented formula per metric type; e.g. a path
metric `P(+1σ before −1σ) = p` ⇒ gross `(p·1 − (1−p)·1) σ`). Compare to two
**documented reference friction scenarios** (these are reference points, not
claims about any real account):

- **Scenario R (conservative retail):** ≈ 0.30 σ round-trip. Basis for XAUUSD
  0.01 lot: spread ≈ $0.34 + commission $6/lot + ~1-tick slip ≈ $0.44 vs
  ATR14 ≈ $1.2–1.4. Log the exact assumptions per instrument & period.
- **Scenario L (low-friction reference):** ≈ 0.03–0.05 σ round-trip. Tight
  spread, low commission, no market impact at small size. Explicitly a
  reference point.

Report: gross σ/event; margin vs R; margin vs L; events/year; a rolling estimate
to check for decay within the sample.

### C — Tradable  → **DEFERRED**

Not run in the first several rounds. The first goal is a *map of market
behaviour*. When eventually added, C is **minimal extraction**: a decision rule
produced by a pre-specified deterministic mapping from the fingerprint, with all
thresholds fixed a priori, tested only on **forward paper time** (historical OOS
is spent). No bespoke "clever extraction."

---

## 6. Layer 4 — Ledger record (what the engine accumulates)

```
STATE:        <id | class | mechanism | exact leak-free definition>
ANCHOR:       <id | selection rule (condition-at-t only)>
HORIZON:      <H>
METRIC:       <which fingerprint metric>
N:            raw / de-clustered / effective
EFFECT:       <value in σ units>  vs matched control
BLOCKS:       P1 <e±CI>  P2 <e±CI>  P3 <e±CI>  P4 <e±CI>
              Cochran Q p=<>, I²=<>, leave-one-out <ok?>
A PREDICTIVE: <FDR q> | shift-test <ok?> | stability <ok?>   → YES / NO
B ECONOMIC:   gross σ/event <> | vs R <±> | vs L <±> | events/yr <> | decay <>
              → MATTERS-AT-R / MATTERS-AT-L-ONLY / NEGLIGIBLE
C TRADABLE:   DEFERRED
VERDICT:      one line
```

Example target record (a *market-behaviour primitive*, not a strategy):

```
STATE:  M1 vol regime = HIGH   (market;  vol clustering)
ANCHOR: A1 reference
HORIZON: 16 (4h)
METRIC: dispersion (std ratio) + left-tail P(r < −2σ)
EFFECT: std ratio 1.42 ; P(r<−2σ) +0.031 abs ; location shift negligible
BLOCKS: P1 1.39 / P2 1.45 / P3 1.40 / P4 1.44   Q p=0.71, I²=0
A: YES (q<0.001, shift ok, stable)
B: NEGLIGIBLE at R for a directional trade; MATTERS-AT-L for a dispersion trade
C: DEFERRED
VERDICT: high-vol regime widens the forward 4h distribution and fattens the left
         tail; no directional content; a reusable primitive.
```

---

## 7. First-run protocol (deliberately boring)

The first run answers **one** question:

> Which of the frozen states measurably alter the forward distribution of
> XAUUSD, at which horizons, and by how much?

- Compute the full fingerprint grid: every frozen `(state-bucket, anchor,
  horizon, metric)` cell, with matched control, block estimates, block bootstrap,
  shift test.
- Apply the single FDR correction across the whole grid.
- Produce a Layer-4 ledger row for every cell.
- **Do not read or interpret any individual result until the entire grid is
  computed and FDR-adjusted.** No stopping on the first shiny cell. (Anti-H2.)
- **Run-1 deliverable:** the full ledger table + a one-page summary — how many
  cells passed A, in which state classes, at which horizons, and the B tally for
  those. No strategy, no entry, no stop, no R:R, no "what would I trade."

Interactions (§2F), Layer C (§5), and any strategy design are explicitly out of
scope for run 1 and require their own frozen addendum.

---

## 8. Scope & what this can conclude

- **Instrument-agnostic.** The identical protocol runs on the `basket/`
  14-instrument daily data at daily/4h resolution as a parallel track. XAUUSD is
  one instrument in the scan, not the target.
- Legitimate outcomes of M4:
  1. A small set of **primitives** (states that measurably reshape the forward
     distribution, stable across blocks) — some MATTERS-AT-R, some
     MATTERS-AT-L-ONLY, some NEGLIGIBLE-but-recorded.
  2. **Nothing** clears A beyond FDR noise on any instrument → a far stronger
     basis than "we tried N setups" for concluding that the premise of
     exploitable short-horizon conditional structure needs to change.
- Either way the output is a **map**, and knowledge accumulates: two independent
  sub-cost primitives may later compose into something economically meaningful;
  that composition is a *future* pre-registered round, never a run-1 liberty.

---

## Change log

- **2026-09-10 — v1.** Architecture agreed. Four edits: (1) block-stability via
  Cochran Q / I² instead of "same sign in all 4 blocks"; (2) "reference friction
  scenarios R / L" instead of asserted retail/institutional costs; (3) Layer C
  deferred, defined as minimal deterministic extraction when added; (4) Layer-0
  states organised into market / temporal / event classes, interactions
  prohibited in run 1.

- **2026-09-10 — v1.1 — §2 STATE LIST FROZEN.** Ten states: `M1` realized-vol
  regime, `M2` vol term structure `log(RV5/RV20)`, `M3` lag-1 sign-autocorr(40),
  `M4` long-term displacement (quintiles), `M5` broad-USD 5-bd change
  (XAUUSD-only in Run 1); `T1` unresolved-duration-after-2σ-1h-impulse,
  `T2` failed extreme-resolution count (0/1/2+); `E1`/`E2`/`E3` FOMC / NFP / CPI
  proximity as three separate states (`PRE_24_4` / `PRE_4_0` / `POST_0_4`).
  Dropped from the frozen set: session-as-a-state and time-between-extremes
  (session is retained only as a mandatory control dimension).
  All redlines applied: every `N`/`M` fixed to a single value (impulse = 2.0σ on
  a completed 1h bar; A3 N = 96; windows 48/192 bars; cooldown 16 bars); every
  quantile bucket is trailing-window-only with a 504-day / 200-event warm-up;
  each state carries an explicit information timestamp; anchor table `A1–A6` with
  per-type cooldowns; control hierarchy promoted to §2G with mandatory
  instrument / block / anchor-type / **session** matching; "and a risk proxy if
  available" removed; block-stability tightened with a leave-one-block-out check;
  **every "same sign in all blocks" phrase removed** from §4.3 and §5.A. §2
  is now frozen — next step is Run 1 (fingerprint grid only, no interpretation
  until the whole grid + FDR is complete).

- **2026-09-10 — RUN 1 EXECUTED** (`research/m4/`, see `RUN1_SUMMARY.md`).
  12,782 cells → 1,689 FDR-sig → 619 block-stable → **305 A=YES**.
  291/305 non-directional (distribution *shape*, not centre).  T1 → RETIRED
  (0 stable primitives).  Event-proximity / M1 vol / M4 distance / T2 →
  VALIDATED NON-DIRECTIONAL (provisional).  **Primary lead:** M1 LOW-vol regime +
  new 1-day extreme (A3) → forward continuation ~0.85σ @ 24h, P1–P4 stable,
  ~190 events/yr, clears Scenario-R friction.  **Limitation recorded:** Run 1
  used analytic SEs, not the §4.1 block bootstrap → inference is PROVISIONAL
  pending a v2 moving-block-bootstrap replication (a validation layer only, not a
  new search).  The other 13 directional A=YES cells are SECONDARY — do not
  promote.  Interactions and Layer C remain out of scope.
