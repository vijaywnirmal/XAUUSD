# XAUUSD Trading-Edge Project

A rigorous, documented search for a repeatable mechanical trading edge in
**XAUUSD** (spot gold) for a small retail account.

**Outcome: no deployable edge found.** A negative result, produced on purpose by a
disciplined process (dated falsifiable hypotheses, cost-realistic backtests, a
touch-once out-of-sample, multiple-testing awareness). Roughly ten strategies
looked promising in some window; none survived honest validation.

## Read these first

| File | What it is |
|---|---|
| [`PROJECT_SUMMARY.md`](PROJECT_SUMMARY.md) | **Start here.** Everything built, every hypothesis tested, everything learned. |
| [`M3_CONCLUSION.md`](M3_CONCLUSION.md) | The edge-search conclusion, short form. |
| [`PROJECT_BLUEPRINT.md`](PROJECT_BLUEPRINT.md) | Charter, milestones, the recalibrated success bar, running status log. |
| `research/H*_RESULT.md` | One write-up per hypothesis — mechanism, result, why it failed. |

## Layout

```
data_pipeline/     M1 — canonical true-UTC tick store, bars, frozen splits, QA
backtest/          M2 — event-driven backtester + metrics + validated cost model
research/          M3 — one script + one RESULT.md per hypothesis (H1..H8)
research/basket/   14 daily-bar instruments (Dukascopy) for the trend-book test
carry/  macro/     FRED interest-rate / real-yield / dollar series
qa/                M1 QA report + supporting CSVs
download_*_ticks.py, verify_sources.py   data fetchers / cross-check
```

## Data is not in the repo

`canonical/`, `dukascopy/`, `bars/` (~34 GB of tick/bar data) are gitignored.
Regenerate:

```bash
python download_dukascopy_ticks.py --start 2009-01-01     # ~hours; ~16 GB
python -m data_pipeline.build_canonical                   # -> ./canonical/
python -m data_pipeline.build_bars                        # -> ./bars/
python -m data_pipeline.qa_report                         # -> ./qa/
```

## Environment

Python 3.13. `pip install pandas pyarrow numpy duckdb dukascopy-python
MetaTrader5 scipy`. Windows (paths and the MT5 fetcher assume it).
