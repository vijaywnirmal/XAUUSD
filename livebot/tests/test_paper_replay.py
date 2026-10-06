"""Server-clock conversion and the paper fill -> settle -> replay file path. No MT5, no network."""
import json
import os
from datetime import datetime, timedelta, timezone

from livebot import brokers, config, logbook


def test_server_offset_follows_new_york_dst():
    utc = lambda s: datetime.fromisoformat(s + "+00:00")  # noqa: E731
    assert brokers.server_offset(utc("2026-10-06T19:00")) == timedelta(hours=3)   # NY daylight time
    assert brokers.server_offset(utc("2026-12-01T12:00")) == timedelta(hours=2)   # NY standard time
    assert brokers.server_offset(utc("2026-03-08T06:59")) == timedelta(hours=2)   # 2nd Sunday of March, before 07:00 UTC
    assert brokers.server_offset(utc("2026-03-08T07:00")) == timedelta(hours=3)
    assert brokers.server_offset(utc("2026-11-01T05:59")) == timedelta(hours=3)   # 1st Sunday of November
    assert brokers.server_offset(utc("2026-11-01T06:00")) == timedelta(hours=2)


class FakeFeed:
    def __init__(self):
        self.now = datetime(2026, 10, 6, 14, 5, tzinfo=timezone.utc)
        self.bid, self.ask = 4000.0, 4000.3

    def tick(self):
        return brokers.Tick(time=self.now, bid=self.bid, ask=self.ask)

    def replay_data(self, start, end, windows):
        return {"minutes": [[start.isoformat(), 1, 2, 0.5, 1.5]], "seconds": []}


def test_paper_stop_writes_trade_and_replay(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(logbook, "_TRADES", str(tmp_path / "trades.csv"))
    monkeypatch.setattr(logbook, "_DECISIONS", str(tmp_path / "decisions.jsonl"))
    feed = FakeFeed()
    b = brokers.PaperBroker(feed)
    b.place_oco(4010.0, 3990.0, 3990.0, 4010.0, config.LOTS, 20.0)
    feed.bid, feed.ask = 4010.2, 4010.5          # breaks above the box
    b.on_poll()
    assert b.positions() and b.positions()[0].side == 1
    feed.now += timedelta(minutes=30)
    feed.bid, feed.ask = 3989.9, 3990.2          # back through the stop
    b.on_poll()
    assert not b.positions() and b.trades_today == 1
    rows = (tmp_path / "trades.csv").read_text().splitlines()
    assert len(rows) == 2 and "XAUUSD" in rows[1]
    rp = json.loads((tmp_path / "replays" / "2026-10-06_XAUUSD.json").read_text())
    t = rp["trade"]
    assert rp["id"] == "2026-10-06-XAUUSD" and t["side"] == "long" and t["exit_reason"] == "stop"
    assert t["entry_time"].startswith("2026-10-06T14:05") and t["exit_time"].startswith("2026-10-06T14:35")
    # gross: (3990 - 4010.52) * 0.01 lot * 100 oz; costs make it worse
    assert float(t["net_pnl"]) < float(t["gross_pnl"]) < 0
    assert abs(float(t["gross_pnl"]) - (3990.0 - (4010.5 + config.PAPER_SLIPPAGE_USD)) * config.LOTS * 100) < 0.01
    assert rp["contract"] == 100.0 and rp["minutes"]
