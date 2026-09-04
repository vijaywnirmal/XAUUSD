"""
Step 1 of M1 — build the MT5 -> UTC offset table.

The Vantage/MT5 tick archive is stamped in Vantage *server* time (GMT+2 in the
early years, GMT+2/+3 with summer DST later). For every MT5 month we find the
clock offset that best aligns its 1-minute log-returns with Dukascopy (true UTC),
by maximising correlation over a coarse grid then a fine grid, and snap to the
nearest 15 minutes.

Output: data_pipeline/mt5_utc_offsets.csv
    year, month, offset_min, corr, n_minutes, method, flag

`flag` is one of:
    ok            corr >= 0.95, snapped cleanly
    low_corr      best corr < 0.95 — offset taken from neighbouring months
    duka_source   month is served from Dukascopy anyway (offset irrelevant, set 0)
    no_overlap    Dukascopy month missing (should not happen post-backfill)

Run:  python -m data_pipeline.build_utc_offsets  [--workers N]
"""

import argparse
import csv
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from . import config as C
from . import common as K

COARSE = range(-360, 361, 30)     # minutes
FINE_HALF = 30                    # +/- around coarse best
FINE_STEP = 5
SNAP = 15                         # snap final offset to nearest N minutes
CORR_OK = 0.95
MIN_MINUTES = 500


def _corr_for(mt5_min_ret, duka_min_ret, shift):
    a = mt5_min_ret.copy()
    a.index = a.index + pd.Timedelta(minutes=shift)
    j = pd.concat([a.rename("v"), duka_min_ret.rename("d")], axis=1, join="inner").dropna()
    if len(j) < MIN_MINUTES:
        return np.nan, len(j)
    return j["v"].corr(j["d"]), len(j)


def _bars_logret(df, off_min, rule):
    t = df["time_msc"].to_numpy() + int(off_min) * 60_000
    s = pd.Series(df["mid"].to_numpy(), index=pd.to_datetime(t, unit="ms", utc=True))
    return np.log(s.resample(rule).last().dropna()).diff().dropna()


def detect_month(y, m):
    # Only skip months that are structurally Dukascopy (pre-Vantage or a known
    # hole). Quality-based Dukascopy overrides are DERIVED from this table, so we
    # must still measure them here.
    if (y, m) < C.MT5_START or (y, m) in C.DUKA_ONLY_MONTHS:
        return dict(year=y, month=m, offset_min=0, corr=1.0, q60=1.0, n_minutes=0,
                    method="n/a", flag="duka_source")

    mt5 = K.load_bidask(C.MT5_DIR, y, m)
    duka = K.load_bidask(C.DUKA_DIR, y, m)
    if mt5 is None or duka is None:
        return dict(year=y, month=m, offset_min="", corr="", q60="", n_minutes=0,
                    method="", flag="no_overlap")

    v = np.log(K.minute_last_mid(mt5, 0)).diff().dropna()
    d = np.log(K.minute_last_mid(duka, 0)).diff().dropna()

    grid = [(off, *_corr_for(v, d, -off)) for off in COARSE]      # shift MT5 by -off
    grid = [(o, c, n) for (o, c, n) in grid if not np.isnan(c)]
    if not grid:
        return dict(year=y, month=m, offset_min="", corr="", q60="", n_minutes=0,
                    method="grid", flag="no_overlap")
    o0 = max(grid, key=lambda t: t[1])[0]
    fine = [(off, *_corr_for(v, d, -off))
            for off in range(o0 - FINE_HALF, o0 + FINE_HALF + 1, FINE_STEP)]
    fine = [(o, c, n) for (o, c, n) in fine if not np.isnan(c)]
    off, corr, n = max(fine, key=lambda t: t[1])
    snapped = int(round(off / SNAP) * SNAP)

    # quality indicator: agreement at 60-min bars with the chosen offset
    dd = _bars_logret(duka, 0, "60min")
    vv = _bars_logret(mt5, -snapped, "60min")
    jj = pd.concat([vv.rename("v"), dd.rename("d")], axis=1, join="inner").dropna()
    q60 = round(float(jj["v"].corr(jj["d"])), 4) if len(jj) > 100 else np.nan

    if corr >= CORR_OK:
        flag = "ok"
    elif not np.isnan(q60) and q60 >= 0.90:
        flag = "ok_coarse"          # 1-min noisy but hourly agrees -> offset trustworthy
    else:
        flag = "low_quality"        # feed genuinely diverges -> prefer Dukascopy here
    return dict(year=y, month=m, offset_min=snapped, corr=round(float(corr), 4),
                q60=q60, n_minutes=int(n), method=f"grid+fine snap{SNAP}", flag=flag)


def _fill_from_neighbours(rows):
    """For low_quality / low_corr months, borrow the offset from the nearest
    confidently-detected month (ok or ok_coarse)."""
    good = {(r["year"], r["month"]): r["offset_min"]
            for r in rows if r["flag"] in ("ok", "ok_coarse") and r["offset_min"] != ""}
    if not good:
        return rows
    keys = sorted(good)
    for r in rows:
        if r["flag"] not in ("low_quality", "low_corr") or r["offset_min"] == "":
            continue
        tgt = r["year"] * 12 + r["month"]
        nearest = min(keys, key=lambda k: abs((k[0] * 12 + k[1]) - tgt))
        if r["offset_min"] != good[nearest]:
            r["method"] += f" offset<-{nearest[0]}-{nearest[1]:02d}({good[nearest]})"
            r["offset_min"] = good[nearest]
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    months = K.list_months(C.MT5_DIR, "bid")
    print(f"MT5 months: {len(months)}  ({months[0]} .. {months[-1]})", flush=True)

    rows = []
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for r in ex.map(_detect_star, months):
                rows.append(r)
                print(f"  {r['year']}-{r['month']:02d}: off={r.get('offset_min')} "
                      f"corr={r.get('corr')} q60={r.get('q60')} {r['flag']}", flush=True)
    else:
        for (y, m) in months:
            r = _detect_star((y, m))
            rows.append(r)
            print(f"  {y}-{m:02d}: off={r.get('offset_min')} corr={r.get('corr')} "
                  f"q60={r.get('q60')} {r['flag']}", flush=True)

    rows.sort(key=lambda r: (r["year"], r["month"]))
    rows = _fill_from_neighbours(rows)

    os.makedirs(C.PIPE_DIR, exist_ok=True)
    with open(C.OFFSETS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["year", "month", "offset_min", "corr", "q60",
                                          "n_minutes", "method", "flag"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    fl = Counter(r["flag"] for r in rows)
    dist = Counter(r["offset_min"] for r in rows if r["flag"] in ("ok", "ok_coarse"))
    bad = [f"{r['year']}-{r['month']:02d}" for r in rows if r["flag"] == "low_quality"]
    print(f"\nwrote {C.OFFSETS_CSV}")
    print(f"  flags: {dict(fl)}")
    print(f"  offset distribution (min): {dict(sorted(dist.items()))}")
    if bad:
        print(f"  LOW-QUALITY MT5 months (consider Dukascopy override): {bad}")


def _detect_star(ym):
    try:
        return detect_month(*ym)
    except Exception as exc:
        import traceback
        return dict(year=ym[0], month=ym[1], offset_min="", corr="", q60="",
                    n_minutes=0, method="", flag="error:" + repr(exc)[:120],
                    _tb=traceback.format_exc()[-500:])


if __name__ == "__main__":
    main()
