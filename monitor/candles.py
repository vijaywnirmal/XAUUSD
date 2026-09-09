"""
Candlestick-pattern recognition on the last few completed M5 bars.

Covers the common named patterns from classic technical analysis. These are
DETECTED for context / completeness - none has been separately validated on
gold in this project, and the project's classic-indicator screen, SMC and
support/resistance tests all came back with no tradeable edge. So every result
carries that caveat; treat a firing pattern as "worth a glance", nothing more.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_CTX = ("classic reversal/continuation lore; not validated on gold here - "
        "context only, no demonstrated edge")


def _b(o, c):        # body, signed
    return c - o


def evaluate(df: pd.DataFrame) -> list[dict]:
    """df: OHLC bars (>=5 completed). Returns firing candlestick patterns on the
    LAST completed bar (df.iloc[-1])."""
    df = df.sort_values("ts").reset_index(drop=True)
    if len(df) < 5:
        return []
    o = df["open"].to_numpy(float); h = df["high"].to_numpy(float)
    l = df["low"].to_numpy(float); c = df["close"].to_numpy(float)
    rng = np.maximum(h - l, 1e-9)
    body = np.abs(c - o)
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - l
    atr = pd.Series(rng).rolling(14, min_periods=3).mean().to_numpy()
    i = len(df) - 1
    up_prior = c[i - 1] > c[i - 4]                  # short prior trend, for reversal context
    dn_prior = c[i - 1] < c[i - 4]
    out = []

    def add(name, fire, direction, extra=""):
        if fire:
            out.append({"name": name, "direction": int(direction), "note": _CTX, "detail": extra})

    small = body[i] < 0.3 * rng[i]
    tiny = body[i] < 0.1 * rng[i]
    bull = c[i] > o[i]
    bear = c[i] < o[i]

    # --- single bar ---
    add("doji", tiny and rng[i] > 0.4 * atr[i], 0, "open≈close - indecision")
    add("hammer", small and lower[i] > 2 * body[i] and upper[i] < body[i] and dn_prior, +1,
        "long lower wick after a dip")
    add("hanging_man", small and lower[i] > 2 * body[i] and upper[i] < body[i] and up_prior, -1,
        "long lower wick after a rally")
    add("shooting_star", small and upper[i] > 2 * body[i] and lower[i] < body[i] and up_prior, -1,
        "long upper wick after a rally")
    add("inverted_hammer", small and upper[i] > 2 * body[i] and lower[i] < body[i] and dn_prior, +1,
        "long upper wick after a dip")
    add("marubozu_bull", bull and upper[i] < 0.05 * rng[i] and lower[i] < 0.05 * rng[i] and body[i] > atr[i], +1,
        "full-body up bar, no wicks")
    add("marubozu_bear", bear and upper[i] < 0.05 * rng[i] and lower[i] < 0.05 * rng[i] and body[i] > atr[i], -1,
        "full-body down bar, no wicks")

    # --- two bar ---
    pbody = body[i - 1]
    add("bullish_engulfing",
        (c[i - 1] < o[i - 1] and bull and c[i] >= o[i - 1] and o[i] <= c[i - 1] and body[i] > pbody),
        +1, "up bar swallows the prior down bar")
    add("bearish_engulfing",
        (c[i - 1] > o[i - 1] and bear and o[i] >= c[i - 1] and c[i] <= o[i - 1] and body[i] > pbody),
        -1, "down bar swallows the prior up bar")
    add("bullish_harami",
        (c[i - 1] < o[i - 1] and bull and max(o[i], c[i]) < o[i - 1] and min(o[i], c[i]) > c[i - 1]),
        +1, "small up bar inside the prior down bar")
    add("bearish_harami",
        (c[i - 1] > o[i - 1] and bear and max(o[i], c[i]) < c[i - 1] and min(o[i], c[i]) > o[i - 1]),
        -1, "small down bar inside the prior up bar")
    add("piercing_line",
        (c[i - 1] < o[i - 1] and bull and o[i] < l[i - 1] and c[i] > (o[i - 1] + c[i - 1]) / 2 and c[i] < o[i - 1]),
        +1, "up bar closes above the midpoint of the prior down bar")
    add("dark_cloud_cover",
        (c[i - 1] > o[i - 1] and bear and o[i] > h[i - 1] and c[i] < (o[i - 1] + c[i - 1]) / 2 and c[i] > o[i - 1]),
        -1, "down bar closes below the midpoint of the prior up bar")
    add("inside_bar", h[i] < h[i - 1] and l[i] > l[i - 1], 0, "range fully inside the prior bar")
    add("outside_bar", h[i] > h[i - 1] and l[i] < l[i - 1], np.sign(_b(o[i], c[i])),
        "range engulfs the prior bar")

    # --- three bar ---
    add("morning_star",
        (c[i - 2] < o[i - 2] and body[i - 2] > atr[i] * 0.6 and body[i - 1] < 0.4 * rng[i - 1]
         and bull and c[i] > (o[i - 2] + c[i - 2]) / 2),
        +1, "big down, small gap, big up")
    add("evening_star",
        (c[i - 2] > o[i - 2] and body[i - 2] > atr[i] * 0.6 and body[i - 1] < 0.4 * rng[i - 1]
         and bear and c[i] < (o[i - 2] + c[i - 2]) / 2),
        -1, "big up, small gap, big down")
    add("three_white_soldiers",
        all(c[i - k] > o[i - k] for k in range(3)) and c[i] > c[i - 1] > c[i - 2]
        and all(body[i - k] > 0.5 * rng[i - k] for k in range(3)),
        +1, "three strong up bars in a row")
    add("three_black_crows",
        all(c[i - k] < o[i - k] for k in range(3)) and c[i] < c[i - 1] < c[i - 2]
        and all(body[i - k] > 0.5 * rng[i - k] for k in range(3)),
        -1, "three strong down bars in a row")
    return out


def net_lean(cands: list[dict]) -> int:
    return int(sum(c["direction"] for c in cands))
