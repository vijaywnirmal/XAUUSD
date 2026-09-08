"""Recursively convert numpy/pandas objects into plain JSON-safe Python values."""
import math
import numpy as np
import pandas as pd


def safe(obj):
    if obj is None:
        return None
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    if isinstance(obj, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(obj).isoformat()
    if isinstance(obj, dict):
        return {str(k): safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [safe(v) for v in obj]
    if isinstance(obj, pd.Series):
        return [safe(v) for v in obj.tolist()]
    if isinstance(obj, pd.DataFrame):
        return [safe(r) for r in obj.to_dict(orient="records")]
    if isinstance(obj, np.ndarray):
        return [safe(v) for v in obj.tolist()]
    if isinstance(obj, str):
        return obj
    return obj
