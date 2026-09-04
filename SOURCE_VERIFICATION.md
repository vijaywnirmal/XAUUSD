# Source Cross-Verification — Vantage (MT5) vs Dukascopy

**Date:** 2026-09-04
**Scripts:** `verify_sources.py` (comparison), `download_dukascopy_ticks.py` (Dukascopy fetch)
**Sample months:** 2018-06, 2020-03 (COVID), 2022-09, 2025-06 — chosen across regimes.

---

## Headline findings

### 1. The MT5 / Vantage archive is NOT in UTC — it is in Vantage *server* time

Detected by maximising 1-minute log-return correlation against Dukascopy (which **is** true UTC):

| Month | MT5 clock is ahead of UTC by | Return corr after alignment |
|-------|------------------------------|-----------------------------|
| 2018-06 | **+120 min** | 0.989 |
| 2020-03 | +180 min (month straddles a DST change) | 0.919 |
| 2022-09 | **+180 min** | 0.992 |
| 2025-06 | **+180 min** | 0.997 |

Vantage's MT5 server ran at roughly **GMT+2 (fixed)** in the early years and moved to
**GMT+2 winter / GMT+3 summer** by 2020. The Parquet metadata labels the column UTC,
but the wall-clock is server-local. **This must be corrected before any
session-based logic.** A NY-session strategy built on the raw timestamps would have
its entire session window shifted 2–3 hours.

Consequence of the Feb-2020 patch: those ticks came from Dukascopy and **are** true
UTC, so the archive is currently **mixed-timezone** until M1 normalises it.

### 2. After time-alignment, the two feeds agree on price to sub-basis-point

| Month | Median price diff | Mean | p95 abs diff |
|-------|-------------------|------|--------------|
| 2018-06 | 0.00 bps | 0.00 bps | 0.33 bps |
| 2020-03 | 0.11 bps | 0.08 bps | **5.99 bps** |
| 2022-09 | 0.06 bps | 0.01 bps | 0.53 bps |
| 2025-06 | 0.00 bps | 0.00 bps | 0.37 bps |

Outside the March-2020 crisis, Dukascopy mid-price tracks the Vantage feed within
a fraction of a cent. **Dukascopy is a sound proxy for the pre-2017 extension and
the Feb-2020 fill.** March 2020 genuinely diverges ~6 bps at the 95th percentile
(different liquidity providers during the liquidity crunch, plus the DST-straddle
weakening a single fixed offset) — results that hinge on 2020-03 microstructure
should be checked on both sources.

### 3. Spreads differ — use Vantage spreads for the cost model, never Dukascopy's

| Month | Median spread MT5 | Median spread Dukascopy |
|-------|-------------------|-------------------------|
| 2018-06 | 1.48 bps ($0.19) | 1.82 bps ($0.23) |
| 2020-03 | 2.76 bps ($0.43) | 2.26 bps ($0.36) |
| 2022-09 | 0.96 bps ($0.16) | 1.95 bps ($0.33) |
| 2025-06 | 0.54 bps ($0.18) | 1.79 bps ($0.60) |

The **Vantage Raw ECN feed is meaningfully tighter** than Dukascopy's aggregate in
2022 and 2025 (roughly half the spread). Costing a backtest on Dukascopy spreads
would **overstate** round-turn cost by ~1 bp (~$0.15–0.25/oz) in recent regimes.
Always model cost from the Vantage archive's own per-tick spread, plus the
$6/lot round-turn commission and a slippage buffer.

---

## How much difference does it make? (summary)

| Dimension | Difference | Impact on the project |
|-----------|-----------|-----------------------|
| **Timestamp / session timing** | 2–3 hours (server time vs UTC) | **Critical** for the intraday NY-session edge. M1 must convert the whole MT5 archive to true UTC via a per-month offset table. |
| **Mid-price path (calm markets)** | < 0.5 bps | Negligible. Dukascopy is fine for pre-2017 and Feb-2020. |
| **Mid-price path (2020-03 crisis)** | up to ~6 bps p95 | Minor but real. Flag any 2020-03-dependent result; verify on both feeds. |
| **Spread / transaction cost** | ~1 bp, Vantage tighter | Cost model uses Vantage spreads only. Dukascopy would make strategies look ~1 bp/trade worse than reality. |
| **Volume** | MT5 = 0 (unusable); Dukascopy = non-zero relative units | Dukascopy volume can serve as an activity proxy where MT5 has none. |

---

## Action items folded into the blueprint (M1)

1. Build a **UTC-correction table**: for every MT5 month, cross-correlate against
   Dukascopy, snap to the nearest 15-min offset with corr > 0.95, convert to true UTC.
   Manually review any month where corr < 0.95 (crisis months, DST-straddle months).
2. After conversion, **re-verify** the Feb-2020 seam and the 2017-08 Dukascopy→MT5
   seam show no discontinuity.
3. Lock the **source-precedence rule**: Vantage for 2017-08→present (except 2020-02);
   Dukascopy before that and for 2020-02; cost model always Vantage spreads.
4. Keep `./dukascopy/` as an independent second archive for ongoing spot-checks.
