"""
News sentiment for gold.

Primary: GDELT DOC 2.0 `timelinetone` (free, no key, 15-min resolution) - the
average tone of global coverage matching a gold query. We derive:
  tone_now        latest 15-min average tone
  tone_mean_24h   rolling mean
  tone_z          (tone_now - mean) / std   -> "unusually negative/positive coverage"
  vol_now / vol_z article volume + its z-score  -> "news is spiking"

Optional: Finnhub /news-sentiment or Alpha Vantage NEWS_SENTIMENT if a key is set
(added to the payload under `finnhub` / `alphavantage`, not required).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np
import requests

from monitor import config

_cache: dict = {}
_fetched_at = 0.0
_cooldown_until = 0.0                                   # set after a 429


def _gdelt_series(mode: str) -> list[tuple[str, float]]:
    params = {"query": config.GDELT_QUERY, "mode": mode, "format": "json", "timespan": "3d"}
    r = requests.get(config.GDELT_URL, params=params,
                     headers={"User-Agent": "xauusd-monitor/1.0"}, timeout=25)
    if r.status_code == 429 or not r.text.strip().startswith("{"):
        raise ValueError(f"GDELT throttled/non-JSON ({r.status_code})")
    r.raise_for_status()
    data = r.json().get("timeline", [])
    if not data:
        return []
    return [(p["date"], float(p["value"])) for p in data[0].get("data", [])]


def refresh() -> bool:
    global _cache, _fetched_at, _cooldown_until
    if time.time() < _cooldown_until:
        return bool(_cache)
    try:
        tone = _gdelt_series("timelinetone")            # single call - lighter on the rate limit
        vol = []
    except (requests.RequestException, ValueError, KeyError):
        _cooldown_until = time.time() + 1800            # back off 30 min on throttle
        return bool(_cache)
    if not tone:
        return bool(_cache)
    tv = np.array([v for _, v in tone], float)
    vv = np.array([v for _, v in vol], float) if vol else np.array([np.nan])
    _cache = {
        "tone_now": round(float(tv[-1]), 3),
        "tone_mean_24h": round(float(tv[-96:].mean()), 3),
        "tone_std_24h": round(float(tv[-96:].std() or 1.0), 3),
        "tone_z": round(float((tv[-1] - tv[-96:].mean()) / (tv[-96:].std() or 1.0)), 2),
        "vol_now": None if np.isnan(vv[-1]) else round(float(vv[-1]), 3),
        "vol_z": None if len(vv) < 10 or np.isnan(vv[-1]) else
                 round(float((vv[-1] - vv[-96:].mean()) / (vv[-96:].std() or 1.0)), 2),
        "last_point_utc": tone[-1][0],
        "n_points": len(tv),
        "source": "gdelt",
    }
    _add_optional()
    _fetched_at = time.time()
    return True


def _add_optional():
    if config.FINNHUB_API_KEY:
        try:
            r = requests.get("https://finnhub.io/api/v1/news-sentiment",
                             params={"symbol": "GLD", "token": config.FINNHUB_API_KEY}, timeout=15)
            if r.ok:
                j = r.json()
                _cache["finnhub"] = {"bullish_pct": j.get("sentiment", {}).get("bullishPercent"),
                                     "articles_week": j.get("buzz", {}).get("articlesInLastWeek")}
        except requests.RequestException:
            pass
    if config.ALPHAVANTAGE_API_KEY:
        try:
            r = requests.get("https://www.alphavantage.co/query",
                             params={"function": "NEWS_SENTIMENT", "topics": "economy_monetary,financial_markets",
                                     "tickers": "FOREX:USD", "limit": 50, "apikey": config.ALPHAVANTAGE_API_KEY},
                             timeout=20)
            if r.ok:
                feed = r.json().get("feed", [])
                scores = [float(a["overall_sentiment_score"]) for a in feed if "overall_sentiment_score" in a]
                if scores:
                    _cache["alphavantage"] = {"mean_sentiment": round(sum(scores) / len(scores), 3),
                                              "n": len(scores)}
        except (requests.RequestException, ValueError):
            pass


def summary(force: bool = False) -> dict:
    global _fetched_at
    if force or not _cache or time.time() - _fetched_at > config.NEWS_REFRESH_SECONDS:
        refresh()
    if not _cache:
        return {"available": False, "source": "gdelt"}
    return {"available": True, **_cache,
            "age_seconds": round(time.time() - _fetched_at, 1) if _fetched_at else None}
