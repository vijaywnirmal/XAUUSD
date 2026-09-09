"""
Live prediction tracking. Each poll the engine calls record(); once a prediction
is `horizon` old it is resolved against realised price and appended to
monitor/logs/outcomes.csv. live_auc() then reports the TRUE live hit-rate / AUC
- the only number that matters.

Files (both gitignored):
  logs/pred_pending.csv   - predictions not yet mature
  logs/outcomes.csv       - resolved: prediction + realised direction
"""
from __future__ import annotations

import csv
import os
from datetime import datetime, timezone

from monitor import config as C

_PEND = os.path.join(C.LOG_DIR, "pred_pending.csv")
_OUT = os.path.join(C.LOG_DIR, "outcomes.csv")
_PF = ["ts", "due_ts", "price", "p_up", "p_correct", "meta_act", "london_p_up", "london_decision"]
_OF = _PF + ["resolved_ts", "future_price", "realised_up", "dir_hit", "london_hit"]

_HORIZON_MIN = C.PREDICT_HORIZON_BARS * 5


def _read(path, fields):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def record(now: datetime, price: float, direction: dict, meta: dict, london: dict) -> None:
    if price is None:
        return
    pend = _read(_PEND, _PF)
    # de-dupe: at most one pending prediction per 5-min bar
    key = now.replace(second=0, microsecond=0).isoformat()
    if pend and pend[-1]["ts"][:16] == key[:16]:
        return
    due = now.timestamp() + _HORIZON_MIN * 60
    pend.append({
        "ts": now.isoformat(timespec="seconds"),
        "due_ts": datetime.fromtimestamp(due, timezone.utc).isoformat(timespec="seconds"),
        "price": round(price, 3),
        "p_up": direction.get("p_up"), "p_correct": meta.get("p_correct"),
        "meta_act": int(bool(meta.get("act"))),
        "london_p_up": london.get("p_up"), "london_decision": int(bool(london.get("at_decision_time"))),
    })
    _write(_PEND, _PF, pend[-2000:])


def resolve(now: datetime, price: float) -> int:
    """Resolve any pending prediction now past its due time, using the current
    price as the realised future price. Returns how many were resolved."""
    if price is None:
        return 0
    pend = _read(_PEND, _PF)
    if not pend:
        return 0
    still, done = [], _read(_OUT, _OF)
    n = 0
    for r in pend:
        try:
            due = datetime.fromisoformat(r["due_ts"])
        except ValueError:
            continue
        if now < due:
            still.append(r)
            continue
        p0 = float(r["price"])
        up = 1 if price > p0 else 0
        pu = float(r["p_up"]) if r["p_up"] not in ("", None) else None
        lpu = float(r["london_p_up"]) if r["london_p_up"] not in ("", None) else None
        done.append({**r, "resolved_ts": now.isoformat(timespec="seconds"),
                     "future_price": round(price, 3), "realised_up": up,
                     "dir_hit": None if pu is None else int((pu >= 0.5) == bool(up)),
                     "london_hit": None if lpu is None else int((lpu >= 0.5) == bool(up))})
        n += 1
    _write(_PEND, _PF, still)
    if n:
        _write(_OUT, _OF, done[-5000:])
    return n


MIN_FOR_ANY = 30            # below this: don't report anything, still noise
MIN_FOR_HIT = 50           # hit-rate is "preliminary" until here
MIN_FOR_AUC = 80           # AUC needs a real sample...
MIN_CLASS_FOR_AUC = 20     # ...with enough of BOTH up and down outcomes
RECENT_WINDOW = 150        # also report the last N, for regime drift


def _hit_rate(rows, mask=None):
    v = [int(r["dir_hit"]) for r in rows
         if r["dir_hit"] not in ("", None) and (mask is None or mask(r))]
    return (round(sum(v) / len(v), 3), len(v)) if v else (None, 0)


def _auc(rows, pcol, ycol, mask=None):
    from sklearn.metrics import roc_auc_score
    p, y = [], []
    for r in rows:
        if mask and not mask(r):
            continue
        if r.get(pcol) in ("", None) or r.get(ycol) in ("", None):
            continue
        p.append(float(r[pcol])); y.append(int(float(r[ycol])))
    n = len(y)
    n_pos, n_neg = sum(y), n - sum(y)
    if n < MIN_FOR_AUC or n_pos < MIN_CLASS_FOR_AUC or n_neg < MIN_CLASS_FOR_AUC:
        return None, n, f"AUC hidden - need {MIN_FOR_AUC}+ with {MIN_CLASS_FOR_AUC}+ of each outcome (have {n}: {n_pos} up / {n_neg} down)"
    return round(float(roc_auc_score(y, p)), 4), n, None


def live_auc() -> dict:
    rows = _read(_OUT, _OF)
    n = len(rows)
    if n < MIN_FOR_ANY:
        return {"available": False, "n": n,
                "detail": f"{n} calls graded - too few to read anything (need {MIN_FOR_ANY}+, "
                          f"and {MIN_FOR_HIT}+ for a hit-rate, {MIN_FOR_AUC}+ for AUC)"}

    recent = rows[-RECENT_WINDOW:]
    all_hit, all_n = _hit_rate(rows)
    rec_hit, rec_n = _hit_rate(recent)
    meta_hit, meta_n = _hit_rate(rows, mask=lambda r: r["meta_act"] == "1")
    meta_hit_rec, _ = _hit_rate(recent, mask=lambda r: r["meta_act"] == "1")
    dir_auc, dir_auc_n, dir_auc_msg = _auc(rows, "p_up", "realised_up")
    lon_auc, lon_auc_n, _ = _auc(rows, "london_p_up", "realised_up",
                                 mask=lambda r: r["london_decision"] == "1")

    preliminary = all_n < MIN_FOR_HIT
    return {
        "available": True,
        "n_resolved": n,
        "preliminary": preliminary,
        "direction_hit": all_hit, "direction_hit_n": all_n,
        "direction_hit_recent": rec_hit, "recent_n": rec_n,
        "meta_selected_hit": meta_hit, "meta_selected_n": meta_n,
        "meta_selected_hit_recent": meta_hit_rec,
        "direction_auc": dir_auc, "direction_auc_note": dir_auc_msg,
        "london_auc": lon_auc, "london_auc_n": lon_auc_n,
        "note": ("PRELIMINARY - too few calls to trust; treat as a sanity check only"
                 if preliminary else
                 "cumulative + last %d; still needs weeks across sessions/regimes to be conclusive" % RECENT_WINDOW),
    }
