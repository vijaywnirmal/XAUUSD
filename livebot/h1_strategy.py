"""
H1 - NY opening-range breakout: pure decision logic, no MT5, no I/O.

Spec (identical to the backtest):
  * box    = completed M5 bars whose open time is in [13:30, 14:00) UTC
             -> box_high = max(high), box_low = min(low)
  * entry  = OCO stop orders: BUY-STOP @ box_high, SELL-STOP @ box_low,
             placed from 14:00 UTC; first to trade wins, cancel the other.
             If price is ALREADY beyond a level when we would first arm, skip
             the day (don't chase).
  * stop   = the opposite box extreme (long -> box_low, short -> box_high)
  * no new entry at/after 18:00 UTC; force any open position flat at/after 20:00 UTC
  * one trade per day
Plus live-only guards: skip wide boxes, skip while spread is wide, per-day
trade cap, daily-loss halt, kill switch.

`decide(ctx)` returns one Intent. The runner executes it against a broker.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Optional, Sequence

from livebot import config


def _hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


BOX_START = _hhmm(config.BOX_START_UTC)
BOX_END = _hhmm(config.BOX_END_UTC)
BREAK_END = _hhmm(config.BREAK_END_UTC)
FLAT = _hhmm(config.FLAT_UTC)


def _p(x: float) -> str:
    """A price in the instrument's own precision (gold 2 decimals, EURUSD 5)."""
    return f"{x:.{config.DIGITS}f}"


# ------------------------------------------------------------------- I/O types
@dataclass(frozen=True)
class Bar:
    time: datetime      # bar OPEN time, tz-aware UTC
    open: float
    high: float
    low: float
    close: float


@dataclass
class Context:
    now: datetime                       # tz-aware UTC
    bars_today: Sequence[Bar]           # completed M5 bars with open time on `now`'s UTC date
    last_price: float                   # mid (or last)
    spread_usd: Optional[float]
    has_position: bool
    has_pending: bool
    trades_today: int
    realised_pnl_today: float
    kill_switch: bool = False
    armed_ever_today: bool = False      # have we placed OCO at any point today


# Intents ---------------------------------------------------------------------
@dataclass(frozen=True)
class Wait:
    status: str


@dataclass(frozen=True)
class Skip:
    reason: str                         # done for the day, nothing more to do


@dataclass(frozen=True)
class PlaceOco:
    buy_stop: float
    sell_stop: float
    buy_sl: float
    sell_sl: float
    lots: float
    box_width: float


@dataclass(frozen=True)
class CancelPending:
    reason: str


@dataclass(frozen=True)
class CloseAll:
    reason: str


# ------------------------------------------------------------------- box calc
def compute_box(bars_today: Sequence[Bar]) -> Optional[tuple[float, float, int]]:
    box = [b for b in bars_today if BOX_START <= b.time.timetz().replace(tzinfo=None) < BOX_END]
    if not box:
        return None
    hi = max(b.high for b in box)
    lo = min(b.low for b in box)
    return hi, lo, len(box)


# ------------------------------------------------------------------- decide
def decide(ctx: Context):
    t = ctx.now.timetz().replace(tzinfo=None)

    # 1. force flat at/after 20:00 UTC, always
    if t >= FLAT:
        if ctx.has_position:
            return CloseAll("session flat 20:00 UTC")
        if ctx.has_pending:
            return CancelPending("past flat time")
        return Skip("past 20:00 UTC")

    # 2. still forming the box
    if t < BOX_END:
        return Wait(f"forming box ({config.BOX_START_UTC}-{config.BOX_END_UTC} UTC)")

    box = compute_box(ctx.bars_today)
    if box is None:
        return Skip("no box bars for today") if t >= BREAK_END else Wait("waiting for box bars")
    box_hi, box_lo, n = box
    if n < 5:
        # incomplete box (missing M5 bars); require the full 30-min window
        return Skip("incomplete box") if t >= BREAK_END else Wait(f"box has {n}/5 bars")
    width = box_hi - box_lo

    # 3. managing an open position: SL sits on the broker order; flat handled above
    if ctx.has_position:
        return Wait("in trade - SL at box extreme, flat at 20:00")

    # 4. no position: guard checks
    if ctx.kill_switch:
        return CancelPending("kill switch") if ctx.has_pending else Skip("kill switch engaged")
    if ctx.trades_today >= config.MAX_TRADES_PER_DAY:
        return CancelPending("trade cap") if ctx.has_pending else Skip("one trade/day done")
    if ctx.realised_pnl_today <= -abs(config.MAX_DAILY_LOSS_USD):
        return CancelPending("daily loss halt") if ctx.has_pending else Skip("daily loss halt")
    if t >= BREAK_END:
        return CancelPending("break window closed") if ctx.has_pending else Skip("no break by 18:00 UTC")

    # 5. day-quality filters
    if config.MAX_BOX_WIDTH_USD is not None and width > config.MAX_BOX_WIDTH_USD:
        return Skip(f"box too wide {_p(width)} > {_p(config.MAX_BOX_WIDTH_USD)}")

    # 6. don't chase: if price already broke a level before we ever armed, skip
    if not ctx.armed_ever_today and (ctx.last_price > box_hi or ctx.last_price < box_lo):
        return Skip(f"broke box before arm (px {_p(ctx.last_price)}, box {_p(box_lo)}-{_p(box_hi)})")

    # 7. spread guard - gates the FIRST arm; pulls a working OCO only on a spike
    spread_bad = ctx.spread_usd is not None and ctx.spread_usd > config.MAX_SPREAD_USD
    if ctx.has_pending:
        if spread_bad:
            return CancelPending(f"spread spike {ctx.spread_usd:.{config.DIGITS + 1}f}")
        return Wait("armed - OCO working, monitoring breakout")
    if spread_bad:
        return Wait(f"spread {ctx.spread_usd:.{config.DIGITS + 1}f} > {_p(config.MAX_SPREAD_USD)} - not arming yet")

    # 8. arm
    return PlaceOco(buy_stop=box_hi, sell_stop=box_lo, buy_sl=box_lo, sell_sl=box_hi,
                    lots=config.LOTS, box_width=width)
