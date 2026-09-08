"""
Orchestrates one backtest run: load_bars -> strategy/builder -> Backtester.run
-> compute_metrics/success_bar/monte_carlo_trades -> JSON-safe result package.

Runs are cached in-memory by run_id (local single-user tool, no DB).
"""
import uuid
from typing import Optional

import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from backtest.engine import Backtester, BTConfig
from backtest.metrics import compute_metrics, success_bar, monte_carlo_trades, SUCCESS_BAR

from webapp.backend.registry import STRATEGY_REGISTRY
from webapp.backend.indicators import compute_indicator
from webapp.backend.jsonsafe import safe
from webapp.backend import builder

RUN_CACHE: dict[str, dict] = {}

BAR_COLUMNS = ["ts", "open", "high", "low", "close", "spread_mean", "volume_sum"]
MAX_CHART_BARS = 5000
OVERRIDABLE_CFG_FIELDS = ("size_mode", "size_lots", "risk_pct", "initial_equity", "slippage_ticks")


def _downsample_ohlc(df: pd.DataFrame, max_bars=MAX_CHART_BARS):
    n = len(df)
    if n <= max_bars:
        return df
    step = int(np.ceil(n / max_bars))
    g = df.groupby(np.arange(n) // step)
    out = g.agg(ts=("ts", "first"), open=("open", "first"), high=("high", "max"),
               low=("low", "min"), close=("close", "last"))
    return out.reset_index(drop=True)


def _downsample_series(s: pd.Series, max_points=MAX_CHART_BARS):
    n = len(s)
    if n <= max_points:
        return s
    step = int(np.ceil(n / max_points))
    return s.iloc[::step]


def _equity_drawdown(equity: pd.Series):
    """Same drawdown definition as backtest.metrics._drawdown, generic over any
    equity series (fractional-return-based or absolute-dollar)."""
    if len(equity) < 2:
        return 0.0, 0.0
    peak = equity.cummax()
    dd = equity / peak - 1.0
    max_dd = float(-dd.min() * 100)
    below = (equity < peak).to_numpy()
    idx = equity.index
    cur_start = None
    best = 0.0
    for k, b in enumerate(below):
        if b and cur_start is None:
            cur_start = idx[k]
        elif not b and cur_start is not None:
            best = max(best, (idx[k] - cur_start).total_seconds() / 86400)
            cur_start = None
    if cur_start is not None:
        best = max(best, (idx[-1] - cur_start).total_seconds() / 86400)
    return max_dd, float(best)


def _daily_metrics(extra: dict, equity: pd.Series, initial_equity: float):
    final_eq = float(equity.iloc[-1]) if len(equity) else initial_equity
    start_eq = float(equity.iloc[0]) if len(equity) else initial_equity
    max_dd_pct, dd_days = _equity_drawdown(equity)
    if "total_return" in extra:
        total_ret_pct = float(extra["total_return"]) * 100
    elif start_eq:
        total_ret_pct = (final_eq / start_eq - 1) * 100
    else:
        total_ret_pct = None
    m = {
        "n_trades": "N/A",
        "profit_factor": extra.get("profit_factor", "N/A"),
        "win_rate": extra.get("win_rate", "N/A"),
        "expectancy_usd": "N/A",
        "initial_equity": initial_equity if "initial_equity_note" not in extra else "N/A (see notes)",
        "final_equity": final_eq,
        "total_return_pct": total_ret_pct,
        "max_drawdown_pct": float(extra["max_dd"]) * 100 if "max_dd" in extra else max_dd_pct,
        "max_dd_duration_days": float(extra.get("dd_days", dd_days)),
        "sharpe": float(extra["sharpe"]) if "sharpe" in extra else None,
        "sortino": float(extra["sortino"]) if "sortino" in extra else None,
        "cagr_pct": float(extra.get("cagr", 0.0) * 100) if "cagr" in extra else None,
    }
    return m


def _daily_success_bar(metrics: dict):
    rows = []
    for key, (op, thr) in SUCCESS_BAR.items():
        val = metrics.get(key)
        if not isinstance(val, (int, float)):
            rows.append({"metric": key, "value": "N/A", "op": op, "threshold": thr, "pass": "N/A"})
            continue
        ok = {"<=": val <= thr, ">=": val >= thr, ">": val > thr, "<": val < thr}[op]
        rows.append({"metric": key, "value": round(val, 4), "op": op, "threshold": thr,
                     "pass": "PASS" if ok else "FAIL"})
    return rows


def list_strategies():
    out = []
    for s in STRATEGY_REGISTRY.values():
        out.append({
            "id": s.id, "name": s.name, "category": s.category, "timeframe": s.timeframe,
            "description": s.description, "notes": s.notes,
            "params": [vars(p) for p in s.params],
        })
    return out


def get_bars(strategy_timeframe: str = "5min", split: Optional[str] = "in_sample",
            start: Optional[str] = None, end: Optional[str] = None,
            indicators: Optional[list] = None):
    df = load_bars(strategy_timeframe, split=split, start=start, end=end, columns=BAR_COLUMNS)
    ind_out = {}
    if indicators:
        for spec in indicators:
            iid = spec["id"]
            vals = compute_indicator(df, iid, spec.get("params", {}))
            for name, series in vals.items():
                ind_out[name] = series
    disp = _downsample_ohlc(df)
    result = {
        "bars": [{"ts": safe(r.ts), "open": safe(r.open), "high": safe(r.high),
                  "low": safe(r.low), "close": safe(r.close)} for r in disp.itertuples()],
        "indicators": {},
    }
    if indicators:
        n = len(df)
        step = int(np.ceil(n / MAX_CHART_BARS)) if n > MAX_CHART_BARS else 1
        idx = list(range(0, n, step))
        result["indicators"] = {
            name: [None if pd.isna(vals.iloc[i]) else float(vals.iloc[i]) for i in idx]
            for name, vals in ind_out.items()
        }
    return result


def get_builder_preview(spec: dict, timeframe: str = "5min", split: Optional[str] = "in_sample",
                        start: Optional[str] = None, end: Optional[str] = None) -> dict:
    """Evaluate a strategy-builder spec's rules over real data WITHOUT running
    the Backtester, so the UI can plot price + the referenced indicators +
    where long/short would fire, for the user to sanity-check before running.
    Uses the exact same rule-evaluation path (builder.compute_signals) the
    real run uses, so what's previewed is what will actually happen."""
    df = load_bars(timeframe, split=split, start=start, end=end, columns=BAR_COLUMNS)
    prev = builder.preview(df, spec)
    n = len(df)
    step = int(np.ceil(n / MAX_CHART_BARS)) if n > MAX_CHART_BARS else 1
    idx = list(range(0, n, step))

    ohlc = [{"ts": safe(df["ts"].iloc[i]), "open": safe(df["open"].iloc[i]), "high": safe(df["high"].iloc[i]),
             "low": safe(df["low"].iloc[i]), "close": safe(df["close"].iloc[i])} for i in idx]
    indicators = {
        name: [None if pd.isna(s.iloc[i]) else float(s.iloc[i]) for i in idx]
        for name, s in prev["indicator_series"].items()
    }
    le, se = prev["long_entry"], prev["short_entry"]
    long_idx = np.where(le)[0][:1000]
    short_idx = np.where(se)[0][:1000]
    return {
        "ohlc": ohlc,
        "indicators": indicators,
        "long_markers": [safe(df["ts"].iloc[i]) for i in long_idx],
        "short_markers": [safe(df["ts"].iloc[i]) for i in short_idx],
        "n_bars": n,
        "n_long_signals": int(le.sum()),
        "n_short_signals": int(se.sum()),
    }


def get_run_detail(run_id: str, days: int = 30) -> dict:
    """Full-resolution candles for a bounded window (default: first `days`
    calendar days of the run's data) plus the trades whose entry falls in
    that window, each with its stop/target price level — for a real
    candlestick chart with entry/exit/SL/TP markers, since the main result's
    `ohlc` is downsampled for the overview equity/close-line charts and can't
    show individual candles or trade brackets."""
    result = get_run(run_id)
    if result is None:
        raise KeyError(f"run '{run_id}' not found (in-memory cache — was the server restarted?)")
    if result["category"] == "daily-portfolio":
        raise ValueError("no discrete trades to chart for a daily-portfolio strategy")

    rc = result.get("run_config") or {}
    tf = rc.get("timeframe") or "5min"
    split = rc.get("split", "in_sample")
    df = load_bars(tf, split=split, start=rc.get("start"), end=rc.get("end"),
                   allow_oos=rc.get("allow_oos", False), columns=BAR_COLUMNS)
    if len(df) == 0:
        raise ValueError("no bars for this run's window")

    window_start = df["ts"].iloc[0]
    window_end = window_start + pd.Timedelta(days=days)
    window_df = df[df["ts"] < window_end]

    candles = [
        {"time": int(r.ts.timestamp()), "open": safe(r.open), "high": safe(r.high),
         "low": safe(r.low), "close": safe(r.close)}
        for r in window_df.itertuples()
    ]
    window_trades = [
        t for t in (result.get("trades") or [])
        if t.get("entry_ts") and window_start.isoformat() <= t["entry_ts"] < window_end.isoformat()
    ]
    return {
        "candles": candles,
        "trades": window_trades,
        "window_start": safe(window_start),
        "window_end": safe(window_end),
        "n_candles": len(candles),
        "n_trades_in_window": len(window_trades),
    }


def _build_intraday_result(strategy_id: str, params: dict, run_config: dict):
    spec = STRATEGY_REGISTRY[strategy_id]
    tf = run_config.get("timeframe") or spec.timeframe
    split = run_config.get("split", "in_sample")
    start = run_config.get("start")
    end = run_config.get("end")
    allow_oos = run_config.get("allow_oos", False)

    df = load_bars(tf, split=split, start=start, end=end, allow_oos=allow_oos, columns=BAR_COLUMNS)
    df_used, sig = spec.signal_fn(df, **params)

    cfg_kwargs = spec.bt_defaults(params) if spec.bt_defaults else {}
    for f in OVERRIDABLE_CFG_FIELDS:
        if run_config.get(f) is not None:
            cfg_kwargs[f] = run_config[f]
    cfg = BTConfig(**cfg_kwargs)

    res = Backtester(cfg).run(df_used, sig)
    metrics = compute_metrics(res, tf)
    sb = success_bar(metrics)
    mc = monte_carlo_trades(res)

    trades = res["trades"]
    eq = res["equity"]
    disp_eq = _downsample_series(eq)

    return {
        "category": "intraday",
        "strategy": {"id": spec.id, "name": spec.name},
        "params": params, "run_config": run_config,
        "metrics": safe(metrics),
        "success_bar": safe(sb.to_dict(orient="records")),
        "success_bar_all_pass": bool(sb.attrs.get("all_pass", False)),
        "monte_carlo": safe(mc),
        "n_bars": len(df_used),
        "trades": safe(trades.to_dict(orient="records")) if len(trades) else [],
        "equity": [{"ts": safe(t), "equity": safe(v)} for t, v in zip(disp_eq.index, disp_eq.values)],
        "ohlc": [{"ts": safe(r.ts), "open": safe(r.open), "high": safe(r.high),
                  "low": safe(r.low), "close": safe(r.close)}
                 for r in _downsample_ohlc(df_used[["ts", "open", "high", "low", "close"]]).itertuples()],
    }


def _build_daily_result(strategy_id: str, params: dict, run_config: dict):
    spec = STRATEGY_REGISTRY[strategy_id]
    split = run_config.get("split", "in_sample")
    start = run_config.get("start")
    end = run_config.get("end")
    initial_equity = run_config.get("initial_equity") or 1000.0

    out = spec.daily_fn(params, split, start, end, initial_equity)
    equity_usd = out["equity"].dropna()
    metrics = _daily_metrics(out["extra"], equity_usd, initial_equity)
    sb_rows = _daily_success_bar(metrics)

    disp_eq = _downsample_series(equity_usd)
    return {
        "category": "daily-portfolio",
        "strategy": {"id": spec.id, "name": spec.name},
        "params": params, "run_config": run_config,
        "metrics": safe(metrics),
        "success_bar": sb_rows,
        "success_bar_all_pass": False,
        "monte_carlo": {"note": "N/A for daily-portfolio hypotheses (no discrete trade list)"},
        "n_bars": len(equity_usd),
        "trades": [],
        "equity": [{"ts": safe(t), "equity": safe(v)} for t, v in zip(disp_eq.index, disp_eq.values)],
        "ohlc": [],
        "extra": safe(out["extra"]),
    }


def run_backtest(strategy_id: str, params: dict, run_config: dict) -> dict:
    if strategy_id not in STRATEGY_REGISTRY:
        raise KeyError(f"unknown strategy '{strategy_id}'")
    spec = STRATEGY_REGISTRY[strategy_id]
    params = {k: v for k, v in (params or {}).items() if v is not None}
    run_config = run_config or {}

    if spec.category == "daily-portfolio":
        result = _build_daily_result(strategy_id, params, run_config)
    else:
        result = _build_intraday_result(strategy_id, params, run_config)

    run_id = str(uuid.uuid4())
    result["run_id"] = run_id
    RUN_CACHE[run_id] = result
    return result


def get_run(run_id: str) -> Optional[dict]:
    return RUN_CACHE.get(run_id)
