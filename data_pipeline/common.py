"""Shared helpers for the data pipeline."""

import os
import glob
import re
import numpy as np
import pandas as pd

from . import config as C


def list_months(dir_tmpl, side="bid"):
    """Sorted [(year, month), ...] present on disk for a source."""
    out = []
    for f in glob.glob(os.path.join(dir_tmpl.format(side=side), "year=*", "month=*", "ticks.parquet")):
        p = f.replace("\\", "/")
        y = int(re.search(r"year=(\d+)", p).group(1))
        m = int(re.search(r"month=(\d+)", p).group(1))
        out.append((y, m))
    return sorted(set(out))


def load_side(dir_tmpl, side, y, m, cols=("time_msc", "price")):
    path = C.month_path(dir_tmpl, side, y, m)
    if not os.path.exists(path):
        return None
    return pd.read_parquet(path, columns=list(cols))


def load_bidask(dir_tmpl, y, m):
    """Merged tick frame for a month: time_msc, bid, ask, mid, spread.
    As-of merge (nearest, 2s tolerance) to pair the two one-sided streams."""
    b = load_side(dir_tmpl, "bid", y, m)
    a = load_side(dir_tmpl, "ask", y, m)
    if b is None or a is None or len(b) == 0 or len(a) == 0:
        return None
    b = b.rename(columns={"price": "bid"}).sort_values("time_msc")
    a = a.rename(columns={"price": "ask"}).sort_values("time_msc")
    df = pd.merge_asof(b, a, on="time_msc", direction="nearest", tolerance=2000).dropna(subset=["bid", "ask"])
    df["mid"] = (df["bid"] + df["ask"]) / 2.0
    df["spread"] = df["ask"] - df["bid"]
    return df.reset_index(drop=True)


def minute_last_mid(df, offset_min=0):
    """Series of last mid per UTC minute; `offset_min` is ADDED to the clock
    (use to shift MT5 server-time onto UTC)."""
    t = df["time_msc"].to_numpy() + int(offset_min) * 60_000
    minute = t // 60_000
    s = pd.Series(df["mid"].to_numpy(), index=minute).groupby(level=0).last()
    s.index = pd.to_datetime(s.index.values * 60_000, unit="ms", utc=True)
    return s


def month_iter(start_ym, end_ym):
    y, m = start_ym
    while (y, m) <= end_ym:
        yield (y, m)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def next_month(y, m):
    return (y + 1, 1) if m == 12 else (y, m + 1)
