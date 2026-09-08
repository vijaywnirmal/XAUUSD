"""
Visual strategy builder: compiles a user-composed rule set (indicator
comparisons, AND/OR, plus a bracket: stop/target/trail/session-flat/max-hold)
into a signals dict, then runs it through the same Backtester. New code —
no existing equivalent in the repo; reuses webapp/backend/indicators.py and
backtest/engine.py without modifying either.

Rule shape:
    {"left": {"kind": "indicator"|"price", "id": "rsi", "params": {"n": 14},
               "output": "rsi", "field": "close"},
     "op": ">"|"<"|">="|"<="|"=="|"cross_above"|"cross_below",
     "right": {"kind": "value"|"indicator"|"price", "value": 30, ...}}
"""
import numpy as np
import pandas as pd

from backtest.engine import Backtester, BTConfig
from webapp.backend.indicators import compute_indicator


def _series_for(operand: dict, df: pd.DataFrame, cache: dict) -> pd.Series:
    kind = operand.get("kind", "value")
    if kind == "value":
        return pd.Series(float(operand["value"]), index=df.index)
    if kind == "price":
        return df[operand.get("field", "close")]
    if kind == "indicator":
        key = (operand["id"], tuple(sorted((operand.get("params") or {}).items())))
        if key not in cache:
            cache[key] = compute_indicator(df, operand["id"], operand.get("params") or {})
        out_name = operand.get("output") or next(iter(cache[key]))
        return cache[key][out_name]
    raise ValueError(f"unknown operand kind {kind}")


def _eval_rule(rule: dict, df: pd.DataFrame, cache: dict) -> np.ndarray:
    left = _series_for(rule["left"], df, cache)
    right = _series_for(rule["right"], df, cache)
    op = rule["op"]
    if op == ">":
        out = left > right
    elif op == "<":
        out = left < right
    elif op == ">=":
        out = left >= right
    elif op == "<=":
        out = left <= right
    elif op == "==":
        out = (left - right).abs() < 1e-9
    elif op == "cross_above":
        out = (left > right) & (left.shift(1) <= right.shift(1))
    elif op == "cross_below":
        out = (left < right) & (left.shift(1) >= right.shift(1))
    else:
        raise ValueError(f"unknown op {op}")
    return out.fillna(False).to_numpy()


def _eval_group(rules: list, logic: str, df: pd.DataFrame, cache: dict) -> np.ndarray:
    if not rules:
        return np.zeros(len(df), bool)
    masks = [_eval_rule(r, df, cache) for r in rules]
    if logic == "OR":
        out = masks[0]
        for m in masks[1:]:
            out = out | m
        return out
    out = masks[0]
    for m in masks[1:]:
        out = out & m
    return out


def compute_signals(df: pd.DataFrame, spec: dict):
    """Shared by compile_and_run (feeds the Backtester) and preview (feeds the
    confirm-before-running chart) — one evaluation path, so the preview always
    matches exactly what the actual run will do.
    Returns (long_entry, short_entry, exit_signal, indicator_cache)."""
    cache = {}
    long_rules = spec.get("long_rules") or []
    short_rules = spec.get("short_rules") or []
    exit_rules = spec.get("exit_rules") or []

    le = _eval_group(long_rules, spec.get("long_logic", "AND"), df, cache)
    se = _eval_group(short_rules, spec.get("short_logic", "AND"), df, cache)
    xs = _eval_group(exit_rules, spec.get("exit_logic", "AND"), df, cache) if exit_rules else np.zeros(len(df), bool)

    # Entry time-of-day window (UTC hours): start inclusive, end exclusive.
    # start > end means a window that wraps midnight (e.g. 22 -> 6). Only
    # gates ENTRIES — an open trade still exits normally / at session-flat.
    win = _entry_window_mask(df, spec)
    if win is not None:
        le = le & win
        se = se & win
    return le, se, xs, cache


def _entry_window_mask(df: pd.DataFrame, spec: dict):
    start = spec.get("entry_start_hour_utc")
    end = spec.get("entry_end_hour_utc")
    if start is None and end is None:
        return None
    hours = pd.DatetimeIndex(df["ts"]).hour.to_numpy()
    lo = 0 if start is None else int(start)
    hi = 24 if end is None else int(end)
    if lo <= hi:
        return (hours >= lo) & (hours < hi)
    return (hours >= lo) | (hours < hi)   # wraps midnight


def preview(df: pd.DataFrame, spec: dict) -> dict:
    """Evaluate the spec's rules WITHOUT running the Backtester — just the
    indicator series and where long/short entries would fire — so the UI can
    plot it for the user to sanity-check before committing to a full run."""
    le, se, xs, cache = compute_signals(df, spec)
    indicator_series = {}
    for (iid, params_key), outputs in cache.items():
        params_label = ",".join(f"{k}={v}" for k, v in params_key) if params_key else ""
        for out_name, series in outputs.items():
            label = f"{iid}({params_label}).{out_name}" if params_label else f"{iid}.{out_name}"
            indicator_series[label] = series
    return {
        "long_entry": le,
        "short_entry": se,
        "indicator_series": indicator_series,
    }


def _bracket_dist(bracket: dict, prefix: str, df: pd.DataFrame, cache: dict):
    """Resolve a bracket distance (stop or target) that's either a fixed $
    amount or a multiple of an indicator (e.g. `n`x ATR(14)) — same per-bar
    array either way, so the rest of the engine doesn't care which. `prefix`
    is "stop" or "target"; looks at bracket["{prefix}_mode"] ("fixed"|"atr"),
    bracket["{prefix}_dist"] (fixed $), bracket["{prefix}_atr_mult"] and
    bracket["{prefix}_atr_n"] (ATR mode)."""
    mode = bracket.get(f"{prefix}_mode", "fixed")
    if mode == "atr":
        mult = bracket.get(f"{prefix}_atr_mult")
        if mult is None:
            return None
        n = int(bracket.get(f"{prefix}_atr_n") or 14)
        key = ("atr", (("n", n),))
        if key not in cache:
            cache[key] = compute_indicator(df, "atr", {"n": n})
        return (cache[key]["atr"] * float(mult)).to_numpy()
    v = bracket.get(f"{prefix}_dist")
    return np.full(len(df), float(v)) if v is not None else None


def compile_and_run(df: pd.DataFrame, spec: dict) -> dict:
    """spec: {long_rules, long_logic, short_rules, short_logic, exit_rules,
              exit_logic, bracket: {...}, bt: {...}} -> Backtester.run() result."""
    le, se, xs, cache = compute_signals(df, spec)
    n = len(df)
    sig = {"long_entry": le, "short_entry": se, "exit_signal": xs}

    bracket = spec.get("bracket") or {}
    stop_arr = _bracket_dist(bracket, "stop", df, cache)
    if stop_arr is not None:
        sig["stop_dist"] = stop_arr
    target_arr = _bracket_dist(bracket, "target", df, cache)
    if target_arr is not None:
        sig["target_dist"] = target_arr
    if bracket.get("trail_dist") is not None:
        sig["trail_dist"] = np.full(n, float(bracket["trail_dist"]))

    bt = spec.get("bt") or {}
    cfg_kwargs = dict(
        allow_short=bt.get("allow_short", True),
        reverse_on_opposite=bt.get("reverse_on_opposite", True),
        session_flat_hour_utc=bracket.get("session_flat_hour_utc"),
        one_trade_per_day=bt.get("one_trade_per_day", False),
        max_hold_bars=bracket.get("max_hold_bars"),
        trail_activate_r=bracket.get("trail_activate_r"),
        trail_ref=bracket.get("trail_ref", "close"),
        size_mode=bt.get("size_mode", "fixed"),
        size_lots=bt.get("size_lots", 0.01),
        risk_pct=bt.get("risk_pct", 0.005),
        initial_equity=bt.get("initial_equity", 1000.0),
        slippage_ticks=bt.get("slippage_ticks", 1.0),
    )
    cfg = BTConfig(**cfg_kwargs)
    return Backtester(cfg).run(df, sig)
