"""
Frozen-split data accessor. Everything downstream (research, backtests, the
webapp) loads bars through here so the in-sample / walk-forward / out-of-sample
boundaries are enforced in one place.

    from data_pipeline.dataset import load_bars, SPLITS
    df = load_bars("5min", split="in_sample")

The out-of-sample slice is TOUCH-ONCE: load_bars(..., split="out_of_sample")
raises unless allow_oos=True is passed explicitly.

Backend: the Postgres `xauusd` db (tables bars_1min / bars_5min / bars_15min /
bars_30min / bars_1h), built by db/migrate.py + data_pipeline/build_bars_pg.py.
This is the single source of truth — the parquet bars/ store was retired once
its contents were verified row-for-row against Postgres. Connection settings
come from the PG* env vars (see _pg_dsn), matching db/config.py.
"""

import os
import warnings

import pandas as pd

from . import config as C

SPLITS = C.SPLITS


def _pg_dsn():
    return dict(
        host=os.environ.get("PGHOST", "localhost"),
        port=int(os.environ.get("PGPORT", "5432")),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", "xauusd_dev_pw"),
        dbname=os.environ.get("PGDATABASE", "xauusd"),
    )


def _effective_bounds(split, start, end):
    """Intersect the split window (if any) with explicit start/end into a single
    [lo, hi) pair for the SQL WHERE clause."""
    lo, hi = None, None
    if split:
        lo, hi = C.SPLITS[split]
        lo, hi = pd.Timestamp(lo), pd.Timestamp(hi)
    if start is not None:
        s = pd.Timestamp(start, tz="UTC")
        lo = s if lo is None else max(lo, s)
    if end is not None:
        e = pd.Timestamp(end, tz="UTC")
        hi = e if hi is None else min(hi, e)
    return lo, hi


def _load_bars_postgres(tf, split, start, end, columns):
    import psycopg2

    cols_sql = "*" if not columns else ", ".join(columns)
    lo, hi = _effective_bounds(split, start, end)
    where, params = [], []
    if lo is not None:
        where.append("ts >= %s")
        params.append(lo.to_pydatetime())
    if hi is not None:
        where.append("ts < %s")
        params.append(hi.to_pydatetime())
    sql = f"SELECT {cols_sql} FROM bars_{tf}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ts"

    with psycopg2.connect(**_pg_dsn()) as conn:
        with warnings.catch_warnings():
            # pandas warns that a raw DBAPI (psycopg2) connection isn't SQLAlchemy;
            # read_sql works fine with it and we don't want the SQLAlchemy dep.
            warnings.filterwarnings("ignore", message=".*SQLAlchemy.*")
            df = pd.read_sql(sql, conn, params=params)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.sort_values("ts").reset_index(drop=True)


def load_bars(tf="1min", split=None, start=None, end=None, allow_oos=False, columns=None):
    if tf not in C.BAR_TIMEFRAMES:
        raise ValueError(f"tf must be one of {C.BAR_TIMEFRAMES}")
    if split == "out_of_sample" and not allow_oos:
        raise RuntimeError(
            "out_of_sample is touch-once. Pass allow_oos=True only for the single "
            "final validation run, and record that you did."
        )
    return _load_bars_postgres(tf, split, start, end, columns)


def split_of(ts):
    return C.split_of(pd.Timestamp(ts, tz="UTC"))


def describe_splits():
    for tf in C.BAR_TIMEFRAMES:
        try:
            all_df = load_bars(tf, allow_oos=True, columns=["ts"])
        except Exception as e:
            print(f"{tf}: unavailable ({type(e).__name__})")
            continue
        line = [f"{tf}:"]
        for name, (lo, hi) in C.SPLITS.items():
            n = ((all_df["ts"] >= lo) & (all_df["ts"] < hi)).sum()
            line.append(f"{name}={n:,}")
        print("  ".join(line))
