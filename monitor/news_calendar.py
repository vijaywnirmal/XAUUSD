"""
ForexFactory weekly economic calendar (free, no key).

Exposes upcoming scheduled events, minutes-to-next-high-impact, and a blackout
flag for the window around High-impact USD releases (FOMC / NFP / CPI / ...).
Cached in-process; refresh() re-fetches.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import requests

from monitor import config

_cache: list[dict] = []
_fetched_at = 0.0


def _parse(raw: list[dict]) -> list[dict]:
    out = []
    for e in raw:
        try:
            # feed dates look like "2026-09-07T02:00:00-04:00"
            dt = datetime.fromisoformat(e["date"]).astimezone(timezone.utc)
        except (KeyError, ValueError):
            continue
        title = e.get("title", "")
        country = e.get("country", "")
        impact = e.get("impact", "") or ""
        # ALWAYS_HIGH terms count only for US events (FOMC/NFP/US CPI etc.)
        us_forced = country in ("USD", "") and any(k.lower() in title.lower() for k in config.ALWAYS_HIGH)
        high = impact == "High" or us_forced
        out.append({
            "title": title, "country": country, "impact": impact,
            "is_high": high, "when_utc": dt.isoformat(),
            "forecast": e.get("forecast", ""), "previous": e.get("previous", ""),
        })
    out.sort(key=lambda x: x["when_utc"])
    return out


def refresh() -> bool:
    global _cache, _fetched_at
    try:
        r = requests.get(config.FF_CALENDAR_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        r.raise_for_status()
        _cache = _parse(r.json())
        _fetched_at = time.time()
        return True
    except (requests.RequestException, ValueError):
        return False


def _ensure():
    if not _cache or time.time() - _fetched_at > 3600:
        refresh()


def upcoming(now: datetime | None = None, hours: int = 24) -> list[dict]:
    _ensure()
    now = now or datetime.now(timezone.utc)
    hi = now + timedelta(hours=hours)
    return [e for e in _cache if now <= datetime.fromisoformat(e["when_utc"]) <= hi]


def next_high_impact(now: datetime | None = None) -> dict | None:
    _ensure()
    now = now or datetime.now(timezone.utc)
    for e in _cache:
        if e["is_high"] and datetime.fromisoformat(e["when_utc"]) >= now:
            return e
    return None


def minutes_to_next_high(now: datetime | None = None) -> float | None:
    e = next_high_impact(now)
    if e is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (datetime.fromisoformat(e["when_utc"]) - now).total_seconds() / 60.0


def in_blackout(now: datetime | None = None) -> tuple[bool, str]:
    """True inside +/- window of a High-impact event in a BLACKOUT currency."""
    _ensure()
    now = now or datetime.now(timezone.utc)
    for e in _cache:
        if not e["is_high"]:
            continue
        if e["country"] not in config.BLACKOUT_CURRENCIES and not any(
            k.lower() in e["title"].lower() for k in config.ALWAYS_HIGH
        ):
            continue
        t = datetime.fromisoformat(e["when_utc"])
        if t - timedelta(minutes=config.BLACKOUT_BEFORE_MIN) <= now <= t + timedelta(minutes=config.BLACKOUT_AFTER_MIN):
            return True, f"{e['title']} ({e['country']}) at {e['when_utc'][11:16]}Z"
    return False, ""


def summary(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    black, why = in_blackout(now)
    nxt = next_high_impact(now)
    return {
        "blackout": black, "blackout_reason": why,
        "minutes_to_next_high": minutes_to_next_high(now),
        "next_high": nxt,
        "upcoming_24h": [
            {"in_min": round((datetime.fromisoformat(e["when_utc"]) - now).total_seconds() / 60),
             "title": e["title"], "country": e["country"], "impact": e["impact"]}
            for e in upcoming(now, 24) if e["impact"] in ("High", "Medium")
        ][:12],
        "source": "forexfactory", "events_loaded": len(_cache),
    }
