"""Dedicated London-continuation model: at ~13:00 UTC, P(the 13:00 -> 17:00 UTC
move is up). This is the one session where the direction signal showed real OOS
skill (AUC ~0.62). Loads monitor/london_model.json."""
from __future__ import annotations

import json
import math
import os

from monitor import config as C

_PATH = C.MODEL_PATH.replace("model.json", "london_model.json")
_m: dict | None = None


def _load():
    global _m
    if _m is None:
        _m = json.load(open(_PATH)) if os.path.exists(_PATH) else {}
    return _m


def predict(feat: dict) -> dict:
    m = _load()
    if not m:
        return {"available": False, "detail": "no london_model.json - run python -m monitor.calibrate"}
    z = m["intercept"]
    drivers = []
    for name, coef, mu, sd in zip(m["cols"], m["coef"], m["mean"], m["std"]):
        v = feat.get(name)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        contrib = coef * ((v - mu) / (sd or 1.0))
        z += contrib
        drivers.append((name, round(contrib, 3)))
    p_up = 1.0 / (1.0 + math.exp(-z))
    mod = feat.get("mod")
    at_decision = mod is not None and 750 <= mod <= 800          # ~12:30-13:20 UTC
    drivers.sort(key=lambda t: -abs(t[1]))
    oos = m.get("metrics", {}).get("oos_auc")
    reliable = oos is not None and oos >= 0.52
    return {
        "available": True,
        "p_up": round(p_up, 4),
        "lean": "up" if p_up > 0.55 else "down" if p_up < 0.45 else "neutral",
        "at_decision_time": bool(at_decision),
        "reliable": bool(reliable),
        "horizon": "13:00 -> 17:00 UTC",
        "top_drivers": drivers[:4],
        "oos_auc": oos,
        "note": (f"EXPERIMENTAL - failed OOS validation (AUC {oos}); shown for transparency, do not trade it."
                 if not reliable else
                 ("at the 13:00 UTC decision point" if at_decision
                  else "indicative only - designed for the 13:00 UTC bar")),
    }
