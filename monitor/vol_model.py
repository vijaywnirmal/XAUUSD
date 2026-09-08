"""Load monitor/vol_model.json -> predict next-~1h realised volatility + regime."""
from __future__ import annotations

import json
import math
import os

from monitor import config as C

_VOL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vol_model.json")
_m: dict | None = None


def _load():
    global _m
    if _m is None:
        _m = json.load(open(_VOL_PATH)) if os.path.exists(_VOL_PATH) else {}
    return _m


def predict(feat: dict) -> dict:
    m = _load()
    if not m:
        return {"available": False, "detail": "no vol_model.json - run `python -m monitor.calibrate`"}
    z = m["intercept"]
    used = 0
    for name, coef, mu, sd in zip(m["cols"], m["coef"], m["mean"], m["std"]):
        v = feat.get(name)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        z += coef * ((v - mu) / (sd or 1.0))
        used += 1
    log_rv = z
    rv = math.exp(log_rv)
    lo, hi = m["terciles"]                              # thresholds on log_rv
    regime = "quiet" if log_rv < lo else "explosive" if log_rv > hi else "normal"
    # percentile of this prediction vs the training distribution of predictions
    grid = m.get("pred_grid", [])
    pct = (sum(1 for g in grid if g <= log_rv) / len(grid)) if grid else None
    return {
        "available": True,
        "rv_pred": round(rv, 6),
        "rv_pred_bps": round(rv * 1e4, 1),             # ~ 1h 1-sigma move in bps
        "regime": regime,
        "percentile": round(pct, 3) if pct is not None else None,
        "model_r2_oos": m.get("metrics", {}).get("oos_r2"),
        "tercile_acc_oos": m.get("metrics", {}).get("oos_tercile_acc"),
        "horizon": f"~{m['horizon_bars'] * 5} min",
        "note": "3-way regime classifier ~"
                f"{int((m.get('metrics', {}).get('oos_tercile_acc') or 0) * 100)}% right OOS "
                "(33% = chance); the exact bps figure is rough.",
    }
