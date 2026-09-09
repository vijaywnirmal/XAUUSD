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
from monitor import meta as MET
from monitor import london as LON
from monitor import outcomes as OUT
from monitor import candles as CND


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


# --- candlestick patterns -------------------------------------------------
def test_candles_bullish_engulfing():
    import pandas as pd
    ts = pd.date_range("2025-06-10 08:00", periods=6, freq="5min", tz="UTC")
    #                             prior=down bar        current: opens <= prior close, closes >= prior open
    o = [100, 100, 100, 101, 102.0, 101.3]
    c = [100, 100, 100, 100.5, 101.4, 102.2]
    h = [100.1, 100.1, 100.1, 101.1, 102.1, 102.3]
    l = [99.9, 99.9, 99.9, 100.4, 101.3, 101.2]
    df = pd.DataFrame({"ts": ts, "open": o, "high": h, "low": l, "close": c})
    names = {d["name"]: d for d in CND.evaluate(df)}
    assert "bullish_engulfing" in names and names["bullish_engulfing"]["direction"] == 1


def test_candles_doji_and_inside_bar():
    import pandas as pd, numpy as np
    ts = pd.date_range("2025-06-10 08:00", periods=6, freq="5min", tz="UTC")
    # wide prior bar, then a tiny doji fully inside it
    o = [100, 100, 100, 100, 99.0, 100.0]
    c = [100, 100, 100, 100, 101.0, 100.02]
    h = [100.1, 100.1, 100.1, 100.1, 101.2, 100.3]
    l = [99.9, 99.9, 99.9, 99.9, 98.8, 99.7]
    df = pd.DataFrame({"ts": ts, "open": o, "high": h, "low": l, "close": c})
    names = {d["name"] for d in CND.evaluate(df)}
    assert "doji" in names and "inside_bar" in names


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
    for c in F.EVENT_COLS + F.XA_COLS + ["rv_1h", "rv_15m", "vol_seasonality"]:
        assert c in f.columns
    assert set(F.EVENT_COLS).issubset(set(F.MODEL_COLS))
    assert set(F.XA_COLS).issubset(set(F.MODEL_COLS))


def test_crossasset_join_no_lookahead():
    import pandas as pd, numpy as np
    ts = pd.date_range("2024-06-10 08:00", periods=200, freq="5min", tz="UTC")
    eur = pd.DataFrame({"close": 1.08 + np.cumsum(np.random.default_rng(2).normal(0, 1e-4, 260))},
                       index=pd.date_range("2024-06-10 06:00", periods=260, freq="5min", tz="UTC"))
    jpy = pd.DataFrame({"close": 157 + np.cumsum(np.random.default_rng(3).normal(0, 1e-2, 260))},
                       index=eur.index)
    px = 2300 + np.cumsum(np.random.default_rng(1).normal(0, 1, 200))
    df = pd.DataFrame({"ts": ts, "open": px, "high": px + .5, "low": px - .5, "close": px})
    f = F.feature_frame(df, {"EURUSD": eur, "USDJPY": jpy})
    assert f["xa_usd_60m"].notna().sum() > 100          # populated
    assert f["xa_usd_60m"].abs().max() < 0.05            # sane magnitude


def test_meta_and_london_contracts():
    feat = F.compute(_synth_bars(340))
    for out in (MET.predict(feat), LON.predict(feat)):
        assert "available" in out
    m = MET.predict(feat)
    if m["available"]:
        assert 0.0 <= m["p_correct"] <= 1.0 and isinstance(m["act"], bool)
    l = LON.predict(feat)
    if l["available"]:
        assert 0.0 <= l["p_up"] <= 1.0 and "at_decision_time" in l


def test_outcomes_record_resolve(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(OUT, "_PEND", str(tmp_path / "pend.csv"))
    monkeypatch.setattr(OUT, "_OUT", str(tmp_path / "out.csv"))
    monkeypatch.setattr(OUT, "_HORIZON_MIN", 60)
    t0 = datetime(2025, 6, 10, 12, 0, tzinfo=timezone.utc)
    OUT.record(t0, 2000.0, {"p_up": 0.62}, {"p_correct": 0.6, "act": True}, {"p_up": 0.55, "at_decision_time": True})
    assert OUT.resolve(t0 + timedelta(minutes=30), 2001.0) == 0        # not mature
    assert OUT.resolve(t0 + timedelta(minutes=61), 2005.0) == 1        # matured, price up
    rows = OUT._read(OUT._OUT, OUT._OF)
    assert rows[0]["realised_up"] == "1" and rows[0]["dir_hit"] == "1"


def test_live_auc_thresholds(tmp_path, monkeypatch):
    import csv
    monkeypatch.setattr(OUT, "_OUT", str(tmp_path / "out.csv"))
    # 25 rows -> below MIN_FOR_ANY (30): nothing reported
    def _mkrows(n, up_frac=0.5):
        rows = []
        for i in range(n):
            up = 1 if i < n * up_frac else 0
            rows.append({**{k: "" for k in OUT._OF}, "p_up": 0.55, "realised_up": up,
                         "dir_hit": int((0.55 >= 0.5) == bool(up)), "meta_act": "1",
                         "london_p_up": "", "london_decision": "0"})
        with open(OUT._OUT, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=OUT._OF); w.writeheader(); w.writerows(rows)
    _mkrows(25)
    assert OUT.live_auc()["available"] is False
    # 60 rows -> hit-rate shows, but preliminary flag off (>=50) and AUC still hidden (<80)
    _mkrows(60, up_frac=0.5)
    la = OUT.live_auc()
    assert la["available"] and la["direction_hit"] is not None
    assert la["direction_auc"] is None and la["direction_auc_note"]
    # 120 rows, balanced -> AUC now reported
    _mkrows(120, up_frac=0.5)
    assert OUT.live_auc()["direction_auc"] is not None
