"""Cross-asset bar access: parquet (training, from monitor.fetch_crossasset)
and MT5 (live)."""
from __future__ import annotations

import os

import pandas as pd

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _utc(t):
    if t is None:
        return None
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def training_xa(start=None, end=None) -> dict:
    """{"EURUSD": df, "USDJPY": df} from monitor/data/*_m5.parquet, sliced."""
    lo, hi = _utc(start), _utc(end)
    out = {}
    for sym in ("EURUSD", "USDJPY"):
        p = os.path.join(_DATA, f"{sym}_m5.parquet")
        if not os.path.exists(p):
            continue
        d = pd.read_parquet(p)
        d.index = pd.to_datetime(d.index, utc=True)
        if lo is not None:
            d = d[d.index >= lo]
        if hi is not None:
            d = d[d.index < hi]
        out[sym] = d.rename(columns={d.columns[0]: "close"}) if "close" not in d else d
    return out


def live_xa(mt5, n: int = 200) -> dict:
    """Recent M5 bars for the cross-asset instruments the MT5 account has."""
    out = {}
    for sym in ("EURUSD", "USDJPY", "BTCUSD"):
        try:
            if not mt5.symbol_select(sym, True):
                continue
            r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 1, n)
            if r is None or len(r) == 0:
                continue
            df = pd.DataFrame(r)
            df["ts"] = pd.to_datetime(df["time"], unit="s", utc=True)
            out[sym] = df.set_index("ts")[["close"]]
        except Exception:
            continue
    return out
