"""
Frozen-split data accessor. Everything downstream (research, backtests) loads
bars through here so the in-sample / walk-forward / out-of-sample boundaries are
enforced in one place.

    from data_pipeline.dataset import load_bars, SPLITS
    df = load_bars("5min", split="in_sample")

The out-of-sample slice is TOUCH-ONCE: load_bars(..., split="out_of_sample")
raises unless allow_oos=True is passed explicitly.
"""

import glob
import os
import warnings

import pandas as pd

from . import config as C

SPLITS = C.SPLITS


def _year_files(tf):
    return sorted(glob.glob(os.path.join(C.BARS_DIR, tf, "year=*", "bars.parquet")))


def load_bars(tf="1min", split=None, start=None, end=None, allow_oos=False, columns=None):
    if tf not in C.BAR_TIMEFRAMES:
        raise ValueError(f"tf must be one of {C.BAR_TIMEFRAMES}")
    if split == "out_of_sample" and not allow_oos:
        raise RuntimeError(
            "out_of_sample is touch-once. Pass allow_oos=True only for the single "
            "final validation run, and record that you did."
        )

    files = _year_files(tf)
    if not files:
        raise FileNotFoundError(f"no bars for {tf} — run build_bars")
    df = pd.concat((pd.read_parquet(f, columns=columns) for f in files), ignore_index=True)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").reset_index(drop=True)

    if split:
        lo, hi = C.SPLITS[split]
        df = df[(df["ts"] >= lo) & (df["ts"] < hi)]
    if start is not None:
        df = df[df["ts"] >= pd.Timestamp(start, tz="UTC")]
    if end is not None:
        df = df[df["ts"] < pd.Timestamp(end, tz="UTC")]

    return df.reset_index(drop=True)


def split_of(ts):
    return C.split_of(pd.Timestamp(ts, tz="UTC"))


def describe_splits():
    for tf in C.BAR_TIMEFRAMES:
        try:
            all_df = load_bars(tf, allow_oos=True, columns=["ts"])
        except FileNotFoundError:
            print(f"{tf}: not built")
            continue
        line = [f"{tf}:"]
        for name, (lo, hi) in C.SPLITS.items():
            n = ((all_df["ts"] >= lo) & (all_df["ts"] < hi)).sum()
            line.append(f"{name}={n:,}")
        print("  ".join(line))
