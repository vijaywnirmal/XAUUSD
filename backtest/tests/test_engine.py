"""
Hand-checked correctness tests for the backtester. Run:
    python -m backtest.tests.test_engine
Exits non-zero on any failure.
"""

import numpy as np
import pandas as pd

from backtest.engine import Backtester, BTConfig


def _bars(rows):
    # rows: list of (open, high, low, close, spread_mean)
    ts = pd.date_range("2024-01-02 13:00", periods=len(rows), freq="5min", tz="UTC")
    a = np.array(rows, float)
    return pd.DataFrame({"ts": ts, "open": a[:, 0], "high": a[:, 1], "low": a[:, 2],
                         "close": a[:, 3], "spread_mean": a[:, 4]})


def approx(a, b, tol=1e-6):
    assert abs(a - b) < tol, f"{a} != {b}"


def test_hand_long_trade():
    # signal on bar 0 -> enter bar 1 open; exit signal on bar 2 -> exit bar 3 open
    df = _bars([
        (100.0, 100.0, 100.0, 100.0, 0.20),   # 0 signal
        (100.0, 101.0, 100.0, 101.0, 0.20),   # 1 entry @ open (mid) = 100.00
        (101.0, 102.0, 101.0, 102.0, 0.20),   # 2 exit signal
        (103.0, 103.0, 103.0, 103.0, 0.20),   # 3 exit @ open (mid) = 103.00
        (103.0, 103.0, 103.0, 103.0, 0.20),
    ])
    sig = {"long_entry": np.array([1, 0, 0, 0, 0], bool),
           "short_entry": np.zeros(5, bool),
           "exit_signal": np.array([0, 0, 1, 0, 0], bool)}
    cfg = BTConfig(size_lots=0.01, contract_size=100.0, tick_size=0.01,
                   slippage_ticks=1.0, commission_roundtrip_per_lot=6.0,
                   initial_equity=1000.0, allow_short=False)
    res = Backtester(cfg).run(df, sig)
    tr = res["trades"]
    assert len(tr) == 1, tr
    t = tr.iloc[0]
    approx(t.entry_mid, 100.00)                                     # mid fill at t+1 open
    approx(t.exit_mid, 103.00)
    assert t.entry_i == 1 and t.exit_i == 3, (t.entry_i, t.exit_i)  # look-ahead: t+1 fills
    gross = 1 * (103.00 - 100.00) * 0.01 * 100.0                    # = 3.00
    cost = ((0.20 / 2 + 0.20 / 2) + 2 * 0.01) * 0.01 * 100.0 + 6.0 * 0.01  # spread+slip+comm
    approx(t.gross_pnl, gross)
    approx(t.cost, cost)
    approx(t.net_pnl, gross - cost)
    approx(res["equity"].iloc[-1], 1000.0 + gross - cost)
    print(f"  hand long trade: gross={gross:.4f} cost={cost:.4f} net={gross-cost:.4f}  OK")


def test_stop_is_pessimistic():
    # bar range touches BOTH stop and target -> stop must win
    df = _bars([
        (100.0, 100.0, 100.0, 100.0, 0.00),
        (100.0, 100.0, 100.0, 100.0, 0.00),   # entry @ 100
        (100.0, 105.0, 95.0, 100.0, 0.00),    # touches +5 target and -5 stop
        (100.0, 100.0, 100.0, 100.0, 0.00),
    ])
    sig = {"long_entry": np.array([1, 0, 0, 0], bool),
           "short_entry": np.zeros(4, bool), "exit_signal": np.zeros(4, bool),
           "stop_dist": np.full(4, 3.0), "target_dist": np.full(4, 3.0)}
    res = Backtester(BTConfig(slippage_ticks=0, commission_roundtrip_per_lot=0,
                              allow_short=False)).run(df, sig)
    t = res["trades"].iloc[0]
    assert t.exit_reason == "stop", t.exit_reason
    approx(t.exit_mid, 97.0)
    print("  stop-before-target pessimism: OK")


def test_costs_make_random_lose():
    from backtest.strategy import random_entries
    ts = pd.date_range("2020-01-01", periods=20000, freq="5min", tz="UTC")
    rng = np.random.default_rng(1)
    px = 1500 + np.cumsum(rng.normal(0, 0.3, len(ts)))
    df = pd.DataFrame({"ts": ts, "open": px, "high": px + 0.2, "low": px - 0.2,
                       "close": px, "spread_mean": 0.30})
    sig = random_entries(df, p=0.05, seed=2)
    res = Backtester(BTConfig(max_hold_bars=10)).run(df, sig)
    from backtest.metrics import compute_metrics
    m = compute_metrics(res, "5min")
    assert m["n_trades"] > 200, m["n_trades"]
    assert m["expectancy_usd"] < 0, m["expectancy_usd"]
    assert m["profit_factor"] < 1.0, m["profit_factor"]
    assert m["total_cost_usd"] > 0
    print(f"  random+costs: n={m['n_trades']} expectancy={m['expectancy_usd']:.4f} "
          f"PF={m['profit_factor']:.3f}  OK (cost model bites)")


def test_buy_and_hold_tracks_price():
    from backtest.strategy import buy_and_hold
    ts = pd.date_range("2020-01-01", periods=5000, freq="15min", tz="UTC")
    px = np.linspace(1500, 1800, len(ts))
    df = pd.DataFrame({"ts": ts, "open": px, "high": px, "low": px, "close": px,
                       "spread_mean": 0.30})
    res = Backtester(BTConfig(size_lots=0.01, allow_short=False)).run(df, buy_and_hold(df))
    tr = res["trades"]
    assert len(tr) == 1
    t = tr.iloc[0]
    # exact: gross = (exit_mid - entry_mid) * size * contract
    approx(t.gross_pnl, (t.exit_mid - t.entry_mid) * 0.01 * 100, tol=1e-6)
    # and it should be within a spread's worth of the raw price move
    raw_move = (px[-1] - px[1]) * 0.01 * 100
    assert abs(t.gross_pnl - raw_move) < 1.0, (t.gross_pnl, raw_move)
    assert t.cost > 0 and t.exit_reason == "eod"
    print(f"  buy&hold tracks price: gross={t.gross_pnl:.2f} (raw move {raw_move:.2f}) OK")


def test_trailing_stop():
    # long entry @100, R=2 (stop 98). Price runs 100->107 then falls back.
    # trail_dist=2, activate at +1R -> once price >= 102, stop = ext-2.
    # peak close 106 on bar 5 -> stop ratchets to 104 -> bar 6 low 103 hits it.
    rows = [(100, 100, 100, 100, 0.0),   # 0 signal
            (100, 100, 100, 100, 0.0),   # 1 entry @100, stop 98
            (100, 103, 100, 103, 0.0),   # 2 +1.5R, activate -> stop=101
            (103, 105, 103, 105, 0.0),   # 3 close105 -> stop=103
            (105, 106, 104, 106, 0.0),   # 4 close106 -> stop=104
            (106, 106, 103, 104, 0.0),   # 5 low103 -> hits stop@104 (set on bar4)
            (104, 104, 100, 100, 0.0)]
    df = _bars(rows)
    sig = {"long_entry": np.array([1, 0, 0, 0, 0, 0, 0], bool),
           "short_entry": np.zeros(7, bool), "exit_signal": np.zeros(7, bool),
           "stop_dist": np.full(7, 2.0), "trail_dist": np.full(7, 2.0)}
    from backtest.engine import BTConfig as _C
    res = Backtester(_C(slippage_ticks=0, commission_roundtrip_per_lot=0,
                        allow_short=False, trail_activate_r=1.0, trail_ref="close")).run(df, sig)
    t = res["trades"].iloc[0]
    assert t.exit_reason == "stop", t.exit_reason
    approx(t.exit_mid, 104.0)
    assert t.net_pnl > 0, t.net_pnl        # locked in a profit via the trail
    print(f"  trailing stop: exit @{t.exit_mid} net={t.net_pnl:.2f}  OK")


if __name__ == "__main__":
    fns = [test_hand_long_trade, test_stop_is_pessimistic,
           test_costs_make_random_lose, test_buy_and_hold_tracks_price,
           test_trailing_stop]
    for fn in fns:
        print(fn.__name__)
        fn()
    print("\nALL BACKTEST ENGINE TESTS PASSED")
