"""Load monitor/model.json and turn a live feature row into P(up) + drivers."""
from __future__ import annotations

import json
import math
import os

from monitor import config as C

_model: dict | None = None


def _load():
    global _model
    if _model is None:
        if not os.path.exists(C.MODEL_PATH):
            _model = {}
        else:
            with open(C.MODEL_PATH) as f:
                _model = json.load(f)
    return _model


def predict(feat: dict) -> dict:
    m = _load()
    if not m:
        return {"available": False, "detail": "no model.json - run `python -m monitor.calibrate`"}
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
    drivers.sort(key=lambda t: -abs(t[1]))
    return {
        "available": True,
        "p_up": round(p_up, 4),
        "lean": "up" if p_up > 0.55 else "down" if p_up < 0.45 else "neutral",
        "confidence": round(abs(p_up - 0.5) * 2, 3),         # 0..1
        "horizon": f"~{m['horizon_bars'] * 5} min",
        "top_drivers": drivers[:5],
        "model_oos_auc": m.get("metrics", {}).get("oos_auc"),
        "caveat": "logistic lean, OOS AUC "
                  f"{m.get('metrics', {}).get('oos_auc')} - treat as a faint tilt, not a signal.",
    }
