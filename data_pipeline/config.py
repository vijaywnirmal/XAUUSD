"""
Central config for the XAUUSD data pipeline (M1).

SOURCE OF TRUTH: Dukascopy (`./dukascopy/`), true UTC, 2009-01 -> present.
The Vantage/MT5 archive was removed on 2026-09-04; `mt5_utc_offsets.csv` and the
SOURCE_VERIFICATION analysis are kept only as historical record of the
Vantage-server-time finding. Everything downstream is single-source Dukascopy.
"""

import os
from datetime import datetime, timezone

# --- paths ----------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MT5_DIR = os.path.join(ROOT, "{side}")                       # ./bid , ./ask   (Vantage, server time)
DUKA_DIR = os.path.join(ROOT, "dukascopy", "{side}")         # ./dukascopy/bid , /ask (true UTC)
CANON_DIR = os.path.join(ROOT, "canonical", "{side}")        # built by build_canonical.py
BARS_DIR = os.path.join(ROOT, "bars")                        # built by build_bars.py
PIPE_DIR = os.path.dirname(os.path.abspath(__file__))
QA_DIR = os.path.join(ROOT, "qa")

OFFSETS_CSV = os.path.join(PIPE_DIR, "mt5_utc_offsets.csv")

SIDES = ("bid", "ask")


def month_path(dir_tmpl, side, year, month):
    return os.path.join(dir_tmpl.format(side=side), f"year={year}", f"month={month:02d}", "ticks.parquet")


# --- source rule ------------------------------------------------------------
# Single source now. Kept as a function so downstream code is unchanged and a
# second source could be reintroduced later.
def source_for_month(year, month):
    return "duka"


def low_quality_mt5_months():
    return set()   # not applicable single-source; retained for API compatibility


# --- cleaning thresholds ---------------------------------------------------
MIN_PRICE = 1.0                 # gold never below this; drops zero/garbage prints
MAX_ABS_LOG_RET_PER_TICK = 0.02   # ~2% single-tick jump -> candidate bad tick
OUTLIER_REVERT_TICKS = 5        # a spike that reverts within N ticks is removed
MAX_SPREAD_MULT = 25.0          # drop quotes wider than N x the month's median spread

# --- bar timeframes ------------------------------------------------------------
# 1min/5min/15min are built by build_bars.py from canonical/ tick parquet (the
# original M1 pipeline). 30min/1h are built by build_bars_pg.py, aggregated
# directly from the Postgres tick archive (ticks_bid/ticks_ask) instead, since
# dukascopy/ and canonical/ were deleted once their contents were verified
# migrated row-for-row into Postgres — same OHLC/spread/volume semantics.
BAR_TIMEFRAMES = ("1min", "5min", "15min", "30min", "1h")

# --- data splits (frozen) ----------------------------------------------------
# Extended vs the original blueprint: in-sample now starts at the Dukascopy
# beginning so the 2011-2015 gold bear is in the build set. Walk-forward and
# out-of-sample are unchanged. OOS is touched exactly once.
SPLITS = {
    "in_sample":     (datetime(2009, 1, 1, tzinfo=timezone.utc),  datetime(2023, 1, 1, tzinfo=timezone.utc)),
    "walk_forward":  (datetime(2023, 1, 1, tzinfo=timezone.utc),  datetime(2024, 7, 1, tzinfo=timezone.utc)),
    "out_of_sample": (datetime(2024, 7, 1, tzinfo=timezone.utc),  datetime(2026, 9, 4, tzinfo=timezone.utc)),
}


def split_of(ts):
    for name, (lo, hi) in SPLITS.items():
        if lo <= ts < hi:
            return name
    return None
