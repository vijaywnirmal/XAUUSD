"""Unit tests for the pure monitor bits (no network, no MT5, no PG)."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from monitor import news_calendar as NC
from monitor import features as F
from monitor import patterns as P
from monitor import direction as D
from monitor import vol_model as V
from monitor import calendar_history as CH


def _synth_bars(n=400, start="2025-06-10 08:00", drift=0.0, seed=1):
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start, periods=n, freq="5min", tz="UTC")
    px = 2000 + np.cumsum(rng.normal(drift, 1.0, n))
    return pd.DataFrame({"ts": ts, "open": px, "high": px + 0.6,
                         "low": px - 0.6, "close": px})


# --- calendar blackout ------------------------------------------------------
def test_blackout_window(monkeypatch):
    t0 = datetime(2025, 6, 18, 18, 0, tzinfo=timezone.utc)          # a fake FOMC
    NC._cache = [{
        "title": "FOMC Statement", "country": "USD", "impact": "High",
        "is_high": True, "when_utc": t0.isoformat(),
    }]
    NC._fetched_at = 9e18                                           # skip refresh
    inside, why = NC.in_blackout(t0.replace(minute=55, hour=17))    # 5 min before
    assert inside and "FOMC" in why
    outside, _ = NC.in_blackout(t0.replace(hour=16))                # 2h before
    assert not outside
    assert 0 < NC.minutes_to_next_high(t0.replace(hour=17)) <= 60


def test_us_forced_high_but_not_foreign_cpi():
    raw = [
        {"title": "German Final CPI m/m", "country": "EUR", "impact": "Low",
         "date": "2025-06-10T06:00:00+00:00"},
        {"title": "CPI m/m", "country": "USD", "impact": "Low",
         "date": "2025-06-11T12:30:00+00:00"},
    ]
    parsed = NC._parse(raw)
    by_title = {e["title"]: e for e in parsed}
    assert by_title["German Final CPI m/m"]["is_high"] is False
    assert by_title["CPI m/m"]["is_high"] is True


# --- features -------------------------------------------------------------
def test_feature_frame_shapes_and_no_lookahead():
    df = _synth_bars(400)
    f = F.feature_frame(df)
    assert len(f) == len(df)
    for c in F.MODEL_COLS:
        assert c in f.columns
    # last row's ret_1h must equal close[-1]/close[-13]-1 (no future info)
    exp = df["close"].iloc[-1] / df["close"].iloc[-13] - 1
    assert abs(f["ret_1h"].iloc[-1] - exp) < 1e-9


def test_compute_returns_json_safe():
    out = F.compute(_synth_bars(300))
    assert isinstance(out["rsi"], float) and 0 <= out["rsi"] <= 100
    assert "session" in out


# --- patterns ----------------------------------------------------------------
def test_ema5_detach_direction():
    df = _synth_bars(120, drift=0.0)
    # force the last candle far above its EMA5 -> should fire a SHORT (fade)
    df.loc[df.index[-1], ["open", "high", "low", "close"]] = [2100, 2101, 2099, 2100]
    pats = {p["name"]: p for p in P.evaluate(df)}
    assert pats["ema5_detach"]["firing"] and pats["ema5_detach"]["direction"] == -1


def test_net_lean_sign():
    pats = [{"name": "ema5_detach", "firing": True, "direction": 1},
            {"name": "rsi_extreme", "firing": True, "direction": 1},
            {"name": "ny_orb", "firing": False, "direction": 0}]
    assert P.net_lean(pats) == 3


# --- direction (uses whatever model.json exists; tolerate absence) ----------
def test_direction_predict_contract():
    out = D.predict(F.compute(_synth_bars(320)))
    assert "available" in out
    if out["available"]:
        assert 0.0 <= out["p_up"] <= 1.0
        assert out["lean"] in ("up", "down", "neutral")
        assert "trust_now" in out and "session_auc" in out


# --- event proximity (calendar history) -----------------------------------
def test_event_proximity_math():
    import pandas as pd
    # 2024-06-12 18:00 UTC is a hardcoded FOMC
    t = pd.DatetimeIndex(["2024-06-12T16:30:00Z", "2024-06-12T18:10:00Z"])
    ef = CH.event_features_frame(t)
    r0, r1 = ef.iloc[0], ef.iloc[1]
    assert abs(r0["ev_mins_to"] - 90) < 1 and r0["ev_next_weight"] == 3 and r0["ev_pre2h"] == 1
    assert abs(r1["ev_mins_from"] - 10) < 1 and r1["ev_post2h"] == 1 and r1["ev_window60"] == 1


def test_event_features_capped_far_out():
    import pandas as pd
    ef = CH.event_features_frame(pd.DatetimeIndex(["2024-07-04T00:00:00Z"]))  # US holiday, no event near
    assert ef.iloc[0]["ev_mins_to"] <= 1440 and ef.iloc[0]["ev_mins_from"] <= 1440


# --- volatility model -----------------------------------------------------
def test_vol_predict_contract():
    out = V.predict(F.compute(_synth_bars(340)))
    assert "available" in out
    if out["available"]:
        assert out["regime"] in ("quiet", "normal", "explosive")
        assert out["rv_pred_bps"] > 0


def test_feature_frame_has_new_cols():
    f = F.feature_frame(_synth_bars(360))
    for c in F.EVENT_COLS + ["rv_1h", "rv_15m", "vol_seasonality"]:
        assert c in f.columns
    assert set(F.EVENT_COLS).issubset(set(F.MODEL_COLS))
    assert set(F.EVENT_COLS).issubset(set(F.VOL_COLS))
