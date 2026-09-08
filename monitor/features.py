"""
Market-state features from M5 bars (+ optional live tick). Pure, deterministic.
Every feature is knowable in real time (no lookahead). `compute(df, tick)` ->
dict of scalars; `feature_frame(df)` -> a DataFrame of the same features per bar,
for calibration.
"""
from __future__ import annotations

from datetime import timezone

import numpy as np
import pandas as pd

from monitor import config as C


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _atr(df: pd.DataFrame, n: int) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _session(mod: int) -> str:
    if 0 <= mod < 420:
        return "asia"
    if 420 <= mod < 780:
        return "london"
    if 780 <= mod < 840:
        return "ny_preopen"
    if 840 <= mod < 1260:
        return "ny"
    return "late"


def feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("ts").reset_index(drop=True)
    c = df["close"]
    ts = pd.DatetimeIndex(df["ts"])
    mod = ts.hour * 60 + ts.minute

    ema_f, ema_s, ema_t = _ema(c, C.EMA_FAST), _ema(c, C.EMA_SLOW), _ema(c, C.EMA_TREND)
    atr = _atr(df, C.ATR_N)
    bars_per_day = 288
    # rolling percentile rank of the current ATR within the trailing window
    atr_pct = atr.rolling(C.VOL_LOOKBACK_DAYS * bars_per_day, min_periods=bars_per_day).rank(pct=True)

    roll_hi = df["high"].rolling(C.RANGE_LOOKBACK_BARS, min_periods=20).max()
    roll_lo = df["low"].rolling(C.RANGE_LOOKBACK_BARS, min_periods=20).min()
    range_pos = (c - roll_lo) / (roll_hi - roll_lo).replace(0, np.nan)

    macd = _ema(c, 12) - _ema(c, 26)
    macd_sig = _ema(macd, 9)

    up = (c.diff() > 0).astype(int)
    streak = up.groupby((up != up.shift()).cumsum()).cumcount() + 1
    streak = np.where(c.diff() > 0, streak, np.where(c.diff() < 0, -streak, 0))

    day = ts.floor("D")
    # London drift (07:00-13:00 UTC) as of each bar, and the day's NY box
    lon_mask = (mod >= 420) & (mod < 780)
    lon_open = c.where(lon_mask).groupby(day).transform("first")
    lon_last = c.where(lon_mask & (mod < mod.max() + 1)).groupby(day).transform("last")
    box_mask = (mod >= 810) & (mod < 840)
    box_hi = df["high"].where(box_mask).groupby(day).transform("max")
    box_lo = df["low"].where(box_mask).groupby(day).transform("min")

    f = pd.DataFrame({"ts": df["ts"], "close": c, "mod": mod})
    f["ret_5m"] = c.pct_change(1)
    f["ret_15m"] = c.pct_change(3)
    f["ret_1h"] = c.pct_change(12)
    f["ret_1d"] = c.pct_change(288)
    f["ema_f_gap"] = (c - ema_f) / atr
    f["ema_s_gap"] = (c - ema_s) / atr
    f["trend"] = np.sign(ema_f - ema_s) + np.sign(ema_s - ema_t)      # -2..+2
    f["atr"] = atr
    f["atr_pct"] = atr_pct
    f["atr_norm"] = atr / c
    f["rsi"] = _rsi(c, C.RSI_N)
    f["macd_hist"] = (macd - macd_sig) / atr
    f["range_pos"] = range_pos
    f["streak"] = streak
    f["dist_hi_atr"] = (roll_hi - c) / atr
    f["dist_lo_atr"] = (c - roll_lo) / atr
    f["session"] = [_session(m) for m in mod]
    f["dow"] = ts.dayofweek
    f["london_drift_atr"] = (lon_last - lon_open) / atr
    f["ny_box_width_atr"] = (box_hi - box_lo) / atr
    f["ny_box_pos"] = (c - box_lo) / (box_hi - box_lo).replace(0, np.nan)
    return f


# columns fed to the direction model (numeric only)
MODEL_COLS = [
    "ret_15m", "ret_1h", "ret_1d", "ema_f_gap", "ema_s_gap", "trend",
    "atr_pct", "atr_norm", "rsi", "macd_hist", "range_pos", "streak",
    "dist_hi_atr", "dist_lo_atr", "london_drift_atr",
]


def compute(df: pd.DataFrame, tick=None) -> dict:
    f = feature_frame(df)
    row = f.iloc[-1].to_dict()
    if tick is not None:
        row["spread"] = round(getattr(tick, "spread", float("nan")), 4)
        row["price"] = round(getattr(tick, "mid", row["close"]), 3)
    row["ts"] = pd.Timestamp(row["ts"]).tz_convert(timezone.utc).isoformat()
    return {k: (None if isinstance(v, float) and (v != v) else v) for k, v in row.items()}
