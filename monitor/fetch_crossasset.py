"""
One-time: pull M5 history for the cross-asset instruments used as features
(EURUSD, USDJPY -> USD-strength proxy) from Dukascopy into monitor/data/.

    python -m monitor.fetch_crossasset [--start 2016-01-01]

BTCUSD is live-only (MT5) - no long clean intraday history needed for training.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

import pandas as pd

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA, exist_ok=True)

INSTR = {
    "EURUSD": "INSTRUMENT_FX_MAJORS_EUR_USD",
    "USDJPY": "INSTRUMENT_FX_MAJORS_USD_JPY",
}


def fetch_one(sym: str, start: datetime, end: datetime) -> pd.DataFrame:
    import dukascopy_python
    from dukascopy_python import instruments as I
    inst = getattr(I, INSTR[sym])
    df = dukascopy_python.fetch(inst, dukascopy_python.INTERVAL_MIN_5,
                                dukascopy_python.OFFER_SIDE_BID, start, end)
    df = df[["close"]].rename(columns={"close": sym})
    df.index = pd.to_datetime(df.index, utc=True)
    return df[~df.index.duplicated()].sort_index()


def load(sym: str) -> pd.DataFrame:
    p = os.path.join(DATA, f"{sym}_m5.parquet")
    return pd.read_parquet(p) if os.path.exists(p) else pd.DataFrame()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2016-01-01")
    a = ap.parse_args()
    start = datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    for sym in INSTR:
        print(f"fetching {sym} {a.start}..now ...", flush=True)
        df = fetch_one(sym, start, end)
        out = os.path.join(DATA, f"{sym}_m5.parquet")
        df.to_parquet(out)
        print(f"  {sym}: {len(df):,} bars -> {out}  ({df.index.min()} .. {df.index.max()})")


if __name__ == "__main__":
    main()
