"""
One-time migration: parquet (bars/ + canonical/{bid,ask}/) -> Postgres (xauusd db).

    python -m db.migrate --schema           # create tables + partitions (idempotent)
    python -m db.migrate --bars             # load bars_1min / bars_5min / bars_15min
    python -m db.migrate --ticks            # load ticks_bid / ticks_ask (~1.37B rows, slow)
    python -m db.migrate --index            # create indexes + ANALYZE (run after loads)
    python -m db.migrate --verify           # compare Postgres row counts vs parquet row counts
    python -m db.migrate --all              # schema -> bars -> ticks -> index -> verify

Uses COPY (via psycopg2 copy_expert) for bulk load speed, one parquet file at a
time to bound memory. Idempotent: re-running --bars/--ticks TRUNCATEs each
table/partition immediately before reloading it, so it's safe to re-run after
a partial failure.
"""

import argparse
import glob
import io
import os
import sys
import time

import psycopg2

from .config import PG_DSN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BARS_DIR = os.path.join(ROOT, "bars")
CANON_DIR = os.path.join(ROOT, "canonical")
SCHEMA_SQL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

BAR_TFS = ("1min", "5min", "15min")
BAR_COLS = ["ts", "open", "high", "low", "close", "bid_close", "ask_close",
            "tick_count", "spread_mean", "spread_median", "volume_sum", "source"]
TICK_COLS = ["time_msc", "time", "price", "volume", "flags", "source"]


def connect():
    conn = psycopg2.connect(**PG_DSN)
    conn.autocommit = True
    return conn


def create_schema(conn):
    with open(SCHEMA_SQL, "r") as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    print("schema created / verified")


def _copy_df(conn, table, cols, df):
    if len(df) == 0:
        return 0
    buf = io.StringIO()
    df.to_csv(buf, columns=cols, index=False, header=False, na_rep="")
    buf.seek(0)
    with conn.cursor() as cur:
        cur.copy_expert(
            f"COPY {table} ({','.join(cols)}) FROM STDIN WITH (FORMAT csv, NULL '')",
            buf,
        )
    return len(df)


def load_bars(conn):
    import pandas as pd

    for tf in BAR_TFS:
        table = f"bars_{tf}"
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE {table};")
        files = sorted(glob.glob(os.path.join(BARS_DIR, tf, "year=*", "bars.parquet")))
        total = 0
        t0 = time.time()
        for fp in files:
            df = pd.read_parquet(fp)
            n = _copy_df(conn, table, BAR_COLS, df)
            total += n
        print(f"{table}: loaded {total:,} rows from {len(files)} files in {time.time()-t0:.1f}s")


def load_ticks(conn):
    import pandas as pd

    for side in ("bid", "ask"):
        table = f"ticks_{side}"
        files = sorted(glob.glob(os.path.join(CANON_DIR, side, "year=*", "month=*", "ticks.parquet")))
        print(f"{table}: {len(files)} monthly files to load")
        # truncate all partitions for this side up front (idempotent re-run)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT inhrelid::regclass FROM pg_inherits WHERE inhparent = %s::regclass",
                (table,),
            )
            parts = [r[0] for r in cur.fetchall()]
            for p in parts:
                cur.execute(f"TRUNCATE {p};")
        total = 0
        t0 = time.time()
        for i, fp in enumerate(files, 1):
            df = pd.read_parquet(fp)
            n = _copy_df(conn, table, TICK_COLS, df)
            total += n
            if i % 12 == 0 or i == len(files):
                elapsed = time.time() - t0
                rate = total / elapsed if elapsed > 0 else 0
                print(f"  [{table}] {i}/{len(files)} files, {total:,} rows, "
                      f"{elapsed:.0f}s elapsed, {rate:,.0f} rows/s")
        print(f"{table}: loaded {total:,} rows from {len(files)} files in {time.time()-t0:.1f}s")


def create_indexes(conn):
    stmts = [
        # plain (non-unique) index: bars_1min has one known pre-existing duplicate
        # ts in the source parquet (2025-08-01 00:00:00 UTC, see project notes) —
        # a unique index would silently drop a row and diverge from the source.
        "CREATE INDEX IF NOT EXISTS bars_1min_ts_idx ON bars_1min (ts);",
        "CREATE INDEX IF NOT EXISTS bars_5min_ts_idx ON bars_5min (ts);",
        "CREATE INDEX IF NOT EXISTS bars_15min_ts_idx ON bars_15min (ts);",
        "CREATE INDEX IF NOT EXISTS ticks_bid_time_brin ON ticks_bid USING brin (time);",
        "CREATE INDEX IF NOT EXISTS ticks_ask_time_brin ON ticks_ask USING brin (time);",
    ]
    with conn.cursor() as cur:
        for s in stmts:
            print("  ", s)
            cur.execute(s)
        cur.execute("ANALYZE;")
    print("indexes created, ANALYZE done")


def verify(conn):
    import pandas as pd
    import pyarrow.parquet as pq

    print("=== row-count verification (Postgres vs parquet) ===")
    with conn.cursor() as cur:
        for tf in BAR_TFS:
            cur.execute(f"SELECT count(*) FROM bars_{tf};")
            pg_n = cur.fetchone()[0]
            files = glob.glob(os.path.join(BARS_DIR, tf, "year=*", "bars.parquet"))
            src_n = sum(pq.ParquetFile(f).metadata.num_rows for f in files)
            status = "OK" if pg_n == src_n else "MISMATCH"
            print(f"  bars_{tf}: postgres={pg_n:,} parquet={src_n:,}  {status}")

        for side in ("bid", "ask"):
            cur.execute(f"SELECT count(*) FROM ticks_{side};")
            pg_n = cur.fetchone()[0]
            files = glob.glob(os.path.join(CANON_DIR, side, "year=*", "month=*", "ticks.parquet"))
            src_n = sum(pq.ParquetFile(f).metadata.num_rows for f in files)
            status = "OK" if pg_n == src_n else "MISMATCH"
            print(f"  ticks_{side}: postgres={pg_n:,} parquet={src_n:,}  {status}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", action="store_true")
    ap.add_argument("--bars", action="store_true")
    ap.add_argument("--ticks", action="store_true")
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if not any([args.schema, args.bars, args.ticks, args.index, args.verify, args.all]):
        ap.print_help()
        sys.exit(1)

    # The parquet stores (bars/, canonical/) were the migration SOURCE and have
    # since been retired — Postgres is now the single source of truth. Steps
    # that read from parquet can no longer run; only --schema/--index remain
    # useful (e.g. rebuilding an index).
    needs_parquet = args.bars or args.ticks or args.verify or args.all
    if needs_parquet and not (os.path.isdir(BARS_DIR) or os.path.isdir(CANON_DIR)):
        print(
            "parquet source (bars/, canonical/) has been retired - the migration "
            "is complete and Postgres is authoritative.\n"
            "  - to (re)build derived bar timeframes: python -m data_pipeline.build_bars_pg\n"
            "  - to (re)create indexes only:          python -m db.migrate --index",
            file=sys.stderr,
        )
        sys.exit(2)

    conn = connect()
    try:
        if args.schema or args.all:
            create_schema(conn)
        if args.bars or args.all:
            load_bars(conn)
        if args.ticks or args.all:
            load_ticks(conn)
        if args.index or args.all:
            create_indexes(conn)
        if args.verify or args.all:
            verify(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
