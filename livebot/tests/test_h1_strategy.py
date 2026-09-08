"""Pure-logic tests for livebot.h1_strategy.decide(). No MT5, no network."""
from datetime import datetime, timezone, timedelta

import pytest

from livebot import config
from livebot import h1_strategy as H


def _bar(hh, mm, o, hi, lo, c, day="2025-06-10"):
    return H.Bar(time=datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:00+00:00"),
                 open=o, high=hi, low=lo, close=c)


def _box_bars(hi=2650.0, lo=2640.0, day="2025-06-10"):
    # six M5 bars 13:30..13:55; extremes land on the middle bars
    out = []
    for i, mnt in enumerate(range(30, 60, 5)):
        h = hi if i == 2 else hi - 2
        l = lo if i == 3 else lo + 2
        out.append(_bar(13, mnt, o=lo + 5, hi=h, lo=l, c=lo + 5, day=day))
    return out


def _ctx(now_hhmm, **kw):
    hh, mm = now_hhmm
    base = dict(
        now=datetime.fromisoformat(f"2025-06-10T{hh:02d}:{mm:02d}:00+00:00"),
        bars_today=_box_bars(), last_price=2645.0, spread_usd=0.25,
        has_position=False, has_pending=False, trades_today=0,
        realised_pnl_today=0.0, kill_switch=False, armed_ever_today=False,
    )
    base.update(kw)
    return H.Context(**base)


def test_forming_box_waits():
    assert isinstance(H.decide(_ctx((13, 45))), H.Wait)


def test_box_values():
    hi, lo, n = H.compute_box(_box_bars(2651.0, 2639.0))
    assert (hi, lo, n) == (2651.0, 2639.0, 6)


def test_arms_after_box_with_ok_spread():
    out = H.decide(_ctx((14, 5)))
    assert isinstance(out, H.PlaceOco)
    assert out.buy_stop == 2650.0 and out.sell_stop == 2640.0
    assert out.buy_sl == 2640.0 and out.sell_sl == 2650.0
    assert out.lots == config.LOTS


def test_wide_spread_holds_then_cancels():
    assert isinstance(H.decide(_ctx((14, 5), spread_usd=0.99)), H.Wait)
    out = H.decide(_ctx((14, 5), spread_usd=0.99, has_pending=True))
    assert isinstance(out, H.CancelPending)


def test_wide_box_skips():
    out = H.decide(_ctx((14, 5), bars_today=_box_bars(2700.0, 2640.0)))
    assert isinstance(out, H.Skip) and "wide" in out.reason


def test_broke_before_arm_skips():
    out = H.decide(_ctx((14, 5), last_price=2655.0))            # already above box high
    assert isinstance(out, H.Skip) and "before arm" in out.reason
    # ...but if we already armed earlier, a breakout is expected, not a skip
    assert isinstance(H.decide(_ctx((14, 5), last_price=2655.0, armed_ever_today=True)), H.PlaceOco)


def test_in_position_waits_then_flats_at_2000():
    assert isinstance(H.decide(_ctx((15, 0), has_position=True)), H.Wait)
    out = H.decide(_ctx((20, 0), has_position=True))
    assert isinstance(out, H.CloseAll)


def test_one_trade_per_day():
    out = H.decide(_ctx((15, 0), trades_today=1))
    assert isinstance(out, H.Skip)


def test_no_break_by_1800_skips_and_cancels():
    assert isinstance(H.decide(_ctx((18, 1))), H.Skip)
    assert isinstance(H.decide(_ctx((18, 1), has_pending=True)), H.CancelPending)


def test_daily_loss_halt():
    out = H.decide(_ctx((14, 30), realised_pnl_today=-config.MAX_DAILY_LOSS_USD - 1))
    assert isinstance(out, H.Skip)


def test_kill_switch():
    assert isinstance(H.decide(_ctx((14, 30), kill_switch=True)), H.Skip)


def test_past_flat_no_position_is_skip():
    assert isinstance(H.decide(_ctx((20, 30))), H.Skip)
