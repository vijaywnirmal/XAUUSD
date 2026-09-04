"""
Performance metrics + the Section-6 success-bar table + Monte-Carlo on trade order.
Everything derives from a Backtester.run() result {"trades", "equity"}.
"""

import numpy as np
import pandas as pd

# Section-6 thresholds (blueprint). Cross-run checks (OOS degradation, parameter
# plateau) are noted but not computed from a single run.
SUCCESS_BAR = {
    "max_drawdown_pct":      ("<=", 20.0),
    "max_dd_duration_days":  ("<=", 95.0),      # ~3 months
    "profit_factor":         (">=", 1.25),
    "sharpe":                (">=", 1.0),
    "sortino":               (">=", 1.5),
    "expectancy_usd":        (">",  0.0),
    "n_trades":              (">=", 300),       # in-sample
}

def _drawdown(equity: pd.Series):
    peak = equity.cummax()
    dd = equity / peak - 1.0
    max_dd = float(-dd.min() * 100)
    below = (equity < peak).to_numpy()
    if not below.any():
        return max_dd, 0.0
    idx = equity.index
    longest = cur_start = None
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


def compute_metrics(res: dict, timeframe: str = "5min", periods_per_year: float | None = None) -> dict:
    tr = res["trades"]
    eq = res["equity"].astype(float)
    cfg = res["config"]

    # Sharpe / Sortino from DAILY equity (robust to long flat stretches between trades)
    daily = eq.resample("1D").last().dropna()
    dret = daily.pct_change().dropna()
    ann = np.sqrt(periods_per_year or 252)
    sharpe = float(dret.mean() / dret.std() * ann) if dret.std() > 0 else 0.0
    dn = dret[dret < 0].std()
    sortino = float(dret.mean() / dn * ann) if dn and dn > 0 else 0.0
    max_dd, dd_days = _drawdown(eq)

    n = len(tr)
    out = {
        "n_trades": n,
        "start": str(eq.index[0]), "end": str(eq.index[-1]),
        "initial_equity": cfg.initial_equity,
        "final_equity": float(eq.iloc[-1]),
        "total_return_pct": float((eq.iloc[-1] / cfg.initial_equity - 1) * 100),
        "max_drawdown_pct": max_dd,
        "max_dd_duration_days": dd_days,
        "sharpe": sharpe,
        "sortino": sortino,
    }
    if n:
        wins = tr[tr.net_pnl > 0].net_pnl
        losses = tr[tr.net_pnl <= 0].net_pnl
        gross_win = float(wins.sum())
        gross_loss = float(-losses.sum())
        out.update({
            "win_rate": float(len(wins) / n * 100),
            "expectancy_usd": float(tr.net_pnl.mean()),
            "expectancy_r": float(tr.r_multiple.mean(skipna=True)) if tr.r_multiple.notna().any() else float("nan"),
            "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
            "avg_win_usd": float(wins.mean()) if len(wins) else 0.0,
            "avg_loss_usd": float(losses.mean()) if len(losses) else 0.0,
            "avg_bars_held": float(tr.bars_held.mean()),
            "total_cost_usd": float(tr.cost.sum()),
            "gross_pnl_usd": float(tr.gross_pnl.sum()),
            "net_pnl_usd": float(tr.net_pnl.sum()),
            "cost_drag_pct_of_gross": float(tr.cost.sum() / abs(tr.gross_pnl.sum()) * 100)
                if tr.gross_pnl.sum() != 0 else float("nan"),
            "exit_reason_mix": tr.exit_reason.value_counts().to_dict(),
        })
    else:
        out.update({"win_rate": 0, "expectancy_usd": 0, "profit_factor": 0})
    return out


def _cmp(op, val, thr):
    return {"<=": val <= thr, ">=": val >= thr, ">": val > thr, "<": val < thr}[op]


def success_bar(metrics: dict) -> pd.DataFrame:
    rows = []
    for key, (op, thr) in SUCCESS_BAR.items():
        val = metrics.get(key, float("nan"))
        ok = (not np.isnan(val)) and _cmp(op, val, thr) if isinstance(val, (int, float)) else False
        rows.append({"metric": key, "value": round(val, 4) if isinstance(val, (int, float)) else val,
                     "op": op, "threshold": thr, "pass": "PASS" if ok else "FAIL"})
    df = pd.DataFrame(rows)
    df.attrs["all_pass"] = bool((df["pass"] == "PASS").all())
    return df


def monte_carlo_trades(res: dict, n_iter: int = 2000, seed: int = 0) -> dict:
    """Resample the trade sequence (with replacement) and look at the spread of
    outcomes — robustness to trade ordering / a few lucky trades."""
    tr = res["trades"]
    cfg = res["config"]
    if len(tr) < 5:
        return {"note": "too few trades"}
    rng = np.random.default_rng(seed)
    pnl = tr.net_pnl.to_numpy()
    finals, maxdds = [], []
    for _ in range(n_iter):
        s = rng.choice(pnl, size=len(pnl), replace=True)
        eq = cfg.initial_equity + np.cumsum(s)
        finals.append(eq[-1])
        peak = np.maximum.accumulate(np.concatenate([[cfg.initial_equity], eq]))
        maxdds.append(float(-np.min(eq / peak[1:] - 1) * 100))
    finals = np.array(finals); maxdds = np.array(maxdds)
    return {
        "final_equity_p05": float(np.percentile(finals, 5)),
        "final_equity_p50": float(np.percentile(finals, 50)),
        "final_equity_p95": float(np.percentile(finals, 95)),
        "prob_profit": float((finals > cfg.initial_equity).mean()),
        "max_dd_pct_p50": float(np.percentile(maxdds, 50)),
        "max_dd_pct_p95": float(np.percentile(maxdds, 95)),
    }


def report(res: dict, timeframe="5min") -> str:
    m = compute_metrics(res, timeframe)
    sb = success_bar(m)
    mc = monte_carlo_trades(res)
    lines = ["=== metrics ==="]
    for k, v in m.items():
        lines.append(f"  {k:28s} {v}")
    lines.append("\n=== success bar ===")
    lines.append(sb.to_string(index=False))
    lines.append(f"\n  ALL PASS: {sb.attrs['all_pass']}")
    lines.append("\n=== monte carlo (trade-order resample) ===")
    for k, v in mc.items():
        lines.append(f"  {k:24s} {v}")
    return "\n".join(lines)
