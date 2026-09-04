"""
Dukascopy XAU/USD tick archiver.

Pulls tick history from Dukascopy (via the `dukascopy-python` package) and stores
it in the SAME on-disk layout / schema as the MT5 archive so downstream tooling
is uniform:

    ./dukascopy/bid/year=YYYY/month=MM/ticks.parquet
    ./dukascopy/ask/year=YYYY/month=MM/ticks.parquet

Schema per file: time_msc (int64 ms, UTC), time (UTC timestamp),
                 price (float64), volume (float64), flags (int32, always 0)

  bid file: price = bidPrice, volume = bidVolume
  ask file: price = askPrice, volume = askVolume

Dukascopy volume is a relative figure (millions of units); unlike the MT5 feed
it is non-zero and usable as an activity proxy.

Modes:
  --start 2009-01-01 --end 2026-09-03   full/backfill range (resumable, per-day)
  --month 2020-02                        a single month (use for gap patches)
  --daily                               append yesterday (UTC) forward
  --patch-mt5-feb2020                   fetch 2020-02 and also drop it into the
                                        MT5 archive (./bid, ./ask) to fill the hole

State/log: ./_fetch_state/dukascopy_state.json , ./_fetch_state/dukascopy.log
"""

import os
import sys
import json
import time
import glob
import random
import socket
import argparse
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FutTimeout
from datetime import datetime, timezone, timedelta

import logging

# Dukascopy occasionally stalls a connection instead of refusing it (soft
# rate-limit). Without a socket timeout a worker hangs forever and the whole
# pool wedges. This makes any stalled socket raise -> caught -> retried.
socket.setdefaulttimeout(45)

import pandas as pd
import dukascopy_python as dk
import dukascopy_python.instruments as dki

# The library logs an INFO line per hourly .bi5 file; quiet all INFO chatter.
logging.disable(logging.INFO)
for _n in ("DUKASCRIPT", "dukascopy_python", "dukascopy"):
    logging.getLogger(_n).setLevel(logging.WARNING)


INSTRUMENT = dki.INSTRUMENT_FX_METALS_XAU_USD  # "XAU/USD"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DUKA_ROOT = os.path.join(PROJECT_ROOT, "dukascopy")
MT5_ROOT = PROJECT_ROOT  # MT5 archive lives at ./bid , ./ask
STATE_DIR = os.path.join(PROJECT_ROOT, "_fetch_state")

DEFAULT_START = datetime(2009, 1, 1, tzinfo=timezone.utc)
HARD_FLOOR = datetime(2003, 1, 1, tzinfo=timezone.utc)

# --- rate-limit / robustness knobs -----------------------------------------
DAY_RETRIES = 6              # attempts per day
DAY_RETRY_BASE = 8.0         # backoff: BASE * 2**(n-1) + jitter  -> 8,16,32,64,128s
DAY_RETRY_MAX = 180.0
DAY_TIMEOUT = 240.0          # hard ceiling for one day-fetch (via the process pool)
INTER_MONTH_SLEEP = 3.0      # pause between months, be polite to Dukascopy
FETCH_LIMIT = 150_000        # rows per internal page
WORKERS = 3                  # concurrent day-fetches (Dukascopy throttles >~4)
SOCKET_TIMEOUT = 45          # kept in sync with socket.setdefaulttimeout above


def utc_now():
    return datetime.now(timezone.utc)


def fmt(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ensure_utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def log_line(msg):
    line = f"[{utc_now().strftime('%Y-%m-%d %H:%M:%S')} UTC] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "dukascopy.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def state_path():
    return os.path.join(STATE_DIR, "dukascopy_state.json")


def read_state():
    try:
        with open(state_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_state(**kw):
    os.makedirs(STATE_DIR, exist_ok=True)
    data = read_state()
    data.update(kw)
    data["updated_at"] = utc_now().isoformat()
    tmp = state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, state_path())


def month_file(root, side, y, m):
    return os.path.join(root, side, f"year={y}", f"month={m:02d}", "ticks.parquet")


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_day(day):
    """Return the raw Dukascopy tick frame for one UTC calendar day.

    Returns a DataFrame on success, None for a genuinely empty day (weekend),
    and the sentinel string "FAILED" if every retry was exhausted so the caller
    can distinguish "no data" from "give up / retry later".
    """
    socket.setdefaulttimeout(SOCKET_TIMEOUT)  # re-assert inside spawned workers
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    last_err = None
    for attempt in range(1, DAY_RETRIES + 1):
        try:
            df = dk.fetch(INSTRUMENT, dk.INTERVAL_TICK, dk.OFFER_SIDE_BID,
                          start, end, limit=FETCH_LIMIT)
            if df is None or df.empty:
                return None
            return df
        except Exception as exc:  # network / server hiccup / soft throttle
            last_err = exc
            if attempt < DAY_RETRIES:
                back = min(DAY_RETRY_BASE * (2 ** (attempt - 1)), DAY_RETRY_MAX)
                time.sleep(back + random.uniform(0, back * 0.25))
    log_line(f"  WARN {day.date()}: fetch failed after {DAY_RETRIES} tries: {last_err}")
    return "FAILED"


def to_side_frames(raw):
    """Split a raw Dukascopy frame into MT5-schema bid / ask frames."""
    df = raw.copy()
    t = pd.to_datetime(df.index, utc=True).as_unit("ns")  # force ns resolution
    time_msc = (t.asi8 // 1_000_000).astype("int64")      # ns -> ms since epoch (UTC)
    t = t.as_unit("ms")                                   # match MT5 archive's ms timestamps

    def build(price_col, vol_col):
        out = pd.DataFrame({
            "time_msc": time_msc,
            "time": t,
            "price": df[price_col].astype("float64").values,
            "volume": df[vol_col].astype("float64").values,
            "flags": 0,
        })
        out["flags"] = out["flags"].astype("int32")
        out = out[out["price"] > 0]
        return out.reset_index(drop=True)

    return build("bidPrice", "bidVolume"), build("askPrice", "askVolume")


def write_month(root, side, y, m, frame):
    if frame.empty:
        return 0
    path = month_file(root, side, y, m)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        existing = pd.read_parquet(path)
        before = len(existing)
        combined = pd.concat([existing, frame], ignore_index=True)
    else:
        before = 0
        combined = frame
    combined = (
        combined.drop_duplicates(subset=["time_msc", "price", "volume", "flags"])
        .sort_values("time_msc")
        .reset_index(drop=True)
    )
    tmp = path + ".tmp"
    combined.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    return max(len(combined) - before, 0)


def iter_days(start, end):
    d = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end = ensure_utc(end)
    while d < end:
        yield d
        d += timedelta(days=1)


def _months_between(start, end):
    y, m = start.year, start.month
    out = []
    while (y, m) <= (end.year, end.month) and datetime(y, m, 1, tzinfo=timezone.utc) < end:
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


class _Pool:
    """ProcessPoolExecutor wrapper that runs day-fetches with a HARD per-day
    timeout and transparently recycles the pool if a worker wedges (Dukascopy
    can stall a socket past the socket timeout under heavy throttling)."""

    def __init__(self, workers):
        self.workers = max(1, workers)
        self.ex = None
        self._spawn()

    def _spawn(self):
        if self.ex is not None:
            self.ex.shutdown(wait=False, cancel_futures=True)
        self.ex = ProcessPoolExecutor(max_workers=self.workers) if self.workers > 1 else None

    def run_days(self, days):
        """Return list aligned with `days`: DataFrame | None | 'FAILED'."""
        if self.ex is None:
            return [fetch_day(d) for d in days]
        results = [None] * len(days)
        futs = {self.ex.submit(fetch_day, d): i for i, d in enumerate(days)}
        wedged = False
        for fut, i in list(futs.items()):
            try:
                results[i] = fut.result(timeout=DAY_TIMEOUT)
            except FutTimeout:
                results[i] = "FAILED"
                wedged = True
            except Exception as exc:
                log_line(f"  WARN {days[i].date()}: worker error {type(exc).__name__}: {exc}")
                results[i] = "FAILED"
        if wedged:
            log_line("  pool wedged on a day-timeout -> recycling worker pool")
            self._spawn()
        return results

    def close(self):
        if self.ex is not None:
            self.ex.shutdown(wait=False, cancel_futures=True)


def download_range(start, end, *, root=DUKA_ROOT, update_state=False, tag="RANGE",
                   workers=WORKERS, conform_mt5=False):
    start = max(ensure_utc(start), HARD_FLOOR)
    end = ensure_utc(end)
    log_line(f"{tag}: {fmt(start)} -> {fmt(end)}  root={os.path.relpath(root, PROJECT_ROOT)} "
             f"workers={workers} socket_timeout={SOCKET_TIMEOUT}s")

    tot_bid = tot_ask = 0
    pool = _Pool(workers)
    try:
      for (y, m) in _months_between(start, end):
        m_start = max(datetime(y, m, 1, tzinfo=timezone.utc), start)
        m_end = min(datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=timezone.utc), end)
        days = list(iter_days(m_start, m_end))

        raws = pool.run_days(days)
        # one extra pass for days that failed / timed out, after a cooldown
        failed_idx = [i for i, r in enumerate(raws) if isinstance(r, str)]
        if failed_idx:
            log_line(f"  {y}-{m:02d}: {len(failed_idx)} day(s) failed; cooldown 30s then retry once")
            time.sleep(30)
            retry = pool.run_days([days[i] for i in failed_idx])
            for j, i in enumerate(failed_idx):
                raws[i] = retry[j]

        still_failed = [days[i].date() for i, r in enumerate(raws) if isinstance(r, str)]
        buf_bid, buf_ask = [], []
        for r in raws:
            if r is None or isinstance(r, str):
                continue
            bid_f, ask_f = to_side_frames(r)
            if conform_mt5:
                bid_f["volume"] = 0
                ask_f["volume"] = 0
            buf_bid.append(bid_f)
            buf_ask.append(ask_f)

        if buf_bid:
            b = write_month(root, "bid", y, m, pd.concat(buf_bid, ignore_index=True))
            a = write_month(root, "ask", y, m, pd.concat(buf_ask, ignore_index=True))
            tot_bid += b
            tot_ask += a
            msg = f"  {y}-{m:02d}: +{b:,} bid / +{a:,} ask"
        else:
            msg = f"  {y}-{m:02d}: no data"
        if still_failed:
            msg += f"  [!! unrecovered days: {', '.join(str(d) for d in still_failed)}]"
        log_line(msg)

        # Only advance the resume cursor if the month is COMPLETE.
        if update_state and not still_failed:
            write_state(last_completed_month=f"{y}-{m:02d}")
        elif update_state and still_failed:
            write_state(last_incomplete_month=f"{y}-{m:02d}",
                        last_incomplete_days=[str(d) for d in still_failed])

        time.sleep(INTER_MONTH_SLEEP)
    finally:
        pool.close()

    log_line(f"{tag} DONE: +{tot_bid:,} bid / +{tot_ask:,} ask ticks")
    return tot_bid, tot_ask


# ---------------------------------------------------------------------------
# MT5-archive helpers (for the Feb-2020 patch)
# ---------------------------------------------------------------------------

def mt5_latest_tick():
    newest = None
    for side in ("bid", "ask"):
        files = glob.glob(os.path.join(MT5_ROOT, side, "year=*", "month=*", "ticks.parquet"))
        for f in files:
            try:
                c = pd.read_parquet(f, columns=["time_msc"])
                if len(c):
                    ts = datetime.fromtimestamp(int(c["time_msc"].max()) / 1000, tz=timezone.utc)
                    newest = ts if newest is None or ts > newest else newest
            except Exception:
                pass
    return newest


def patch_mt5_month(y, m, workers=WORKERS):
    """Fetch one month from Dukascopy and write it into the MT5 archive tree,
    conforming to the MT5 schema (volume 0, flags 0). Source noted in state."""
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    end = datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=timezone.utc)
    log_line(f"PATCH MT5 {y}-{m:02d}: writing Dukascopy ticks into ./bid , ./ask ...")

    tot_b, tot_a = download_range(start, end, root=MT5_ROOT, update_state=False,
                                  tag=f"PATCH MT5 {y}-{m:02d}", workers=workers,
                                  conform_mt5=True)

    write_state(**{
        f"mt5_patch_{y}-{m:02d}": {
            "source": "dukascopy",
            "bid_ticks": tot_b,
            "ask_ticks": tot_a,
            "patched_at": utc_now().isoformat(),
        }
    })
    log_line(f"PATCH MT5 {y}-{m:02d} DONE: +{tot_b:,} bid / +{tot_a:,} ask "
             f"(also mirrored into ./dukascopy/ by --month)")
    return tot_b, tot_a


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_month(s):
    return datetime.strptime(s, "%Y-%m").replace(tzinfo=timezone.utc)


def parse_date(s):
    s = s.strip().replace("Z", "+00:00")
    try:
        return ensure_utc(datetime.fromisoformat(s))
    except ValueError:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _next_month(dt):
    return datetime(dt.year + (dt.month // 12), (dt.month % 12) + 1, 1, tzinfo=timezone.utc)


def acquire_lock():
    """Prevent two backfills from stacking on the same archive (that stall was
    partly caused by a --resume launched on top of a still-running backfill)."""
    os.makedirs(STATE_DIR, exist_ok=True)
    lock = os.path.join(STATE_DIR, "dukascopy.lock")
    if os.path.exists(lock):
        try:
            info = json.load(open(lock))
        except Exception:
            info = {}
        age = time.time() - os.path.getmtime(lock)
        raise SystemExit(
            f"Another run holds {lock} (pid {info.get('pid')}, started "
            f"{info.get('started')}, {age/60:.0f} min ago).\n"
            f"If you are sure it is dead: delete that file and re-run."
        )
    with open(lock, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "started": utc_now().isoformat()}, f)
    return lock


def main():
    p = argparse.ArgumentParser(description="Dukascopy XAU/USD tick archiver")
    p.add_argument("--start", type=parse_date, help="range start (YYYY-MM-DD)")
    p.add_argument("--end", type=parse_date, help="range end exclusive (YYYY-MM-DD); default now")
    p.add_argument("--month", type=parse_month, help="fetch a single month YYYY-MM into ./dukascopy/")
    p.add_argument("--resume", action="store_true",
                   help="continue a --start/--end backfill from dukascopy_state.json")
    p.add_argument("--daily", action="store_true", help="append from last state to yesterday (UTC)")
    p.add_argument("--patch-mt5", type=parse_month, metavar="YYYY-MM",
                   help="fetch this month into BOTH ./dukascopy/ and the MT5 archive "
                        "(./bid, ./ask) to fill a hole. Default 2020-02 if flag given bare.")
    p.add_argument("--patch-mt5-feb2020", action="store_true",
                   help="shortcut for --patch-mt5 2020-02")
    p.add_argument("--workers", type=int, default=WORKERS,
                   help=f"concurrent day-fetches (default {WORKERS})")
    args = p.parse_args()

    patch_target = args.patch_mt5
    if args.patch_mt5_feb2020 and not patch_target:
        patch_target = datetime(2020, 2, 1, tzinfo=timezone.utc)
    if patch_target:
        y, m = patch_target.year, patch_target.month
        nxt = datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=timezone.utc)
        download_range(patch_target, nxt, root=DUKA_ROOT, update_state=False,
                       tag=f"DUKA {y}-{m:02d}", workers=args.workers)
        patch_mt5_month(y, m, workers=args.workers)
        return

    if args.month:
        y, m = args.month.year, args.month.month
        nxt = datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=timezone.utc)
        download_range(args.month, nxt, root=DUKA_ROOT, update_state=False,
                       tag=f"DUKA {y}-{m:02d}", workers=args.workers)
        return

    if args.daily:
        st = read_state()
        lc = st.get("last_completed_month")
        start = (parse_month(lc) if lc else DEFAULT_START)
        end = datetime(*utc_now().timetuple()[:3], tzinfo=timezone.utc)  # today 00:00 UTC
        download_range(start, end, root=DUKA_ROOT, update_state=True, tag="DUKA DAILY",
                       workers=args.workers)
        return

    start = args.start or DEFAULT_START
    if args.resume:
        st = read_state()
        lc = st.get("last_completed_month")
        inc = st.get("last_incomplete_month")
        if inc:                       # redo the month that had unrecovered days
            start = parse_month(inc)
            log_line(f"RESUME: redoing incomplete month {inc}")
        elif lc:
            start = _next_month(parse_month(lc))
            log_line(f"RESUME: from {start:%Y-%m} (last complete {lc})")
    end = args.end or datetime(*utc_now().timetuple()[:3], tzinfo=timezone.utc)

    lock = acquire_lock()
    try:
        download_range(start, end, root=DUKA_ROOT, update_state=True, tag="DUKA BACKFILL",
                       workers=args.workers)
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


if __name__ == "__main__":
    main()
