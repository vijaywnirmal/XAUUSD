"""
Cross-verify the MT5 (Vantage) tick archive against the Dukascopy archive.

Important discovery: the MT5/Vantage archive timestamps are NOT UTC -- they are in
Vantage *server* time (empirically GMT+2 in the early years, GMT+2/+3 with summer
DST later). This script auto-detects the offset per month by maximising the
1-minute log-return correlation against Dukascopy (which IS true UTC), applies it,
then reports how closely the two feeds agree on price and how their spreads differ.

Usage:
    python verify_sources.py 2018-06 2020-03 2022-09 2025-06
    python verify_sources.py --all
    python verify_sources.py --all --csv SOURCE_VERIFICATION.csv
"""

import os
import glob
import argparse
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
MT5 = ROOT
DUKA = os.path.join(ROOT, "dukascopy")


def mfile(root, side, y, m):
    return os.path.join(root, side, f"year={y}", f"month={m:02d}", "ticks.parquet")


def have(root, y, m):
    return os.path.exists(mfile(root, "bid", y, m)) and os.path.exists(mfile(root, "ask", y, m))


def load_ticks(root, y, m):
    """Merged bid/ask tick frame: time_msc, bid, ask (as-of merge on time)."""
    bid = pd.read_parquet(mfile(root, "bid", y, m), columns=["time_msc", "price"]).rename(columns={"price": "bid"})
    ask = pd.read_parquet(mfile(root, "ask", y, m), columns=["time_msc", "price"]).rename(columns={"price": "ask"})
    bid = bid.sort_values("time_msc")
    ask = ask.sort_values("time_msc")
    df = pd.merge_asof(bid, ask, on="time_msc", direction="nearest", tolerance=2000).dropna()
    df["mid"] = (df["bid"] + df["ask"]) / 2
    df["spread"] = df["ask"] - df["bid"]
    return df


def minute_mid(df, offset_min=0):
    t = df["time_msc"].to_numpy() + offset_min * 60_000
    minute = t // 60_000
    g = pd.DataFrame({"minute": minute, "mid": df["mid"].to_numpy()})
    s = g.groupby("minute")["mid"].last()
    s.index = pd.to_datetime(s.index * 60_000, unit="ms", utc=True)
    return s


def detect_offset(v_df, d_df):
    """Return (offset_minutes, correlation) that best aligns MT5 -> true UTC.
    Coarse 30-min grid over +/-6h, then +/-15-min refine."""
    d_min = minute_mid(d_df, 0)
    rd = np.log(d_min).diff()

    def corr_at(off):
        v_min = minute_mid(v_df, off)
        rv = np.log(v_min).diff()
        j = pd.concat([rv.rename("v"), rd.rename("d")], axis=1, join="inner").dropna()
        return (j["v"].corr(j["d"]), len(j)) if len(j) > 500 else (-1.0, 0)

    # +off means MT5 clock runs `off` minutes AHEAD of UTC; we shift MT5 by -off.
    grid = [(off, *corr_at(-off)) for off in range(-360, 361, 30)]
    off0 = max(grid, key=lambda t: t[1])[0]
    fine = [(off, *corr_at(-off)) for off in range(off0 - 30, off0 + 31, 5)]
    off, c, n = max(fine, key=lambda t: t[1])
    return off, c, n


def compare_month(y, m):
    v = load_ticks(MT5, y, m)
    d = load_ticks(DUKA, y, m)
    off, corr, n = detect_offset(v, d)

    # Align MT5 to UTC and re-pair at the minute for price comparison.
    vm = minute_mid(v, -off)
    dm = minute_mid(d, 0)
    j = pd.concat([vm.rename("mt5"), dm.rename("duka")], axis=1, join="inner").dropna()
    diff = j["mt5"] - j["duka"]
    bps = diff / j["duka"] * 1e4
    rv = np.log(j["mt5"]).diff()
    rd = np.log(j["duka"]).diff()

    # Spread: median instantaneous spread per source (tick level, robust).
    return {
        "month": f"{y}-{m:02d}",
        "utc_offset_detected": f"{off:+d}m",
        "ret_corr_after_align": round(rv.corr(rd), 4),
        "minutes": len(j),
        "mt5_ticks_M": round(len(v) / 1e6, 2),
        "duka_ticks_M": round(len(d) / 1e6, 2),
        "px_diff_$_med": round(diff.median(), 3),
        "px_diff_$_mean": round(diff.mean(), 3),
        "px_diff_bps_med": round(bps.median(), 2),
        "px_absdiff_bps_p95": round(bps.abs().quantile(0.95), 2),
        "spread_$_med_MT5": round(v["spread"].median(), 3),
        "spread_$_med_DUKA": round(d["spread"].median(), 3),
        "spread_bps_med_MT5": round((v["spread"] / v["mid"] * 1e4).median(), 2),
        "spread_bps_med_DUKA": round((d["spread"] / d["mid"] * 1e4).median(), 2),
    }


def discover_common():
    out = []
    for f in glob.glob(os.path.join(DUKA, "bid", "year=*", "month=*", "ticks.parquet")):
        p = f.replace("\\", "/").split("/")
        y = int([s for s in p if s.startswith("year=")][0].split("=")[1])
        m = int([s for s in p if s.startswith("month=")][0].split("=")[1])
        if have(MT5, y, m) and have(DUKA, y, m):
            out.append((y, m))
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("months", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--csv")
    a = ap.parse_args()

    targets = discover_common() if a.all else [(int(x[:4]), int(x[5:7])) for x in a.months]
    if not targets:
        print("No targets. Pass YYYY-MM or --all (needs ./dukascopy data).")
        return

    rows = []
    for y, m in targets:
        if not (have(MT5, y, m) and have(DUKA, y, m)):
            print(f"{y}-{m:02d}: missing one source, skip")
            continue
        print(f"comparing {y}-{m:02d} ...", flush=True)
        rows.append(compare_month(y, m))

    tbl = pd.DataFrame(rows).set_index("month")
    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 40)
    print("\n=== MT5 (Vantage) vs Dukascopy ===")
    print(tbl.to_string())
    print("\n=== medians across months ===")
    for c in ["ret_corr_after_align", "px_diff_bps_med", "px_absdiff_bps_p95",
              "spread_bps_med_MT5", "spread_bps_med_DUKA"]:
        print(f"  {c:24s} {tbl[c].median()}")
    if a.csv:
        tbl.to_csv(a.csv)
        print(f"\nwrote {a.csv}")


if __name__ == "__main__":
    main()
