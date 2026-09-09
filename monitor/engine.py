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
from monitor import candles as CN
from monitor import direction as D
from monitor import vol_model as V
from monitor import meta as M
from monitor import london as L
from monitor import outcomes as O
from monitor import xa_data
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

    def cross_bars(self) -> dict:
        try:
            return xa_data.live_xa(self.feed.mt5)
        except Exception:
            return {}

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

    def cross_bars(self) -> dict:
        lo = self.df["ts"].iloc[max(0, self.i - 400)]
        hi = self.df["ts"].iloc[min(self.i, len(self.df) - 1)]
        try:
            return xa_data.training_xa(lo, hi)
        except Exception:
            return {}

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
              "meta_p_correct", "meta_act", "london_p_up", "vol_regime", "rv_pred_bps",
              "vol_pct", "ev_mins_to", "ev_next_weight", "xa_usd_60m",
              "blackout", "min_to_high", "tone_now", "tone_z", "trend",
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
    last_news = last_xa = 0.0
    xa = {}
    try:
        while True:
            try:
                now = source.now()
                df = source.bars(600)
                if len(df) < 60:
                    time.sleep(2)
                    continue
                tick = source.tick()
                if time.time() - last_xa > 60 or not xa:
                    try:
                        xa = source.cross_bars()
                    except Exception:
                        xa = {}
                    last_xa = time.time()
                feat = F.compute(df, tick, xa=xa)
                pats = P.evaluate(df)
                cands = CN.evaluate(df)
                pred = D.predict(feat)
                meta_p = M.predict(feat)
                lon_p = L.predict(feat)

                if time.time() - last_news > C.NEWS_REFRESH_SECONDS or not news_cal:
                    news_cal = news_calendar.summary(now)
                    news_sent = news_sentiment.summary()
                    last_news = time.time()

                vol = V.predict(feat)
                pat_lean = P.net_lean(pats)
                firing = [p for p in pats if p["firing"]]
                # live-AUC bookkeeping - only while the feed is actually moving
                # (skip weekends / market-closed so flat prices don't pollute it)
                feed_live = df["close"].tail(6).nunique() > 1
                try:
                    if feed_live:
                        O.record(now, feat.get("price"), pred, meta_p, lon_p)
                        O.resolve(now, feat.get("price"))
                    la = O.live_auc()
                except Exception:
                    la = {"available": False}
                read = _read(pred, meta_p, lon_p, vol, pat_lean, news_cal, feat)
                ev = {k: feat.get(k) for k in F.EVENT_COLS}
                ev["next_kind"] = None
                try:
                    from monitor.calendar_history import live_event_summary
                    ev.update({k: live_event_summary(now)[k] for k in ("next_kind", "next_when_utc")})
                except Exception:
                    pass

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
                    "candles": cands, "candle_lean": CN.net_lean(cands),
                    "direction": pred,
                    "meta": meta_p,
                    "london": lon_p,
                    "volatility": vol,
                    "event_proximity": ev,
                    "cross_asset": {k: feat.get(k) for k in F.XA_COLS},
                    "live_auc": la,
                    "news_calendar": news_cal, "news_sentiment": news_sent,
                    "read": read,
                }
                _write_snapshot(snap)
                _append_history({
                    "ts": snap["ts"], "price": snap["price"], "spread": snap["spread"],
                    "p_up": pred.get("p_up"), "lean": pred.get("lean"),
                    "confidence": pred.get("confidence"), "pattern_lean": pat_lean,
                    "meta_p_correct": meta_p.get("p_correct"), "meta_act": int(bool(meta_p.get("act"))),
                    "london_p_up": lon_p.get("p_up"),
                    "vol_regime": vol.get("regime"), "rv_pred_bps": vol.get("rv_pred_bps"),
                    "vol_pct": vol.get("percentile"),
                    "ev_mins_to": feat.get("ev_mins_to"), "ev_next_weight": feat.get("ev_next_weight"),
                    "xa_usd_60m": feat.get("xa_usd_60m"),
                    "blackout": news_cal.get("blackout"),
                    "min_to_high": news_cal.get("minutes_to_next_high"),
                    "tone_now": news_sent.get("tone_now"), "tone_z": news_sent.get("tone_z"),
                    "trend": feat.get("trend"), "rsi": feat.get("rsi"),
                    "atr_pct": feat.get("atr_pct"), "range_pos": feat.get("range_pos"),
                    "session": feat.get("session"),
                })
            except Exception:
                traceback.print_exc()
            if not source.advance():
                break
    finally:
        source.shutdown()


def _pct(x):
    return f"{round(x * 100)}%" if isinstance(x, (int, float)) else "?"


def _read(pred, meta_p, lon_p, vol, pat_lean, news_cal, feat) -> dict:
    """Plain-language composite for a non-quant reader. The go/no-go gate is the
    confidence filter (meta model): only 'take a trade' when it's confident the
    direction call is right, there's no news blackout, and swings aren't huge."""
    parts = []
    if news_cal.get("blackout"):
        parts.append(f"News blackout — {news_cal.get('blackout_reason')}. Don't trade through it.")
    m2h = news_cal.get("minutes_to_next_high")
    if m2h is not None and 0 < m2h <= 60:
        parts.append(f"Big news due in {m2h:.0f} min ({(news_cal.get('next_high') or {}).get('title')}) "
                     f"— expect a spike.")

    if pred.get("available"):
        sess, sauc = pred.get("session"), pred.get("session_auc")
        good = pred.get("trust_now")
        parts.append(
            f"Model sees about a {_pct(pred['p_up'])} chance price is higher in ~1 hour. "
            f"In the {sess} session it's been {_pct(sauc)} accurate on unseen data — "
            + ("usable here." if good else "basically a coin toss here, so ignore its guess."))

    act = bool(meta_p.get("act"))
    if meta_p.get("available"):
        parts.append(
            f"Confidence filter: {_pct(meta_p.get('p_correct'))} sure that direction call is right "
            f"(needs {_pct(meta_p.get('threshold'))}) — "
            + ("it says act on it." if act else "not confident enough, so skip."))

    if lon_p.get("available") and lon_p.get("at_decision_time") and lon_p.get("reliable"):
        parts.append(f"London-session model (1pm→5pm UTC move): leans {lon_p.get('lean')}, "
                     f"{_pct(lon_p.get('p_up'))} chance up.")

    reg = vol.get("regime")
    if vol.get("available"):
        bps = vol.get("rv_pred_bps") or 0
        parts.append(f"Next hour looks {reg} — expect a move of roughly {bps/100:.2f}% either way.")
        if reg == "explosive":
            parts.append("Big swings likely — trade small or wait.")
        elif reg == "quiet":
            parts.append("Very calm — fade extremes rather than chase breakouts.")

    if pat_lean:
        parts.append(f"Chart patterns lean {'bullish' if pat_lean > 0 else 'bearish'}.")

    tradeable = act and not news_cal.get("blackout") and reg != "explosive"
    side = meta_p.get("primary_side", "?").upper()
    if tradeable:
        verdict = f"Lean {side} — filter is confident, no news blackout, volatility {reg}"
    elif news_cal.get("blackout") or reg == "explosive":
        verdict = "Stand aside"
    else:
        verdict = "No trade — not confident enough right now"
    return {"verdict": verdict, "notes": parts, "tradeable": tradeable}
