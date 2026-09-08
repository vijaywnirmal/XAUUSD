"""
Persistence for strategies built through the Strategy Builder (custom
indicator rules), so a composed strategy survives a page refresh or server
restart instead of living only in the browser tab's React state.

Storage: a single JSON file on disk (webapp/backend/data/saved_strategies.json).
This is a local, single-user tool (per the project's original scope), so a
flat file is enough — no DB migration needed for this.
"""
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_STORE_PATH = os.path.join(_DATA_DIR, "saved_strategies.json")
_lock = threading.Lock()


def _load_all() -> dict[str, dict]:
    if not os.path.exists(_STORE_PATH):
        return {}
    with open(_STORE_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_all(records: dict[str, dict]) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp_path = _STORE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    os.replace(tmp_path, _STORE_PATH)


def list_saved() -> list[dict]:
    with _lock:
        records = _load_all()
    out = [
        {k: v for k, v in r.items() if k != "spec"}
        for r in records.values()
    ]
    out.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    return out


def get_saved(strategy_id: str) -> Optional[dict]:
    with _lock:
        records = _load_all()
    return records.get(strategy_id)


def save_strategy(name: str, timeframe: str, split: Optional[str], start: Optional[str],
                   end: Optional[str], spec: dict[str, Any], strategy_id: Optional[str] = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        records = _load_all()
        if strategy_id and strategy_id in records:
            record = records[strategy_id]
            record.update(name=name, timeframe=timeframe, split=split,
                          start=start, end=end, spec=spec, updated_at=now)
        else:
            strategy_id = str(uuid.uuid4())
            record = {
                "id": strategy_id, "name": name, "timeframe": timeframe,
                "split": split, "start": start, "end": end, "spec": spec,
                "created_at": now, "updated_at": now,
            }
            records[strategy_id] = record
        _save_all(records)
    return record


def delete_saved(strategy_id: str) -> bool:
    with _lock:
        records = _load_all()
        if strategy_id not in records:
            return False
        del records[strategy_id]
        _save_all(records)
    return True
