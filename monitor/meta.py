"""Meta-label model: P(the direction call is correct). Trade only when high.
Loads monitor/meta_model.joblib (a GBM + the direction logistic coefficients)."""
from __future__ import annotations

import math
import os

from monitor import config as C

_META_PATH = C.MODEL_PATH.replace("model.json", "meta_model.joblib")
THRESHOLD = 0.58
_m = None


def _load():
    global _m
    if _m is None:
        if not os.path.exists(_META_PATH):
            _m = {}
        else:
            import joblib
            _m = joblib.load(_META_PATH)
    return _m


def _p_dir(feat, m):
    z = m["dir_intercept"]
    for name, coef, mu, sd in zip(m["dir_cols"], m["dir_coef"], m["dir_mu"], m["dir_sd"]):
        v = feat.get(name)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        z += coef * ((v - mu) / (sd or 1.0))
    return 1.0 / (1.0 + math.exp(-z))


def predict(feat: dict) -> dict:
    m = _load()
    if not m:
        return {"available": False, "detail": "no meta_model.joblib - run python -m monitor.calibrate"}
    import numpy as np
    p_dir = _p_dir(feat, m)
    row = {}
    for c in m["cols"]:
        if c == "_pdir":
            row[c] = p_dir
        elif c == "_pdir_conf":
            row[c] = abs(p_dir - 0.5)
        else:
            v = feat.get(c)
            row[c] = np.nan if v is None else v
    import pandas as pd
    X = pd.DataFrame([[row[c] for c in m["cols"]]], columns=m["cols"], dtype=float)
    p_correct = float(m["model"].predict_proba(X)[0, 1])
    side = "up" if p_dir >= 0.5 else "down"
    return {
        "available": True,
        "p_dir": round(p_dir, 4),
        "primary_side": side,
        "p_correct": round(p_correct, 4),
        "threshold": THRESHOLD,
        "act": p_correct >= THRESHOLD,
        "recommendation": (f"take {side}" if p_correct >= THRESHOLD else "skip - low confidence"),
    }
