"""
Incremental top-up of bars_15min from Dukascopy.

Fetches XAU/USD 15-minute bars (BID + ASK) from the last stored timestamp minus a
2-day overlap, up to now, and DELETE-then-INSERTs that window into bars_15min
(the table has no unique key, so a rewrite of the overlap is the idempotent move).
Rows written by this job carry source = 2.

Safeguards:
  * aborts (no delete) if the fetch is empty or brings nothing newer than what is
    already stored;
  * only touches ts >= (stored_max - 2 days).

This keeps the 15-min series current so research/m4/primary_lead_signal.py has
forward bars to resolve.  It does NOT touch ticks_* or the other bar tables.

Run:  python -m data_pipeline.topup_bars_pg [--days-overlap 2] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

import dukascopy_python as dk
from dukascopy_python.instruments import INSTRUMENT_FX_METALS_XAU_USD as XAU

from data_pipeline.dataset import _pg_dsn

SOURCE_TOPUP = 2
COLS = ["ts", "open", "high", "low", "close", "bid_close", "ask_close",
        "tick_count", "spread_mean", "spread_median", "volume_sum", "source"]


def _fetch(side, start, end):
    df = dk.fetch(XAU, dk.INTERVAL_MIN_15, side, start, end)
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days-overlap", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    dsn = _pg_dsn()
    with psycopg2.connect(**dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT max(ts) FROM bars_15min")
        stored_max = cur.fetchone()[0]
    if stored_max is None:
        raise SystemExit("bars_15min is empty — top-up expects an existing series.")
    stored_max = pd.Timestamp(stored_max).tz_convert("UTC")
    start = (stored_max - pd.Timedelta(days=a.days_overlap)).to_pydatetime()
    end = dt.datetime.now(dt.timezone.utc)
    print(f"stored max = {stored_max}  |  fetching {start:%Y-%m-%d %H:%M} .. {end:%Y-%m-%d %H:%M} UTC")

    bid = _fetch(dk.OFFER_SIDE_BID, start, end)
    ask = _fetch(dk.OFFER_SIDE_ASK, start, end)
    if bid.empty or ask.empty:
        print("no data returned — nothing to do."); return
    idx = bid.index.intersection(ask.index)
    bid, ask = bid.loc[idx], ask.loc[idx]
    fetched_max = idx.max()
    print(f"fetched {len(idx)} bars, newest = {fetched_max}")
    if fetched_max <= stored_max:
        print("nothing newer than stored max — no write."); return

    mid = pd.DataFrame(index=idx)
    for c in ("open", "high", "low", "close"):
        mid[c] = (bid[c] + ask[c]) / 2.0
    mid["bid_close"] = bid["close"]
    mid["ask_close"] = ask["close"]
    mid["tick_count"] = None
    mid["spread_mean"] = (ask["close"] - bid["close"]).clip(lower=0)
    mid["spread_median"] = mid["spread_mean"]
    mid["volume_sum"] = bid["volume"]
    mid["source"] = SOURCE_TOPUP
    mid = mid.reset_index().rename(columns={"index": "ts", "timestamp": "ts"})
    mid["ts"] = pd.to_datetime(mid["ts"], utc=True)
    rows = [tuple(None if pd.isna(v) else v for v in r)
            for r in mid[COLS].itertuples(index=False, name=None)]

    del_from = pd.Timestamp(start).tz_convert("UTC")
    if a.dry_run:
        print(f"[dry-run] would DELETE bars_15min WHERE ts >= {del_from} "
              f"then INSERT {len(rows)} rows (newest {fetched_max}).")
        return
    with psycopg2.connect(**dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM bars_15min WHERE ts >= %s", (del_from.to_pydatetime(),))
        n_del = cur.fetchone()[0]
        if len(rows) < n_del - 5:
            raise SystemExit(f"refusing: fetch has {len(rows)} rows vs {n_del} to delete "
                             f"in the overlap window — looks like a bad fetch.")
        cur.execute("DELETE FROM bars_15min WHERE ts >= %s", (del_from.to_pydatetime(),))
        execute_values(cur,
                       f"INSERT INTO bars_15min ({','.join(COLS)}) VALUES %s", rows,
                       page_size=1000)
        conn.commit()
    print(f"replaced {n_del} rows with {len(rows)}; bars_15min now current to {fetched_max}")


if __name__ == "__main__":
    main()
