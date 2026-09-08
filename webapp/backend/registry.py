"""
STRATEGY_REGISTRY: id -> StrategySpec.

Clean slate (reset on operator request) — every previously-registered
hypothesis (H1-H18, NFP straddle, H5-H8/H14 daily-portfolio sleeves) has been
removed along with the underlying research/*.py and research/*_RESULT.md
files, PROJECT_SUMMARY.md, and webapp/backend/ml/ (the meta-labeling layer).
`backtest/`, `data_pipeline/`, and the rest of this webapp (indicators.py,
builder.py, runner.py, the Strategy Builder UI, saved-strategy persistence)
are untouched — this file is just the empty catalog new strategies get
registered into.

Wraps existing, unmodified research/backtest code — never modify research/,
backtest/, or data_pipeline/ here, only import and call with pass-through
**params.

Shape for a new intraday entry (produces a signals dict for the shared
backtest.engine.Backtester):

    StrategySpec(id, name, "intraday", timeframe, description,
                 params=[...], signal_fn=lambda df, **p: (df, sig_dict),
                 bt_defaults=lambda p: dict(...BTConfig kwargs...))

Shape for a daily-portfolio entry (vol-targeted daily rebalancing, no
discrete trade list):

    StrategySpec(id, name, "daily-portfolio", "1D", description,
                 params=[...], daily_fn=lambda p, split, start, end: {...})
"""
from dataclasses import dataclass, field
from typing import Callable, Optional, Any


@dataclass
class ParamSpec:
    name: str
    type: str                     # "int" | "float" | "select" | "bool"
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    options: Optional[list] = None
    help: Optional[str] = None


@dataclass
class StrategySpec:
    id: str
    name: str
    category: str                 # "intraday" | "daily-portfolio"
    timeframe: str                # default bar timeframe ("5min"/"15min"/"30min"/"1h"/"1D")
    description: str
    params: list = field(default_factory=list)
    # intraday: (df) -> (df_used, signals_dict)
    signal_fn: Optional[Callable] = None
    # intraday: (params) -> dict of BTConfig kwargs
    bt_defaults: Optional[Callable] = None
    # daily-portfolio: (params, split, start, end) -> {equity, extra, net}
    daily_fn: Optional[Callable] = None
    notes: Optional[str] = None


def _p(name, type, default, **kw):
    return ParamSpec(name=name, type=type, default=default, **kw)


INTRADAY_SPECS: list[StrategySpec] = []
DAILY_SPECS: list[StrategySpec] = []


STRATEGY_REGISTRY: dict[str, StrategySpec] = {
    s.id: s for s in [*INTRADAY_SPECS, *DAILY_SPECS]
}
