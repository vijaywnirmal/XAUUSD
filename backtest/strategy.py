"""
Strategy interface + validation / demo strategies.

A strategy is any callable `fn(df) -> signals dict` where df has the bar columns
and signals has equal-length arrays: long_entry, short_entry, exit_signal, and
optionally stop_dist / target_dist (price units). All decisions on bar t are
acted on at bar t+1 by the engine, so a strategy may use df up to and including
row t when producing signals[t] (no shift needed here — the engine does it).
"""

import numpy as np
import pandas as pd


def buy_and_hold(df):
    n = len(df)
    le = np.zeros(n, bool); le[0] = True
    return {"long_entry": le, "short_entry": np.zeros(n, bool),
            "exit_signal": np.zeros(n, bool)}


def random_entries(df, p=0.02, hold=12, allow_short=True, seed=0):
    """Random long/short entries, flat after `hold` bars (engine max_hold_bars
    can also do this; here we emit explicit exits). Expectancy should be ~ -cost."""
    rng = np.random.default_rng(seed)
    n = len(df)
    fire = rng.random(n) < p
    side = rng.choice([1, -1] if allow_short else [1], size=n)
    le = fire & (side == 1)
    se = fire & (side == -1)
    return {"long_entry": le, "short_entry": se, "exit_signal": np.zeros(n, bool)}


def always_flip(df, hold=1):
    """Alternate long/short every `hold` bars — pure cost sink, PF must be < 1."""
    n = len(df)
    le = np.zeros(n, bool); se = np.zeros(n, bool)
    k = 0
    for i in range(0, n, hold):
        (le if k % 2 == 0 else se)[i] = True
        k += 1
    return {"long_entry": le, "short_entry": se, "exit_signal": np.zeros(n, bool)}


def sma_trend(df, fast=20, slow=100, stop_atr=2.0, target_atr=3.0, atr_win=50):
    """Demo (NOT a validated edge): long when fast SMA > slow SMA, short when
    below; ATR-based stop/target. Just exercises the full engine path."""
    c = df["close"]
    f = c.rolling(fast).mean()
    s = c.rolling(slow).mean()
    tr = (df["high"] - df["low"]).abs()
    atr = tr.rolling(atr_win).mean()

    up = (f > s) & (f.shift() <= s.shift())
    dn = (f < s) & (f.shift() >= s.shift())
    le = up.fillna(False).to_numpy()
    se = dn.fillna(False).to_numpy()
    return {
        "long_entry": le, "short_entry": se, "exit_signal": np.zeros(len(df), bool),
        "stop_dist": (atr * stop_atr).to_numpy(),
        "target_dist": (atr * target_atr).to_numpy(),
    }


REGISTRY = {
    "buy_and_hold": buy_and_hold,
    "random": random_entries,
    "always_flip": always_flip,
    "sma_trend": sma_trend,
}
