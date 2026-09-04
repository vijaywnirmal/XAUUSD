# M2 — Research harness (validation record)

**Date:** 2026-09-04
**Package:** `backtest/` — `engine.py`, `metrics.py`, `strategy.py`, `run.py`, `tests/test_engine.py`

## What the harness is

Event-driven **bar** backtester over the M1 bar store (`data_pipeline.dataset.load_bars`).

- A strategy sees bars `[0..t]`, emits signals for bar `t`.
- **Entries fill at bar `t+1` open (mid)** — no look-ahead.
- Exits: strategy `exit_signal`, ATR/price **stop** & **target** (checked intrabar on mid high/low), **time-stop** (`max_hold_bars`), **session-flat** (`session_flat_hour_utc`), reverse-on-opposite, and EOD.
- **If a bar touches both stop and target, the stop is taken** (pessimistic).
- One position at a time; long/short.

## Cost model (single friction charge, no double-count)

PnL is measured **mid-to-mid**; all friction is one explicit deduction per trade:

| Component | Formula |
|---|---|
| spread | `(spread_mean[entry_bar]/2 + spread_mean[exit_bar]/2) × lots × 100` — real per-bar **Dukascopy** spread |
| slippage | `2 × slippage_ticks × 0.01 × lots × 100` (default 1 tick/side) |
| commission | `$6 × lots` (Vantage Raw ECN $3/side round-turn) |

Dukascopy spreads run ~1 bp wider than Vantage Raw ECN → **costs are conservative**; a real edge should look slightly better live.

Sizing: `fixed` lots (default 0.01) or `risk_pct` (needs a stop; floored at the 0.01 min lot — on a $1k account wide stops therefore over-risk vs the 0.5 % target, exactly the charter's small-account problem). **Ruin guard:** no new trades once equity ≤ 0 (margin call).

## Metrics (`metrics.py`)

`compute_metrics` → n_trades, expectancy ($ and R), profit factor, win rate, **Sharpe/Sortino from daily equity** (robust to flat stretches), max drawdown depth & duration, cost drag, exit-reason mix.
`success_bar` → the Section-6 table with PASS/FAIL (DD ≤ 20 %, PF ≥ 1.25, Sharpe ≥ 1.0, Sortino ≥ 1.5, expectancy > 0, ≥ 300 trades).
`monte_carlo_trades` → resample trade order, p5/p50/p95 of final equity & max DD, prob(profit).

## Validation results — the harness is trusted

| Test | Result |
|---|---|
| **Hand-checked trade** (synthetic, 5 bars) | entry fills at `t+1` open exactly; gross = 3.00, cost = 0.28, net = 2.72 — matches by hand ✅ |
| **Look-ahead** | `entry_i == signal_i + 1` in every case ✅ |
| **Stop-before-target** | bar spanning both → `exit_reason == "stop"` at the stop level ✅ |
| **Buy & hold** (15 m, 2009–2022) | 1 trade; gross PnL = raw price move **to the cent** (no spread double-count); +94 % return, Sharpe 0.35, max DD 42.8 % (the 2011–15 bear) ✅ |
| **Random entries** (5 m, 2015–2022, ~2.6 k trades) | **gross PnL ≈ 0** (−$55, i.e. −$0.02/trade noise); loses **exactly the transaction cost** (expectancy −$0.38 ≈ cost/trade); PF 0.55 ✅ |
| **Random + costs** (unit test) | expectancy < 0, PF < 1, cost > 0 ✅ |
| Engine unit tests | `python -m backtest.tests.test_engine` → ALL PASS |

**Conclusion:** gross PnL reflects only directional edge, cost reflects only friction, and a no-edge strategy loses precisely its costs. Numbers from this harness can be trusted for M3+.

## Usage

```
python -m backtest.run --strategy sma_trend --tf 5min --split in_sample \
       --flat-hour 21 --size-lots 0.01 --params '{"fast":50,"slow":200}'
```

`--split out_of_sample` requires `--allow-oos` (touch-once). `sma_trend` is a **demo, not an edge** — it exists to exercise the full path (it loses: whipsaw + costs).
