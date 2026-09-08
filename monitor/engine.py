"""
Real-time monitor loop:  bars + tick  ->  features + patterns + direction lean
+ news (calendar blackout, GDELT tone)  ->  monitor/logs/snapshot.json  (live)
and an appended row in monitor/logs/history.csv (for later study).

Bar/tick source:
  mt5  (default) - the running MT5 terminal, read-only (via livebot.brokers.Mt5Feed)
  pg            - Postgres M5 bars, walking forward (offline testing)
"""
from __future__ import annotations

import json
import os
import tempfile
import time
import traceback
from datetime import datetime, timezone

import pandas as pd

from monitor import config as C
from monitor import features as F
from monitor import patterns as P
from monitor import direction as D
from monitor import news_calendar, news_sentiment

os.makedirs(C.LOG_DIR, exist_ok=True)


# ---------------------------------------------------------------- sources
class Mt5Source:
    def __init__(self):
        from livebot.brokers import Mt5Feed
        self.feed = Mt5Feed()

    def connect(self):
        return self.feed.connect()

    def bars(self, n=600) -> pd.DataFrame:
        rows = self.feed.recent_m5_bars(n)
        return pd.DataFrame([{"ts": b.time, "open": b.open, "high": b.high,
                              "low": b.low, "close": b.close} for b in rows])

    def tick(self):
        return self.feed.tick()

    def now(self):
        return datetime.now(timezone.utc)

    def advance(self):
        time.sleep(C.POLL_SECONDS)
        return True

    def shutdown(self):
        self.feed.shutdown()


class PgSource:
    def __init__(self, start="2024-01-01", end="2024-02-01"):
        from data_pipeline.dataset import load_bars
        self.df = load_bars(C.TF, allow_oos=True, start=start, end=end,
                            columns=["ts", "open", "high", "low", "close", "spread_mean"]).reset_index(drop=True)
        self.i = 600

    def connect(self):
        return None

    def bars(self, n=600):
        return self.df.iloc[max(0, self.i - n):self.i][["ts", "open", "high", "low", "close"]]

    def tick(self):
        r = self.df.iloc[min(self.i, len(self.df) - 1)]
        sp = float(r.spread_mean) if r.spread_mean == r.spread_mean else 0.34

        class T:
            bid = r.close - sp / 2
            ask = r.close + sp / 2
            mid = r.close
            spread = sp
        return T()

    def now(self):
        return self.df["ts"].iloc[min(self.i, len(self.df) - 1)].to_pydatetime()

    def advance(self):
        self.i += 1
        return self.i < len(self.df)

    def shutdown(self):
        pass


# ---------------------------------------------------------------- write
def _write_snapshot(payload: dict):
    fd, tmp = tempfile.mkstemp(dir=C.LOG_DIR, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, default=str, indent=1)
    os.replace(tmp, C.SNAPSHOT)


_HIST_COLS = ["ts", "price", "spread", "p_up", "lean", "confidence", "pattern_lean",
              "blackout", "min_to_high", "tone_now", "tone_z", "vol_z", "trend",
              "rsi", "atr_pct", "range_pos", "session"]


def _append_history(row: dict):
    import csv
    new = not os.path.exists(C.HISTORY_CSV)
    with open(C.HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_HIST_COLS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(row)


# ---------------------------------------------------------------- loop
def run(source):
    acc = source.connect()
    print(f"monitor: source={type(source).__name__} "
          f"account={getattr(acc, 'login', None)} server={getattr(acc, 'server', None)}")
    news_cal, news_sent = {}, {}
    last_news = 0.0
    try:
        while True:
            try:
                now = source.now()
                df = source.bars(600)
                if len(df) < 60:
                    time.sleep(2)
                    continue
                tick = source.tick()
                feat = F.compute(df, tick)
                pats = P.evaluate(df)
                pred = D.predict(feat)

                if time.time() - last_news > C.NEWS_REFRESH_SECONDS or not news_cal:
                    news_cal = news_calendar.summary(now)
                    news_sent = news_sentiment.summary()
                    last_news = time.time()

                pat_lean = P.net_lean(pats)
                firing = [p for p in pats if p["firing"]]
                read = _read(pred, pat_lean, news_cal, feat)

                snap = {
                    "ts": now.isoformat(timespec="seconds"),
                    "symbol": C.SYMBOL, "source": type(source).__name__,
                    "price": feat.get("price"), "spread": feat.get("spread"),
                    "session": feat.get("session"),
                    "features": {k: feat.get(k) for k in
                                 ["ret_1h", "ret_1d", "trend", "ema_f_gap", "rsi",
                                  "macd_hist", "atr_pct", "range_pos", "streak",
                                  "london_drift_atr", "ny_box_width_atr", "ny_box_pos"]},
                    "patterns": pats, "patterns_firing": [p["name"] for p in firing],
                    "pattern_lean": pat_lean,
                    "direction": pred,
                    "news_calendar": news_cal, "news_sentiment": news_sent,
                    "read": read,
                }
                _write_snapshot(snap)
                _append_history({
                    "ts": snap["ts"], "price": snap["price"], "spread": snap["spread"],
                    "p_up": pred.get("p_up"), "lean": pred.get("lean"),
                    "confidence": pred.get("confidence"), "pattern_lean": pat_lean,
                    "blackout": news_cal.get("blackout"),
                    "min_to_high": news_cal.get("minutes_to_next_high"),
                    "tone_now": news_sent.get("tone_now"), "tone_z": news_sent.get("tone_z"),
                    "vol_z": news_sent.get("vol_z"), "trend": feat.get("trend"),
                    "rsi": feat.get("rsi"), "atr_pct": feat.get("atr_pct"),
                    "range_pos": feat.get("range_pos"), "session": feat.get("session"),
                })
            except Exception:
                traceback.print_exc()
            if not source.advance():
                break
    finally:
        source.shutdown()


def _read(pred, pat_lean, news_cal, feat) -> dict:
    """A plain-English composite, deliberately conservative."""
    parts = []
    if news_cal.get("blackout"):
        parts.append(f"NEWS BLACKOUT - {news_cal.get('blackout_reason')}. Stand aside.")
    m2h = news_cal.get("minutes_to_next_high")
    if m2h is not None and 0 < m2h <= 60:
        parts.append(f"High-impact event in {m2h:.0f} min ({news_cal.get('next_high', {}).get('title')}).")
    lean = pred.get("lean", "n/a")
    conf = pred.get("confidence")
    if pred.get("available"):
        parts.append(f"Model lean {lean} (P_up {pred['p_up']}, conf {conf}, OOS AUC {pred.get('model_oos_auc')}).")
    if pat_lean:
        parts.append(f"Patterns net {'+' if pat_lean > 0 else ''}{pat_lean} "
                     f"({'bullish' if pat_lean > 0 else 'bearish'} tilt).")
    agree = (lean == "up" and pat_lean > 0) or (lean == "down" and pat_lean < 0)
    verdict = ("model and patterns AGREE" if agree and pat_lean and lean in ("up", "down")
               else "mixed / no conviction")
    return {"verdict": verdict, "notes": parts,
            "tradeable": (not news_cal.get("blackout")) and agree and (conf or 0) >= 0.1}
