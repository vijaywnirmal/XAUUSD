import os
import sys
import glob
import json
import time
import argparse
import subprocess
from datetime import datetime, timezone, timedelta

import MetaTrader5 as mt5
import pandas as pd


SYMBOL = "XAUUSD"

# The archive lives directly under the project folder as ./ask/... and ./bid/...
# (matching the existing 6+ GB history). State/metadata/log go in ./_fetch_state/.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = PROJECT_ROOT
STATE_DIR = os.path.join(PROJECT_ROOT, "_fetch_state")

# Default archive start (overridable with --start). This is where the current
# archive begins; run `--probe-earliest` to learn how far back the broker will
# actually serve ticks, then `--start <date>` to backfill.
DEFAULT_ARCHIVE_START = datetime(2017, 8, 1, 0, 0, 0, tzinfo=timezone.utc)

# Absolute lower bound for any probe/backfill request.
HARD_FLOOR = datetime(2004, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

# Mutable run-time floor; set from --start (or DEFAULT_ARCHIVE_START).
ARCHIVE_START = DEFAULT_ARCHIVE_START

INITIAL_CHUNK_HOURS = 24
MIN_CHUNK_MINUTES = 1
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
UPDATE_OVERLAP_SECONDS = 2

# Probe tuning: broker tick history is fetched from the server on demand and can
# take several seconds to arrive, so the probe waits longer than a normal request.
PROBE_WINDOW_DAYS = 10
PROBE_TRIES = 12
PROBE_DELAY_SECONDS = 3

TASK_NAME = "XAUUSD MT5 Daily Fetch"


def utc_now():
    return datetime.now(timezone.utc)


def fmt(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " UTC"


def ensure_utc(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def from_msc(msc):
    return datetime.fromtimestamp(msc / 1000.0, tz=timezone.utc)


def symbol_root():
    return DATA_ROOT


def side_root(side):
    return os.path.join(symbol_root(), side)


def metadata_path():
    return os.path.join(STATE_DIR, "metadata.json")


def state_path():
    return os.path.join(STATE_DIR, "download_state.json")


def log_path():
    return os.path.join(STATE_DIR, "fetch.log")


def log_line(msg):
    stamp = utc_now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp} UTC] {msg}"
    print(line)
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def month_file(side, dt):
    return os.path.join(
        side_root(side),
        f"year={dt.year}",
        f"month={dt.month:02d}",
        "ticks.parquet",
    )


def read_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"Warning: could not read {path}: {exc}")
        return None


def write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(temp, path)


def initialize_mt5():
    print("Connecting to MetaTrader 5...")
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialization failed: {mt5.last_error()}")
    if not mt5.symbol_select(SYMBOL, True):
        raise RuntimeError(f"Could not select {SYMBOL}: {mt5.last_error()}")

    account = mt5.account_info()
    info = mt5.symbol_info(SYMBOL)
    print(f"Symbol: {SYMBOL}")
    if account is not None:
        print(f"Account: {account.login}")
        print(f"Server:  {account.server}")
    if info is not None:
        print(f"Digits:  {info.digits}")
        print(f"Point:   {info.point}")


def latest_archived_time():
    """Newest tick timestamp present in the on-disk archive (bid or ask).

    Lets a daily run resume correctly even if the state file is missing or was
    written for the old ./data/XAUUSD layout.
    """
    newest = None
    for side in ("bid", "ask"):
        files = glob.glob(
            os.path.join(side_root(side), "year=*", "month=*", "ticks.parquet")
        )
        if not files:
            continue

        def sort_key(p):
            parts = p.replace("\\", "/").split("/")
            y = int([s for s in parts if s.startswith("year=")][0].split("=")[1])
            m = int([s for s in parts if s.startswith("month=")][0].split("=")[1])
            return (y, m)

        latest_file = max(files, key=sort_key)
        try:
            col = pd.read_parquet(latest_file, columns=["time_msc"])
            if len(col):
                ts = from_msc(int(col["time_msc"].max()))
                if newest is None or ts > newest:
                    newest = ts
        except Exception as exc:
            print(f"Warning: could not read {latest_file}: {exc}")
    return newest


def get_last_saved_time():
    state = read_json(state_path())
    value = state.get("last_completed_time_msc") if state else None
    from_state = from_msc(int(value)) if value is not None else None

    from_disk = latest_archived_time()

    # Trust whichever is later so we never re-download years unnecessarily and
    # never skip a gap between the state file and the real archive.
    if from_state and from_disk:
        return max(from_state, from_disk)
    return from_state or from_disk


def save_download_state(last_completed_time):
    last_completed_time = ensure_utc(last_completed_time)
    write_json_atomic(
        state_path(),
        {
            "symbol": SYMBOL,
            "last_completed_time_msc": int(last_completed_time.timestamp() * 1000),
            "last_completed_time": last_completed_time.isoformat(),
            "updated_at": utc_now().isoformat(),
        },
    )


def save_metadata():
    latest_saved = get_last_saved_time()
    write_json_atomic(
        metadata_path(),
        {
            "symbol": SYMBOL,
            "confirmed_archive_start": ARCHIVE_START.isoformat(),
            "last_completed_time": latest_saved.isoformat() if latest_saved else None,
            "storage": {
                "bid": "Separate monthly Parquet files",
                "ask": "Separate monthly Parquet files",
            },
            "updated_at": utc_now().isoformat(),
        },
    )


def request_ticks(start_time, end_time):
    start_time = ensure_utc(start_time)
    end_time = ensure_utc(end_time)

    for attempt in range(1, MAX_RETRIES + 1):
        ticks = mt5.copy_ticks_range(
            SYMBOL,
            start_time,
            end_time,
            mt5.COPY_TICKS_ALL,
        )
        if ticks is not None:
            return pd.DataFrame(ticks)

        print(
            f"  MT5 request failed {mt5.last_error()} "
            f"({attempt}/{MAX_RETRIES})"
        )
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SECONDS)

    return None


def download_range_adaptive(start_time, end_time):
    if start_time >= end_time:
        return [], []

    df = request_ticks(start_time, end_time)
    if df is not None:
        return [df], []

    duration = end_time - start_time
    if duration <= timedelta(minutes=MIN_CHUNK_MINUTES):
        print(f"  FAILED minimum chunk: {fmt(start_time)} -> {fmt(end_time)}")
        return [], [(start_time, end_time)]

    midpoint = start_time + duration / 2
    print(f"  Splitting failed range: {fmt(start_time)} -> {fmt(end_time)}")

    left_data, left_failed = download_range_adaptive(start_time, midpoint)
    right_data, right_failed = download_range_adaptive(midpoint, end_time)

    return left_data + right_data, left_failed + right_failed


def split_bid_ask(raw_df):
    if raw_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = raw_df.copy()
    df["time"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True)

    bid_df = df.loc[
        df["bid"] > 0,
        ["time_msc", "time", "bid", "volume", "flags"],
    ].copy().rename(columns={"bid": "price"})

    ask_df = df.loc[
        df["ask"] > 0,
        ["time_msc", "time", "ask", "volume", "flags"],
    ].copy().rename(columns={"ask": "price"})

    return bid_df, ask_df


def append_to_month(side, df):
    if df.empty:
        return 0

    work = df.copy()
    work["year"] = work["time"].dt.year
    work["month"] = work["time"].dt.month
    total_added = 0

    for (year, month), part in work.groupby(["year", "month"]):
        part = part.drop(columns=["year", "month"]).copy()
        dt = datetime(int(year), int(month), 1, tzinfo=timezone.utc)
        path = month_file(side, dt)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        if os.path.exists(path):
            existing = pd.read_parquet(path)
            before = len(existing)
            combined = pd.concat([existing, part], ignore_index=True)
        else:
            before = 0
            combined = part

        dedupe_cols = [
            c for c in ["time_msc", "price", "volume", "flags"]
            if c in combined.columns
        ]
        combined = (
            combined.drop_duplicates(subset=dedupe_cols)
            .sort_values("time_msc")
            .reset_index(drop=True)
        )

        temp = path + ".tmp"
        combined.to_parquet(temp, index=False)
        os.replace(temp, path)
        total_added += max(len(combined) - before, 0)

    return total_added


def process_tick_dataframe(raw_df):
    if raw_df.empty:
        return 0, 0

    bid_df, ask_df = split_bid_ask(raw_df)
    return append_to_month("bid", bid_df), append_to_month("ask", ask_df)


def download_period(start_time, end_time, *, update_state=False):
    start_time = max(ensure_utc(start_time), ARCHIVE_START)
    end_time = ensure_utc(end_time)

    if start_time >= end_time:
        return {"bid_added": 0, "ask_added": 0, "failed_ranges": []}

    cursor = start_time
    total_bid = 0
    total_ask = 0
    failed_ranges = []

    while cursor < end_time:
        chunk_end = min(
            cursor + timedelta(hours=INITIAL_CHUNK_HOURS),
            end_time,
        )

        print(f"\nRange: {fmt(cursor)} -> {fmt(chunk_end)}")
        dataframes, failures = download_range_adaptive(cursor, chunk_end)

        if failures:
            failed_ranges.extend(failures)
            print(f"  WARNING: {len(failures)} sub-range(s) failed; state not advanced for this chunk.")
        else:
            for raw_df in dataframes:
                if raw_df.empty:
                    continue
                bid_added, ask_added = process_tick_dataframe(raw_df)
                total_bid += bid_added
                total_ask += ask_added

            if update_state:
                save_download_state(chunk_end)

        print(f"  Total new Bid: {total_bid:,}")
        print(f"  Total new Ask: {total_ask:,}")
        cursor = chunk_end
        time.sleep(0.05)

    if update_state and not failed_ranges:
        save_metadata()

    return {
        "bid_added": total_bid,
        "ask_added": total_ask,
        "failed_ranges": failed_ranges,
    }


def download_all(until=None):
    last_saved = get_last_saved_time()
    end_time = ensure_utc(until or utc_now())

    if last_saved is None:
        start_time = ARCHIVE_START
        print(f"No previous state. Starting from {fmt(start_time)}")
    else:
        start_time = max(
            last_saved - timedelta(seconds=UPDATE_OVERLAP_SECONDS),
            ARCHIVE_START,
        )
        print(f"Resuming from {fmt(start_time)}")

    if start_time >= end_time:
        print(f"Already complete through {fmt(end_time)}")
        return {
            "bid_added": 0,
            "ask_added": 0,
            "failed_ranges": [],
            "until": end_time.isoformat(),
            "skipped": True,
        }

    result = download_period(start_time, end_time, update_state=True)

    if result["failed_ranges"]:
        print("\nDOWNLOAD COMPLETED WITH FAILED RANGES:")
        for start, end in result["failed_ranges"]:
            print(f"  {fmt(start)} -> {fmt(end)}")
        raise RuntimeError(
            "One or more minimum-size ranges failed. "
            "The completion state was not advanced past those chunks."
        )

    print("\nDOWNLOAD COMPLETE")
    print(f"New Bid ticks: {result['bid_added']:,}")
    print(f"New Ask ticks: {result['ask_added']:,}")
    return {**result, "until": end_time.isoformat(), "skipped": False}


def previous_day_cutoff(now=None):
    now = ensure_utc(now or utc_now())
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def update_through_previous_day():
    return download_all(until=previous_day_cutoff())


def repair_range(start_time, end_time):
    """
    Re-download an exact UTC range without deleting existing data.
    Overlapping ticks are merged and deduplicated.
    """
    print("\nREPAIR MODE")
    print(f"Repairing: {fmt(start_time)} -> {fmt(end_time)}")
    result = download_period(start_time, end_time, update_state=False)

    if result["failed_ranges"]:
        print("\nREPAIR FAILED FOR:")
        for start, end in result["failed_ranges"]:
            print(f"  {fmt(start)} -> {fmt(end)}")
        raise RuntimeError("Repair did not complete successfully.")

    print("\nREPAIR COMPLETE")
    print(f"New Bid ticks: {result['bid_added']:,}")
    print(f"New Ask ticks: {result['ask_added']:,}")


def parse_utc(value):
    value = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    return ensure_utc(dt)


def parse_date_arg(value):
    """Accept 'YYYY-MM-DD' or a full ISO timestamp; return aware UTC datetime."""
    value = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        dt = datetime.strptime(value, "%Y-%m-%d")
    return ensure_utc(dt)


# ---------------------------------------------------------------------------
# Earliest-history probe
# ---------------------------------------------------------------------------

def _window_has_ticks(start_time):
    """True if the broker returns any ticks in a PROBE_WINDOW_DAYS window.

    Uses long, patient retries because MT5 fetches deep history from the server
    asynchronously and the first few calls often return 0 while it downloads.
    """
    start_time = ensure_utc(start_time)
    end_time = start_time + timedelta(days=PROBE_WINDOW_DAYS)
    for attempt in range(1, PROBE_TRIES + 1):
        ticks = mt5.copy_ticks_range(
            SYMBOL, start_time, end_time, mt5.COPY_TICKS_ALL
        )
        if ticks is not None and len(ticks) > 0:
            first = from_msc(int(ticks[0]["time_msc"]))
            return True, len(ticks), first
        time.sleep(PROBE_DELAY_SECONDS)
    return False, 0, None


def probe_earliest(floor):
    """Find the earliest XAUUSD tick the broker will serve.

    Fast path: `copy_ticks_from(HARD_FLOOR, 1)` — MT5 clamps a too-early request
    to the earliest available tick, so this returns the boundary directly.
    Fallback: a month-by-month bisect with `copy_ticks_range` if the fast path
    yields nothing.
    """
    floor = max(ensure_utc(floor), HARD_FLOOR)

    log_line("PROBE: asking broker for its earliest tick (clamped request) ...")
    for attempt in range(1, PROBE_TRIES + 1):
        ticks = mt5.copy_ticks_from(
            SYMBOL, HARD_FLOOR, 1, mt5.COPY_TICKS_ALL
        )
        if ticks is not None and len(ticks) > 0:
            first = from_msc(int(ticks[0]["time_msc"]))
            earliest_month = datetime(first.year, first.month, 1, tzinfo=timezone.utc)
            log_line(f"PROBE RESULT: earliest served tick = {fmt(first)} "
                     f"(month {earliest_month.strftime('%Y-%m')})")
            meta = read_json(metadata_path()) or {}
            meta.update({
                "symbol": SYMBOL,
                "probe_earliest_month": earliest_month.isoformat(),
                "probe_first_tick_seen": first.isoformat(),
                "probe_method": "copy_ticks_from clamp",
                "probe_run_at": utc_now().isoformat(),
            })
            write_json_atomic(metadata_path(), meta)
            return earliest_month
        time.sleep(PROBE_DELAY_SECONDS)

    log_line("PROBE: clamp method returned nothing; falling back to bisect.")
    return _probe_earliest_bisect(floor)


def _probe_earliest_bisect(floor):
    """Fallback: bisect month-by-month between `floor` and a recent known-good
    point for the boundary between "no data" and "data".
    """
    floor = max(ensure_utc(floor), HARD_FLOOR)
    known_good = datetime(
        (utc_now() - timedelta(days=20)).year,
        (utc_now() - timedelta(days=20)).month,
        1,
        tzinfo=timezone.utc,
    )

    log_line(f"PROBE: verifying recent history at {fmt(known_good)} ...")
    ok, n, first = _window_has_ticks(known_good)
    if not ok:
        log_line(
            "PROBE: could not retrieve even recent ticks. Check that the MT5 "
            "terminal is logged in and connected, then retry."
        )
        return None
    log_line(f"PROBE: recent OK ({n:,} ticks, first {fmt(first)}).")

    # Build a list of month starts from floor .. known_good, then binary search
    # for the boundary between "no data" and "data".
    months = []
    cur = datetime(floor.year, floor.month, 1, tzinfo=timezone.utc)
    while cur <= known_good:
        months.append(cur)
        year, month = cur.year + (cur.month // 12), (cur.month % 12) + 1
        cur = datetime(year, month, 1, tzinfo=timezone.utc)

    lo, hi = 0, len(months) - 1          # invariant: months[hi] has data
    earliest_hit = months[hi]
    while lo <= hi:
        mid = (lo + hi) // 2
        m = months[mid]
        log_line(f"PROBE: testing {m.strftime('%Y-%m')} ...")
        ok, n, first = _window_has_ticks(m)
        if ok:
            earliest_hit = first or m
            log_line(f"PROBE:   data present ({n:,} ticks, first {fmt(first)})")
            hi = mid - 1
        else:
            log_line("PROBE:   no data")
            lo = mid + 1

    earliest_month = datetime(earliest_hit.year, earliest_hit.month, 1, tzinfo=timezone.utc)
    log_line(f"PROBE RESULT: earliest served tick history ~ {earliest_month.strftime('%Y-%m')} "
             f"(first tick seen {fmt(earliest_hit)})")

    meta = read_json(metadata_path()) or {}
    meta.update({
        "symbol": SYMBOL,
        "probe_earliest_month": earliest_month.isoformat(),
        "probe_first_tick_seen": earliest_hit.isoformat(),
        "probe_run_at": utc_now().isoformat(),
    })
    write_json_atomic(metadata_path(), meta)
    return earliest_month


# ---------------------------------------------------------------------------
# Windows Task Scheduler helpers (daily automated fetch)
# ---------------------------------------------------------------------------

def install_daily_task(at_hhmm):
    if os.name != "nt":
        raise RuntimeError("--install-task is Windows-only.")
    python_exe = sys.executable
    script = os.path.abspath(__file__)
    tr = f'"{python_exe}" "{script}" --through-yesterday'
    cmd = [
        "schtasks", "/Create", "/TN", TASK_NAME,
        "/TR", tr, "/SC", "DAILY", "/ST", at_hhmm, "/F",
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(
        f"\nScheduled task '{TASK_NAME}' created: runs daily at {at_hhmm} (local time),\n"
        f"executing: {tr}\n"
        "It appends everything up to the previous UTC midnight into ./ask and ./bid.\n"
        "Note: the MT5 terminal must be installed, logged in, and able to start for the\n"
        "fetch to succeed (the task will launch it via the Python API)."
    )


def uninstall_daily_task():
    if os.name != "nt":
        raise RuntimeError("--uninstall-task is Windows-only.")
    subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], check=True)
    print(f"Scheduled task '{TASK_NAME}' removed.")


def main():
    parser = argparse.ArgumentParser(
        description="MT5 XAUUSD Bid/Ask tick archiver: incremental daily updates, "
                    "historical backfill, earliest-history probe, exact-range repair."
    )
    parser.add_argument("--update", action="store_true",
                        help="Fetch from last archived tick up to now.")
    parser.add_argument("--through-yesterday", action="store_true",
                        help="Fetch up to the previous UTC midnight (use for the daily job).")
    parser.add_argument("--daily", action="store_true",
                        help="Alias of --through-yesterday, with logging to _fetch_state/fetch.log.")
    parser.add_argument("--start", metavar="YYYY-MM-DD",
                        help="Override the archive start for a historical backfill "
                             "(e.g. the value reported by --probe-earliest).")
    parser.add_argument("--probe-earliest", action="store_true",
                        help="Discover how far back the broker will serve XAUUSD ticks.")
    parser.add_argument("--probe-floor", metavar="YYYY-MM-DD", default="2004-01-01",
                        help="Lower bound for --probe-earliest (default 2004-01-01).")
    parser.add_argument("--install-task", action="store_true",
                        help="Register a Windows daily Scheduled Task for the fetch.")
    parser.add_argument("--uninstall-task", action="store_true",
                        help="Remove the Windows daily Scheduled Task.")
    parser.add_argument("--at", metavar="HH:MM", default="06:30",
                        help="Local time for --install-task (default 06:30).")
    parser.add_argument("--repair-start", help="UTC ISO timestamp, e.g. 2021-04-12T23:57:59Z")
    parser.add_argument("--repair-end", help="UTC ISO timestamp, e.g. 2021-04-13T20:57:27Z")
    args = parser.parse_args()

    if bool(args.repair_start) != bool(args.repair_end):
        parser.error("--repair-start and --repair-end must be supplied together")

    # Task-scheduler management needs no MT5 connection.
    if args.install_task:
        install_daily_task(args.at)
        return
    if args.uninstall_task:
        uninstall_daily_task()
        return

    global ARCHIVE_START
    backfill_from = None
    if args.start:
        ARCHIVE_START = max(parse_date_arg(args.start), HARD_FLOOR)
        backfill_from = ARCHIVE_START
        print(f"Archive start overridden -> {fmt(ARCHIVE_START)}")

    initialize_mt5()
    try:
        if args.probe_earliest:
            probe_earliest(parse_date_arg(args.probe_floor))
        elif args.repair_start:
            repair_range(parse_utc(args.repair_start), parse_utc(args.repair_end))
        elif backfill_from is not None and not (args.through_yesterday or args.daily or args.update):
            # Historical backfill: fill gaps from --start forward without
            # touching / relying on the incremental state cursor.
            log_line(f"BACKFILL: {fmt(backfill_from)} -> now")
            res = download_period(backfill_from, utc_now(), update_state=False)
            if res["failed_ranges"]:
                for s, e in res["failed_ranges"]:
                    log_line(f"BACKFILL FAILED RANGE: {fmt(s)} -> {fmt(e)}")
                raise RuntimeError("Backfill had failed ranges (see log).")
            log_line(f"BACKFILL: done. new bid={res['bid_added']:,} ask={res['ask_added']:,}")
        elif args.through_yesterday or args.daily:
            log_line("DAILY: starting update through previous UTC midnight")
            res = update_through_previous_day()
            log_line(f"DAILY: done. new bid={res.get('bid_added', 0):,} "
                     f"ask={res.get('ask_added', 0):,} skipped={res.get('skipped', False)}")
        else:
            download_all()
    finally:
        mt5.shutdown()
        print("\nMT5 connection closed.")


if __name__ == "__main__":
    main()
