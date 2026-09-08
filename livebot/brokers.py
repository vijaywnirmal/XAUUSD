"""
Broker + price-feed layer for the H1 bot.

  Mt5Feed      - read-only bars + ticks from a running MT5 terminal
  ReplayFeed   - iterate Postgres M5 bars (no MT5), for offline testing
  PaperBroker  - simulates OCO fills / SL / flat from a feed's ticks, with the
                 same cost model as backtest/engine.py; sends NOTHING
  Mt5Broker    - real pending/market orders via mt5.order_send; every send is
                 hard-gated on MODE=="live" AND LIVEBOT_CONFIRM_LIVE=="yes"

All position/order queries are filtered to this bot's MAGIC + SYMBOL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from livebot import config
from livebot.h1_strategy import Bar

CONTRACT = 100.0            # oz per 1.0 lot (XAUUSD)


# --------------------------------------------------------------------- types
@dataclass
class Tick:
    time: datetime
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass
class Position:
    ticket: int
    side: int                  # +1 long, -1 short
    volume: float
    entry_px: float
    entry_time: datetime
    sl: float
    box_hi: float = 0.0
    box_lo: float = 0.0
    entry_spread: float = 0.0


@dataclass
class Order:
    ticket: int
    kind: str                  # "buy_stop" | "sell_stop"
    price: float
    sl: float


# ==================================================================== FEEDS
class Mt5Feed:
    """Read-only view of a running, logged-in MT5 terminal."""

    def __init__(self):
        import MetaTrader5 as mt5
        self.mt5 = mt5
        self._m5 = mt5.TIMEFRAME_M5

    def connect(self):
        mt5 = self.mt5
        if not mt5.initialize():
            raise RuntimeError(f"mt5.initialize() failed: {mt5.last_error()}")
        term = mt5.terminal_info()
        if term is None or not term.connected:
            mt5.shutdown()
            raise RuntimeError("MT5 terminal is not connected to a trade server")
        if not mt5.symbol_select(config.SYMBOL, True):
            raise RuntimeError(f"symbol_select({config.SYMBOL}) failed")
        acc = mt5.account_info()
        return acc

    def shutdown(self):
        self.mt5.shutdown()

    def symbol_spec(self) -> dict:
        s = self.mt5.symbol_info(config.SYMBOL)
        return dict(point=s.point, digits=s.digits, min_lot=s.volume_min,
                    lot_step=s.volume_step, stops_level=s.trade_stops_level * s.point)

    def recent_m5_bars(self, n: int) -> list[Bar]:
        rates = self.mt5.copy_rates_from_pos(config.SYMBOL, self._m5, 1, n)  # skip forming bar
        if rates is None:
            return []
        return [Bar(time=datetime.fromtimestamp(r["time"], tz=timezone.utc),
                    open=float(r["open"]), high=float(r["high"]),
                    low=float(r["low"]), close=float(r["close"])) for r in rates]

    def tick(self) -> Tick:
        t = self.mt5.symbol_info_tick(config.SYMBOL)
        return Tick(time=datetime.fromtimestamp(t.time, tz=timezone.utc), bid=float(t.bid), ask=float(t.ask))


class ReplayFeed:
    """Feeds Postgres M5 bars one at a time. tick() is synthesised from the
    current bar close +/- half a nominal spread."""

    def __init__(self, nominal_spread=0.34):
        from data_pipeline.dataset import load_bars
        df = load_bars(config.REPLAY_TF, allow_oos=True, start=config.REPLAY_START,
                       end=config.REPLAY_END, columns=["ts", "open", "high", "low", "close", "spread_mean"])
        self._df = df.reset_index(drop=True)
        self._i = 0
        self._nom = nominal_spread

    def connect(self):
        return None

    def shutdown(self):
        pass

    def symbol_spec(self) -> dict:
        return dict(point=0.01, digits=2, min_lot=0.01, lot_step=0.01, stops_level=0.0)

    def advance(self) -> bool:
        self._i += 1
        return self._i < len(self._df)

    @property
    def now(self) -> datetime:
        return self._df["ts"].iloc[min(self._i, len(self._df) - 1)].to_pydatetime()

    def current_bar(self) -> tuple[float, float, float, float]:
        r = self._df.iloc[min(self._i, len(self._df) - 1)]
        return float(r.open), float(r.high), float(r.low), float(r.close)

    def recent_m5_bars(self, n: int) -> list[Bar]:
        lo = max(0, self._i - n)
        sub = self._df.iloc[lo:self._i]
        return [Bar(time=r.ts.to_pydatetime(), open=r.open, high=r.high, low=r.low, close=r.close)
                for r in sub.itertuples()]

    def tick(self) -> Tick:
        r = self._df.iloc[min(self._i, len(self._df) - 1)]
        sp = float(r.spread_mean) if r.spread_mean == r.spread_mean else self._nom
        return Tick(time=r.ts.to_pydatetime(), bid=r.close - sp / 2, ask=r.close + sp / 2)


# ================================================================== BROKERS
class PaperBroker:
    """Simulated fills from a feed. Sends nothing. Cost model mirrors
    backtest/engine.py: round-trip spread + $6/lot commission + slippage."""

    def __init__(self, feed):
        self.feed = feed
        self._pos: Optional[Position] = None
        self._orders: list[Order] = []
        self._next_ticket = 1
        self.realised_today = 0.0
        self.trades_today = 0
        self._closed_cb = None

    def connect(self):
        return self.feed.connect()

    def shutdown(self):
        self.feed.shutdown()

    def symbol_spec(self):
        return self.feed.symbol_spec()

    def recent_m5_bars(self, n):
        return self.feed.recent_m5_bars(n)

    def tick(self):
        return self.feed.tick()

    def on_new_day(self):
        self.realised_today = 0.0
        self.trades_today = 0

    def positions(self):
        return [self._pos] if self._pos else []

    def pending_orders(self):
        return list(self._orders)

    def place_oco(self, buy_stop, sell_stop, buy_sl, sell_sl, lots, box_width=0.0):
        self._orders = [
            Order(self._tk(), "buy_stop", buy_stop, buy_sl),
            Order(self._tk(), "sell_stop", sell_stop, sell_sl),
        ]
        for o in self._orders:
            o.box_hi, o.box_lo, o.box_width = buy_stop, sell_stop, box_width
        return [o.ticket for o in self._orders]

    def cancel_pending(self, reason=""):
        self._orders = []

    def close_all(self, reason=""):
        if not self._pos:
            return
        tk = self.tick()
        px = tk.bid if self._pos.side > 0 else tk.ask
        self._settle(px, reason, tk.spread)

    def on_poll(self):
        """Advance the simulation. If the feed exposes full bar OHLC (replay),
        use the bar's high/low so intrabar stop hits are caught the same
        pessimistic way backtest/engine.py does; otherwise fall back to ticks."""
        tk = self.tick()
        bar = self.feed.current_bar() if hasattr(self.feed, "current_bar") else None

        if self._pos is not None:                       # manage open position: SL only
            p = self._pos
            if bar is not None:
                _o, hi, lo, _c = bar
                if p.side > 0 and lo <= p.sl:
                    self._settle(p.sl, "stop", tk.spread)
                elif p.side < 0 and hi >= p.sl:
                    self._settle(p.sl, "stop", tk.spread)
            else:
                if p.side > 0 and tk.bid <= p.sl:
                    self._settle(p.sl, "stop", tk.spread)
                elif p.side < 0 and tk.ask >= p.sl:
                    self._settle(p.sl, "stop", tk.spread)
            return

        if not self._orders:
            return
        buy = next((o for o in self._orders if o.kind == "buy_stop"), None)
        sell = next((o for o in self._orders if o.kind == "sell_stop"), None)
        if bar is not None:
            o, hi, lo, _c = bar
            if buy and hi >= buy.price:                 # long checked first (matches engine)
                self._fill(+1, max(buy.price, o) + config.PAPER_SLIPPAGE_USD, buy, tk)
            elif sell and lo <= sell.price:
                self._fill(-1, min(sell.price, o) - config.PAPER_SLIPPAGE_USD, sell, tk)
        else:
            if buy and tk.ask >= buy.price:
                self._fill(+1, max(buy.price, tk.ask) + config.PAPER_SLIPPAGE_USD, buy, tk)
            elif sell and tk.bid <= sell.price:
                self._fill(-1, min(sell.price, tk.bid) - config.PAPER_SLIPPAGE_USD, sell, tk)

    # -- internals --
    def _tk(self):
        self._next_ticket += 1
        return self._next_ticket

    def _fill(self, side, px, order: Order, tk: Tick):
        self._pos = Position(ticket=self._tk(), side=side, volume=config.LOTS, entry_px=px,
                             entry_time=tk.time, sl=(order.box_lo if side > 0 else order.box_hi),
                             box_hi=order.box_hi, box_lo=order.box_lo, entry_spread=tk.spread)
        self._orders = []
        from livebot import logbook
        logbook.event("PAPER_FILL", side="long" if side > 0 else "short", px=round(px, 2),
                      sl=round(self._pos.sl, 2), spread=round(tk.spread, 3))

    def _settle(self, exit_px, reason, exit_spread):
        p = self._pos
        gross = p.side * (exit_px - p.entry_px) * p.volume * CONTRACT
        cost = ((p.entry_spread / 2 + exit_spread / 2) + 2 * config.PAPER_SLIPPAGE_USD) * p.volume * CONTRACT \
            + config.PAPER_COMMISSION_PER_LOT_RT * p.volume
        net = gross - cost
        self.realised_today += net
        self.trades_today += 1
        box_lvl = p.box_hi if p.side > 0 else p.box_lo
        from livebot import logbook
        logbook.trade(dict(
            date=p.entry_time.strftime("%Y-%m-%d"), box_high=round(p.box_hi, 2), box_low=round(p.box_lo, 2),
            box_width=round(p.box_hi - p.box_lo, 2), side="long" if p.side > 0 else "short",
            entry_time_utc=p.entry_time.strftime("%H:%M"), entry_px=round(p.entry_px, 2),
            entry_spread=round(p.entry_spread, 3), stop_px=round(p.sl, 2),
            exit_time_utc=self.tick().time.strftime("%H:%M"), exit_px=round(exit_px, 2), exit_reason=reason,
            gross_pnl=round(gross, 2), cost=round(cost, 2), net_pnl=round(net, 2),
            slippage_vs_box=round(p.side * (p.entry_px - box_lvl), 3), ticket=p.ticket, notes="paper",
        ))
        self._pos = None


class Mt5Broker:
    """Real orders. Every send is gated: MODE must be 'live' AND
    LIVEBOT_CONFIRM_LIVE=='yes', else _guard() raises before anything is sent."""

    def __init__(self, feed: Mt5Feed):
        self.feed = feed
        import MetaTrader5 as mt5
        self.mt5 = mt5
        self.realised_today = 0.0
        self.trades_today = 0

    def connect(self):
        acc = self.feed.connect()
        if acc is not None and not acc.trade_allowed:
            from livebot import logbook
            logbook.event("WARN", msg="account trade_allowed is False")
        return acc

    def shutdown(self):
        self.feed.shutdown()

    def symbol_spec(self):
        return self.feed.symbol_spec()

    def recent_m5_bars(self, n):
        return self.feed.recent_m5_bars(n)

    def tick(self):
        return self.feed.tick()

    def on_new_day(self):
        self.realised_today = 0.0
        self.trades_today = 0

    def on_poll(self):
        """Refresh today's realised P&L / trade count from history deals (our magic)."""
        mt5 = self.mt5
        now = datetime.now(timezone.utc)
        day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = mt5.history_deals_get(day0, now) or []
        pnl, entries = 0.0, 0
        for d in deals:
            if d.magic != config.MAGIC or d.symbol != config.SYMBOL:
                continue
            pnl += d.profit + d.commission + d.swap
            if d.entry == mt5.DEAL_ENTRY_IN:
                entries += 1
        self.realised_today = pnl
        self.trades_today = entries

    def _guard(self, what: str):
        if not (config.MODE == "live" and config.CONFIRM_LIVE):
            raise RuntimeError(
                f"BLOCKED live send ({what}): set config.MODE='live' AND env "
                f"LIVEBOT_CONFIRM_LIVE=yes to authorise real orders. (MODE={config.MODE!r}, "
                f"CONFIRM_LIVE={config.CONFIRM_LIVE})")

    def positions(self) -> list[Position]:
        out = []
        for p in (self.mt5.positions_get(symbol=config.SYMBOL) or []):
            if p.magic != config.MAGIC:
                continue
            side = 1 if p.type == self.mt5.POSITION_TYPE_BUY else -1
            out.append(Position(ticket=p.ticket, side=side, volume=p.volume, entry_px=p.price_open,
                                entry_time=datetime.fromtimestamp(p.time, tz=timezone.utc), sl=p.sl))
        return out

    def pending_orders(self) -> list[Order]:
        out = []
        for o in (self.mt5.orders_get(symbol=config.SYMBOL) or []):
            if o.magic != config.MAGIC:
                continue
            kind = "buy_stop" if o.type == self.mt5.ORDER_TYPE_BUY_STOP else "sell_stop"
            out.append(Order(ticket=o.ticket, kind=kind, price=o.price_open, sl=o.sl))
        return out

    def place_oco(self, buy_stop, sell_stop, buy_sl, sell_sl, lots, box_width=0.0):
        self._guard("place_oco")
        mt5 = self.mt5
        tickets = []
        for kind, price, sl, otype in (
            ("buy_stop", buy_stop, buy_sl, mt5.ORDER_TYPE_BUY_STOP),
            ("sell_stop", sell_stop, sell_sl, mt5.ORDER_TYPE_SELL_STOP),
        ):
            req = {
                "action": mt5.TRADE_ACTION_PENDING, "symbol": config.SYMBOL, "volume": float(lots),
                "type": otype, "price": float(price), "sl": float(sl),
                "type_time": mt5.ORDER_TIME_GTC, "magic": config.MAGIC, "comment": config.ORDER_COMMENT,
            }
            r = mt5.order_send(req)
            from livebot import logbook
            logbook.event("ORDER_SEND", kind=kind, price=price, sl=sl,
                          retcode=getattr(r, "retcode", None), comment=getattr(r, "comment", None))
            if r is not None and r.retcode == mt5.TRADE_RETCODE_DONE:
                tickets.append(r.order)
        return tickets

    def cancel_pending(self, reason=""):
        self._guard("cancel_pending")
        mt5 = self.mt5
        for o in self.pending_orders():
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
        from livebot import logbook
        logbook.event("PENDING_CANCELLED", reason=reason)

    def close_all(self, reason=""):
        self._guard("close_all")
        mt5 = self.mt5
        for p in self.positions():
            tk = self.tick()
            req = {
                "action": mt5.TRADE_ACTION_DEAL, "symbol": config.SYMBOL, "volume": p.volume,
                "type": mt5.ORDER_TYPE_SELL if p.side > 0 else mt5.ORDER_TYPE_BUY,
                "position": p.ticket, "price": tk.bid if p.side > 0 else tk.ask,
                "deviation": config.ORDER_DEVIATION_POINTS, "magic": config.MAGIC,
                "comment": f"{config.ORDER_COMMENT} flat", "type_time": mt5.ORDER_TIME_GTC,
            }
            r = mt5.order_send(req)
            from livebot import logbook
            logbook.event("POSITION_CLOSE", ticket=p.ticket, reason=reason,
                          retcode=getattr(r, "retcode", None))


def make_broker():
    """Pick the broker/feed for the configured MODE."""
    if config.MODE == "replay":
        return PaperBroker(ReplayFeed())
    if config.MODE == "paper":
        return PaperBroker(Mt5Feed())
    if config.MODE == "live":
        return Mt5Broker(Mt5Feed())
    raise SystemExit(f"unknown MODE {config.MODE!r} (paper | replay | live)")
