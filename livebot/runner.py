"""
The poll loop: build a Context, ask h1_strategy.decide(), execute the Intent.

Modes (from livebot/config.py, override with LIVEBOT_MODE):
  paper  - attach to MT5 read-only, simulate fills. DEFAULT.
  replay - run over Postgres M5 bars, no MT5, prints a summary at the end.
  live   - real orders (also needs env LIVEBOT_CONFIRM_LIVE=yes).
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from livebot import config, logbook, recorder, status as statusfile
from livebot import h1_strategy as H
from livebot.brokers import make_broker


class Runner:
    def __init__(self):
        self.broker = make_broker()
        self._day = None
        self._armed_ever = False
        self._day_done = False
        self._last_status = None
        self._acct = {}
        self._last_intent = "starting"

    # ---- per-day bookkeeping ------------------------------------------
    def _roll_day(self, now: datetime):
        d = now.date()
        if d != self._day:
            self._day = d
            self._armed_ever = False
            self._day_done = False
            self._last_status = None
            self.broker.on_new_day()
            logbook.event("NEW_DAY", date=str(d))

    # ---- one iteration ---------------------------------------------------
    def step(self, now: datetime) -> None:
        self._roll_day(now)
        self.broker.on_poll()
        tick = self.broker.tick()
        bars_today = [b for b in self.broker.recent_m5_bars(180) if b.time.date() == now.date()]

        ctx = H.Context(
            now=now, bars_today=bars_today, last_price=tick.mid, spread_usd=tick.spread,
            has_position=bool(self.broker.positions()),
            has_pending=bool(self.broker.pending_orders()),
            trades_today=self.broker.trades_today,
            realised_pnl_today=self.broker.realised_today,
            kill_switch=os.path.exists(config.KILL_SWITCH_FILE),
            armed_ever_today=self._armed_ever,
        )
        if self._day_done and not ctx.has_position and not ctx.has_pending:
            self._publish(ctx, tick, "day complete")
            return

        intent = H.decide(ctx)
        self._publish(ctx, tick, self._intent_label(intent))

        if isinstance(intent, H.Wait):
            if intent.status != self._last_status:
                logbook.decision("Wait", intent.status, spread=round(tick.spread, 3),
                                 px=round(tick.mid, 2))
                self._last_status = intent.status
        elif isinstance(intent, H.Skip):
            logbook.decision("Skip", intent.reason)
            self._day_done = True
        elif isinstance(intent, H.PlaceOco):
            logbook.event("ARM", buy_stop=round(intent.buy_stop, 2), sell_stop=round(intent.sell_stop, 2),
                          box_width=round(intent.box_width, 2), spread=round(tick.spread, 3))
            self.broker.place_oco(intent.buy_stop, intent.sell_stop, intent.buy_sl, intent.sell_sl,
                                  intent.lots, intent.box_width)
            self._armed_ever = True
            self._last_status = None
        elif isinstance(intent, H.CancelPending):
            self.broker.cancel_pending(intent.reason)
            logbook.decision("CancelPending", intent.reason)
        elif isinstance(intent, H.CloseAll):
            self.broker.close_all(intent.reason)
            logbook.decision("CloseAll", intent.reason)

    # ---- status snapshot for the webapp --------------------------------
    @staticmethod
    def _intent_label(intent) -> str:
        if isinstance(intent, H.Wait):
            return intent.status
        if isinstance(intent, H.Skip):
            return f"skip: {intent.reason}"
        if isinstance(intent, H.PlaceOco):
            return f"arm OCO {intent.sell_stop:.2f} / {intent.buy_stop:.2f}"
        if isinstance(intent, H.CancelPending):
            return f"cancel: {intent.reason}"
        if isinstance(intent, H.CloseAll):
            return f"close: {intent.reason}"
        return type(intent).__name__

    def _publish(self, ctx, tick, label: str) -> None:
        self._last_intent = label
        if config.MODE != "replay":
            try:
                recorder.record(tick, label)
            except Exception:
                pass
        box = H.compute_box(ctx.bars_today)
        pos = (self.broker.positions() or [None])[0]
        statusfile.write({
            "account": self._acct,
            "now_utc": ctx.now.isoformat(timespec="seconds"),
            "price": round(tick.mid, 2),
            "spread": round(tick.spread, 4),
            "box": None if box is None else {
                "high": round(box[0], 2), "low": round(box[1], 2),
                "width": round(box[0] - box[1], 2), "bars": box[2]},
            "state": label,
            "armed_today": self._armed_ever,
            "day_done": self._day_done,
            "has_pending": ctx.has_pending,
            "trades_today": ctx.trades_today,
            "realised_today": round(ctx.realised_pnl_today, 2),
            "kill_switch": ctx.kill_switch,
            "position": None if pos is None else {
                "side": "long" if pos.side > 0 else "short",
                "entry": round(pos.entry_px, 2), "sl": round(pos.sl, 2),
                "unrealised": round(pos.side * (tick.mid - pos.entry_px) * pos.volume * 100.0, 2)},
        })

    # ---- run --------------------------------------------------------------
    def run(self):
        acc = self.broker.connect()
        server = str(getattr(acc, "server", "") or "")
        is_live_acct = "live" in server.lower()
        login = getattr(acc, "login", None)
        self._acct = {
            "login": (str(login)[:3] + "***") if login else None,   # masked
            "broker": getattr(acc, "company", None), "server": server or None,
            "balance": getattr(acc, "balance", None), "currency": getattr(acc, "currency", None),
            "trade_allowed": getattr(acc, "trade_allowed", None), "is_live": is_live_acct,
        }
        logbook.event("START", mode=config.MODE, symbol=config.SYMBOL, magic=config.MAGIC,
                      account=self._acct["login"], broker=getattr(acc, "company", None),
                      server=server or None, balance=getattr(acc, "balance", None),
                      trade_allowed=getattr(acc, "trade_allowed", None),
                      live_authorised=(config.MODE == "live" and config.CONFIRM_LIVE))
        if is_live_acct and config.MODE != "replay":
            print(f"\n  *** attached to a LIVE account ({server}, #{getattr(acc,'login','?')}, "
                  f"bal {getattr(acc,'balance','?')}) ***")
            print(f"  *** MODE={config.MODE} -> "
                  + ("REAL ORDERS WILL BE SENT" if (config.MODE == "live" and config.CONFIRM_LIVE)
                     else "read-only, no orders") + " ***\n")
        if config.MODE == "live":
            if not config.CONFIRM_LIVE:
                raise SystemExit(
                    "MODE=live but LIVEBOT_CONFIRM_LIVE!=yes -> refusing to start. "
                    "Set the env var to 'yes' only when you intend to trade real money.")
            if getattr(acc, "trade_allowed", True) is False:
                raise SystemExit(
                    "MODE=live but the account/terminal has trade_allowed=False "
                    "(enable Algo Trading in MT5). Refusing to start.")
        try:
            if config.MODE == "replay":
                self._run_replay()
            else:
                self._run_realtime()
        finally:
            self.broker.shutdown()

    def _run_realtime(self):
        while True:
            try:
                self.step(datetime.now(timezone.utc))
            except Exception:
                logbook.event("ERROR")
                import traceback
                traceback.print_exc()
            time.sleep(config.POLL_SECONDS)

    def _run_replay(self):
        feed = self.broker.feed
        n = 0
        while True:
            self.step(feed.now)
            n += 1
            if not feed.advance():
                break
        logbook.event("REPLAY_DONE", steps=n)
        _replay_summary()


def _replay_summary():
    import csv
    path = os.path.join(config.LOG_DIR, "trades.csv")
    if not os.path.exists(path):
        print("\n  replay: no trades.\n")
        return
    rows = [r for r in csv.DictReader(open(path)) if r["mode"] == "replay" and r["net_pnl"]]
    if not rows:
        print("\n  replay: no trades.\n")
        return
    net = [float(r["net_pnl"]) for r in rows]
    wins = [x for x in net if x > 0]
    pf = sum(wins) / -sum(x for x in net if x <= 0) if any(x <= 0 for x in net) else float("inf")
    print(f"\n  REPLAY SUMMARY  ({config.REPLAY_START}..{config.REPLAY_END})")
    print(f"    trades {len(net)}   win {len(wins)/len(net):.0%}   "
          f"exp ${sum(net)/len(net):+.3f}/trade   PF {pf:.2f}   net ${sum(net):+.2f}")
    print(f"    (compare to backtest H1 in-sample: gross +$0.388/trade, "
          f"net ~-$0.03 at $0.34 spread)\n")
