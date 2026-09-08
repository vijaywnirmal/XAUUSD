"""
Transparent pattern layer: each rule is one the project has actually studied.
`evaluate(df)` returns which are firing right now, their suggested direction,
and a one-line note on what the backtest said about that rule (so a firing
signal is never shown without its track record).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# what the research established about each rule (net, at retail cost)
NOTES = {
    "ema5_detach": "5-EMA fade: strongest raw directional signal in the project "
                   "(t~2.7 vs null) but net -$0.17/trade - sub-cost.",
    "ny_orb": "NY opening-range breakout (H1): gross +$0.39/trade, net ~breakeven "
              "at $0.30 spread. Marginal.",
    "london_agree": "H1 break that AGREES with the London 07:00-13:00 drift: "
                    "+$0.05/trade in-sample vs -$0.21 when it disagrees. Unvalidated OOS.",
    "range_extreme": "Price at a 24h extreme - fading it was a coin flip (H11 t~0.06). "
                     "Context only.",
    "trend_pullback": "Dip in an up-trend / rally in a down-trend. Every trend filter "
                      "added in this project hurt (H1b, H5-forensics). Context only.",
    "rsi_extreme": "RSI <30 / >70. Classic-indicator screen: no edge after cost.",
}


def evaluate(df: pd.DataFrame) -> list[dict]:
    df = df.sort_values("ts").reset_index(drop=True)
    if len(df) < 60:
        return []
    c = df["close"]
    ema5 = c.ewm(span=5, adjust=False).mean()
    ema20 = c.ewm(span=20, adjust=False).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()
    last, prev = df.iloc[-1], df.iloc[-2]
    ts = pd.DatetimeIndex(df["ts"])
    mod = ts[-1].hour * 60 + ts[-1].minute
    out = []

    def add(name, firing, direction, extra=""):
        out.append({"name": name, "firing": bool(firing),
                    "direction": int(direction), "note": NOTES.get(name, ""), "detail": extra})

    # 5-EMA detach on the last completed candle -> fade
    e5 = ema5.iloc[-1]
    above = last.low > e5
    below = last.high < e5
    add("ema5_detach", above or below, -1 if above else (1 if below else 0),
        "candle fully above EMA5" if above else ("candle fully below EMA5" if below else ""))

    # NY opening-range box + break (13:30-14:00 box, break 14:00-18:00)
    day = ts.floor("D")[-1]
    todays = df[ts.floor("D") == day]
    tmod = pd.DatetimeIndex(todays["ts"]).hour * 60 + pd.DatetimeIndex(todays["ts"]).minute
    box = todays[(tmod >= 810) & (tmod < 840)]
    orb_dir, orb_fire, orb_detail = 0, False, ""
    if len(box) >= 5 and 840 <= mod < 1080:
        bh, bl = box["high"].max(), box["low"].min()
        brk = todays[(tmod >= 840)]
        broke_up = (brk["high"] >= bh).any()
        broke_dn = (brk["low"] <= bl).any()
        first_up = brk.index[brk["high"] >= bh].min() if broke_up else np.inf
        first_dn = brk.index[brk["low"] <= bl].min() if broke_dn else np.inf
        if broke_up or broke_dn:
            orb_fire = True
            orb_dir = 1 if first_up < first_dn else -1
            orb_detail = f"box {bl:.2f}-{bh:.2f}, broke {'up' if orb_dir > 0 else 'down'}"
        # london-agree
        lon = todays[(tmod >= 420) & (tmod < 780)]
        if len(lon) and orb_fire:
            ld = np.sign(lon["close"].iloc[-1] - lon["close"].iloc[0])
            add("london_agree", ld == orb_dir and ld != 0, orb_dir,
                f"London drift {'up' if ld > 0 else 'down' if ld < 0 else 'flat'}, break {'up' if orb_dir>0 else 'down'}")
    add("ny_orb", orb_fire, orb_dir, orb_detail)

    # 24h range extreme
    hi = df["high"].tail(288).max()
    lo = df["low"].tail(288).min()
    pos = (c.iloc[-1] - lo) / (hi - lo) if hi > lo else 0.5
    add("range_extreme", pos > 0.97 or pos < 0.03, -1 if pos > 0.97 else (1 if pos < 0.03 else 0),
        f"range position {pos:.2f}")

    # trend + pullback
    trend = np.sign(ema20.iloc[-1] - ema50.iloc[-1])
    gap = (c.iloc[-1] - ema20.iloc[-1])
    pull = (trend > 0 and gap < 0) or (trend < 0 and gap > 0)
    add("trend_pullback", bool(pull and trend != 0), int(trend),
        f"trend {'up' if trend>0 else 'down'}, price {'below' if gap<0 else 'above'} EMA20")

    # RSI extreme
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    rv = float(rsi.iloc[-1])
    add("rsi_extreme", rv < 30 or rv > 70, 1 if rv < 30 else (-1 if rv > 70 else 0), f"RSI {rv:.0f}")

    return out


def net_lean(patterns: list[dict]) -> int:
    """Sum of firing pattern directions, weighted toward the ones with a real
    (if sub-cost) signal. Just a tally for display - not a trade signal."""
    w = {"ema5_detach": 2, "ny_orb": 2, "london_agree": 2, "range_extreme": 1,
         "trend_pullback": 1, "rsi_extreme": 1}
    return sum(w.get(p["name"], 1) * p["direction"] for p in patterns if p["firing"])
