"""
Step 2 of M1 — build the canonical, true-UTC, cleaned tick store.

For every month 2009-01 .. present:
  * pick the authoritative source (Vantage MT5, else Dukascopy) per config.source_for_month
  * if MT5: shift timestamps by that month's offset from mt5_utc_offsets.csv  -> true UTC
  * clean each side:  drop price<=MIN_PRICE, drop reverting single-tick spikes, dedupe, sort
  * pair bid/ask (as-of) and drop crossed / absurd-spread timestamps from BOTH sides
  * write ./canonical/{bid,ask}/year=/month=/ticks.parquet
        schema: time_msc int64(UTC ms), time datetime64[ms,UTC], price float64,
                volume float64, flags int32, source uint8   (0=mt5, 1=duka)

Per-month cleaning stats -> ./qa/clean_stats.csv

Run:  python -m data_pipeline.build_canonical  [--workers N] [--from YYYY-MM] [--to YYYY-MM]
"""

import argparse
import csv
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from . import config as C
from . import common as K

SRC_CODE = {"mt5": 0, "duka": 1}


def _load_offsets():
    if not os.path.exists(C.OFFSETS_CSV):
        raise SystemExit(f"missing {C.OFFSETS_CSV} — run build_utc_offsets first")
    off = {}
    with open(C.OFFSETS_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (int(r["year"]), int(r["month"]))
            off[key] = int(r["offset_min"]) if r["offset_min"] not in ("", None) else 0
    return off


def _despike_side(price, time_msc):
    """Remove single-tick jumps > MAX_ABS_LOG_RET_PER_TICK that revert within
    OUTLIER_REVERT_TICKS ticks. Returns a boolean keep-mask."""
    p = price.to_numpy(dtype="float64")
    n = len(p)
    keep = np.ones(n, dtype=bool)
    if n < 3:
        return keep
    lr = np.diff(np.log(np.clip(p, 1e-9, None)))
    susp = np.where(np.abs(lr) > C.MAX_ABS_LOG_RET_PER_TICK)[0] + 1  # index of the jumped tick
    for i in susp:
        lo = p[i - 1]
        hi_idx = min(i + C.OUTLIER_REVERT_TICKS, n - 1)
        # reverts if any of the next few ticks come back near the pre-jump level
        if np.min(np.abs(np.log(np.clip(p[i:hi_idx + 1], 1e-9, None)) - np.log(lo))) < C.MAX_ABS_LOG_RET_PER_TICK:
            keep[i] = False
    return keep


def _clean_side(df):
    """df: time_msc, price, volume, flags  -> cleaned, with stats dict."""
    n0 = len(df)
    df = df[df["price"] > C.MIN_PRICE]
    n_price = n0 - len(df)

    df = df.sort_values("time_msc", kind="stable")
    before = len(df)
    df = df.drop_duplicates(subset=["time_msc"], keep="last")
    n_dup = before - len(df)

    keep = _despike_side(df["price"], df["time_msc"])
    n_spike = int((~keep).sum())
    df = df.loc[keep].reset_index(drop=True)

    return df, dict(dropped_price=n_price, dropped_dup=n_dup, dropped_spike=n_spike)


def process_month(y, m, offsets):
    src = C.source_for_month(y, m)
    src_dir = C.MT5_DIR if src == "mt5" else C.DUKA_DIR
    shift_ms = offsets.get((y, m), 0) * 60_000 if src == "mt5" else 0

    out = {}
    stats = dict(year=y, month=m, source=src, offset_min=shift_ms // 60_000)
    per_side_clean = {}
    for side in C.SIDES:
        raw = K.load_side(src_dir, side, y, m, cols=("time_msc", "price", "volume", "flags"))
        if raw is None or len(raw) == 0:
            return dict(stats, error="missing_source_side_" + side)
        if shift_ms:
            raw = raw.copy()
            raw["time_msc"] = raw["time_msc"] + shift_ms
        cleaned, cs = _clean_side(raw)
        out[side] = cleaned
        per_side_clean[side] = cs

    # pair bid/ask, drop crossed / absurd-spread timestamps from both sides
    b = out["bid"][["time_msc", "price"]].rename(columns={"price": "bid"})
    a = out["ask"][["time_msc", "price"]].rename(columns={"price": "ask"})
    pair = pd.merge_asof(b.sort_values("time_msc"), a.sort_values("time_msc"),
                         on="time_msc", direction="nearest", tolerance=2000).dropna()
    spr = pair["ask"] - pair["bid"]
    med = float(np.median(spr[spr > 0])) if (spr > 0).any() else 0.0
    bad = pair["time_msc"][(spr < 0) | (med > 0) & (spr > C.MAX_SPREAD_MULT * med)]
    bad_set = set(bad.to_numpy().tolist())
    n_crossed = len(bad_set)
    if bad_set:
        for side in C.SIDES:
            out[side] = out[side][~out[side]["time_msc"].isin(bad_set)].reset_index(drop=True)

    # write
    for side in C.SIDES:
        d = out[side]
        d = d.assign(
            time=pd.to_datetime(d["time_msc"], unit="ms", utc=True).astype("datetime64[ms, UTC]"),
            volume=d["volume"].astype("float64"),
            flags=d["flags"].astype("int32"),
            source=np.uint8(SRC_CODE[src]),
        )[["time_msc", "time", "price", "volume", "flags", "source"]]
        path = C.month_path(C.CANON_DIR, side, y, m)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        d.to_parquet(tmp, index=False)
        os.replace(tmp, path)

    stats.update(
        bid_ticks=len(out["bid"]), ask_ticks=len(out["ask"]),
        med_spread=round(med, 4), dropped_crossed=n_crossed,
        **{f"bid_{k}": v for k, v in per_side_clean["bid"].items()},
        **{f"ask_{k}": v for k, v in per_side_clean["ask"].items()},
    )
    return stats


def _star(args):
    y, m, offsets = args
    try:
        return process_month(y, m, offsets)
    except Exception as exc:
        import traceback
        return dict(year=y, month=m, error=f"{type(exc).__name__}: {exc}",
                    tb=traceback.format_exc()[-800:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--from", dest="frm", default="2009-01")
    ap.add_argument("--to", dest="to", default=None)
    args = ap.parse_args()

    offsets = _load_offsets()
    duka_months = K.list_months(C.DUKA_DIR, "bid")
    mt5_months = set(K.list_months(C.MT5_DIR, "bid"))
    allm = sorted(set(duka_months) | mt5_months)
    frm = tuple(int(x) for x in args.frm.split("-"))
    to = tuple(int(x) for x in args.to.split("-")) if args.to else allm[-1]
    todo = [(y, m) for (y, m) in allm if frm <= (y, m) <= to]
    print(f"canonical build: {len(todo)} months  {todo[0]}..{todo[-1]}  workers={args.workers}", flush=True)

    os.makedirs(C.QA_DIR, exist_ok=True)
    rows = []
    payload = [(y, m, offsets) for (y, m) in todo]
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for r in ex.map(_star, payload):
                rows.append(r)
                tag = r.get("error", f"{r.get('bid_ticks',0):,}/{r.get('ask_ticks',0):,} "
                                     f"src={r.get('source')} off={r.get('offset_min')} "
                                     f"xed={r.get('dropped_crossed')}")
                print(f"  {r['year']}-{r['month']:02d}: {tag}", flush=True)
    else:
        for p in payload:
            r = _star(p)
            rows.append(r)
            print(f"  {r['year']}-{r['month']:02d}: {r.get('error', r.get('bid_ticks'))}", flush=True)

    cols = ["year", "month", "source", "offset_min", "bid_ticks", "ask_ticks",
            "med_spread", "dropped_crossed",
            "bid_dropped_price", "bid_dropped_dup", "bid_dropped_spike",
            "ask_dropped_price", "ask_dropped_dup", "ask_dropped_spike", "error"]
    with open(os.path.join(C.QA_DIR, "clean_stats.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    errs = [r for r in rows if r.get("error")]
    tot_b = sum(r.get("bid_ticks", 0) for r in rows)
    print(f"\ncanonical done: {len(rows)-len(errs)} ok, {len(errs)} errors, {tot_b:,} bid ticks total")
    for r in errs:
        print(f"  ERROR {r['year']}-{r['month']:02d}: {r['error']}")
    print(f"stats -> {os.path.join(C.QA_DIR, 'clean_stats.csv')}")


if __name__ == "__main__":
    main()
