"""
Martingale on 200-EMA bias — XAUUSD.

Rules (user spec):
  * bias = sign(close - EMA200) on the current bar.
  * When flat, enter next bar's open in the bias direction.
  * Fixed 20-pip stop AND 20-pip target (1 pip = 0.10 price => 20 pip = $2.00 move).
  * On a STOP: double the lot for the next entry.
  * On a TARGET: reset the lot to the 0.01 base.
  * One position at a time; hold to SL/TP regardless of a mid-trade bias flip.
  * If a bar touches both stop and target, assume STOP first (pessimistic, matches engine).

Costs per round trip (same model as backtest/engine.py):
  spread     = (spread_mean_entry/2 + spread_mean_exit/2) * lots * 100
  slippage   = 2 * slippage_ticks(1) * tick(0.01) * lots * 100
  commission = 6.0 * lots            # Vantage Raw ECN, $3/side per 1.0 lot

Ruin = equity (start + realised) <= 0  -> margin call, stop.
Lot cap = broker max; a required lot above the cap cannot be placed -> the
sequence is stuck: we mark it and stop (that is a real-world blow-up too).

Usage:  python -m research.martingale_200ema
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars

PIP = 0.10
STOP_PIPS = 20                    # overridden per-run by simulate()
TP_PIPS = 20
BASE_LOT = 0.01
CONTRACT = 100.0
COMMISSION_RT_PER_LOT = 6.0
SLIP_TICKS = 1.0
TICK = 0.01
EMA_LEN = 200
LOT_CAP = 50.0                    # Vantage XAUUSD max lot per order (typical)


def _cost(lots, spr_entry, spr_exit):
    spread = (spr_entry / 2 + spr_exit / 2) * lots * CONTRACT
    slip = 2 * SLIP_TICKS * TICK * lots * CONTRACT
    comm = COMMISSION_RT_PER_LOT * lots
    return spread + slip + comm


def simulate(df: pd.DataFrame, start_equity: float, lot_cap: float = LOT_CAP,
             reset_on_ruin: bool = False, stop_pips: int = STOP_PIPS,
             tp_pips: int = TP_PIPS, entry_mode: str = "ema200",
             martingale: bool = True):
    STOP_D = stop_pips * PIP
    TP_D = tp_pips * PIP
    o = df["open"].to_numpy(float)
    hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    cl = df["close"].to_numpy(float)
    spr = df["spread_mean"].to_numpy(float)
    ema = pd.Series(cl).ewm(span=EMA_LEN, adjust=False).mean().to_numpy()
    n = len(df)

    def _want(i):
        # signal computed on the just-closed bar i; entry fills at bar i+1 open
        if entry_mode == "ema200":
            return np.nan if np.isnan(ema[i]) else (1 if cl[i] > ema[i] else -1)
        if entry_mode == "fade_candle":          # fade the last candle's colour
            if cl[i] > o[i]:
                return -1
            if cl[i] < o[i]:
                return 1
            return np.nan                         # doji -> skip
        if entry_mode == "fade_ret":             # fade the last close-to-close move
            if i < 1:
                return np.nan
            if cl[i] > cl[i - 1]:
                return -1
            if cl[i] < cl[i - 1]:
                return 1
            return np.nan
        raise ValueError(entry_mode)

    realised = 0.0
    lot = BASE_LOT
    pos = 0                       # 0 flat, +1 long, -1 short
    entry_px = np.nan
    entry_i = -1
    stop_lvl = tgt_lvl = np.nan
    cur_lot = 0.0

    trades = []                   # (exit_i, side, lots, net, reason)
    equity_curve = np.empty(n)
    max_lot_seen = BASE_LOT
    max_streak = 0
    streak = 0
    ruined_at = None
    stuck_at = None

    for i in range(n):
        if pos != 0:
            exit_px = reason = None
            stop_hit = (lo[i] <= stop_lvl) if pos > 0 else (hi[i] >= stop_lvl)
            tgt_hit = (hi[i] >= tgt_lvl) if pos > 0 else (lo[i] <= tgt_lvl)
            if stop_hit:
                exit_px, reason = stop_lvl, "stop"
            elif tgt_hit:
                exit_px, reason = tgt_lvl, "target"
            if exit_px is not None:
                gross = pos * (exit_px - entry_px) * cur_lot * CONTRACT
                net = gross - _cost(cur_lot, spr[entry_i], spr[i])
                realised += net
                trades.append((i, pos, cur_lot, net, reason))
                if reason == "stop":
                    lot = min(lot * 2, lot_cap * 2) if martingale else BASE_LOT
                    streak += 1
                    max_streak = max(max_streak, streak)
                else:
                    lot = BASE_LOT
                    streak = 0
                pos = 0
                entry_px = stop_lvl = tgt_lvl = np.nan
                entry_i = -1

        eq = start_equity + realised
        equity_curve[i] = eq
        if eq <= 0 and ruined_at is None:
            ruined_at = i
            if not reset_on_ruin:
                equity_curve[i:] = eq
                break
            realised = 0.0
            lot = BASE_LOT
            streak = 0

        if pos == 0 and i + 1 < n:
            want = _want(i)
            if np.isnan(want):
                continue
            want = int(want)
            place_lot = round(lot, 2)
            if place_lot > lot_cap:
                stuck_at = i
                equity_curve[i:] = start_equity + realised
                break
            nb = i + 1
            fill = o[nb]
            pos = want
            entry_px = fill
            entry_i = nb
            cur_lot = place_lot
            max_lot_seen = max(max_lot_seen, cur_lot)
            stop_lvl = fill - want * STOP_D
            tgt_lvl = fill + want * TP_D

    tdf = pd.DataFrame(trades, columns=["exit_i", "side", "lots", "net", "reason"])
    return {
        "trades": tdf,
        "equity": pd.Series(equity_curve[: i + 1], index=df["ts"].iloc[: i + 1]),
        "realised": realised,
        "n_trades": len(tdf),
        "wins": int((tdf["reason"] == "target").sum()) if len(tdf) else 0,
        "losses": int((tdf["reason"] == "stop").sum()) if len(tdf) else 0,
        "max_lot": max_lot_seen,
        "max_loss_streak": max_streak,
        "ruined_at": None if ruined_at is None else str(df["ts"].iloc[ruined_at]),
        "stuck_at": None if stuck_at is None else str(df["ts"].iloc[stuck_at]),
        "end_equity": float(equity_curve[min(i, n - 1)]),
    }


def simulate_nosl(df: pd.DataFrame, start_equity: float, tp_pips: int = 100,
                  ema_len: int = 5, entry_mode: str = "ema5_trend",
                  lot: float = BASE_LOT):
    """No stop-loss. Enter on the 5-EMA relationship, hold until +tp_pips or
    end-of-data. Floating P&L is marked every bar so a margin call is detected
    while the position is still open."""
    TP_D = tp_pips * PIP
    o = df["open"].to_numpy(float)
    hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    cl = df["close"].to_numpy(float)
    spr = df["spread_mean"].to_numpy(float)
    ts = df["ts"].to_numpy()
    ema = pd.Series(cl).ewm(span=ema_len, adjust=False).mean().to_numpy()
    n = len(df)

    realised = 0.0
    pos = 0
    entry_px = np.nan
    entry_i = -1
    tgt_lvl = np.nan
    equity_curve = np.empty(n)
    trades = []                   # (entry_i, exit_i, side, net, reason, bars, mae_usd)
    mae_px = 0.0
    worst_float = 0.0            # most negative floating equity hit, USD
    max_bars = 0
    ruined_at = None

    for i in range(n):
        if pos != 0:
            adv = (entry_px - lo[i]) if pos > 0 else (hi[i] - entry_px)
            mae_px = max(mae_px, adv)
            tgt_hit = (hi[i] >= tgt_lvl) if pos > 0 else (lo[i] <= tgt_lvl)
            if tgt_hit:
                gross = pos * (tgt_lvl - entry_px) * lot * CONTRACT
                net = gross - _cost(lot, spr[entry_i], spr[i])
                realised += net
                trades.append((entry_i, i, pos, net, "target", i - entry_i,
                               mae_px * lot * CONTRACT))
                pos = 0
                entry_px = tgt_lvl = np.nan
                entry_i = -1
                mae_px = 0.0

        unreal = 0.0
        if pos != 0:
            unreal = pos * (cl[i] - entry_px) * lot * CONTRACT
        eq = start_equity + realised + unreal
        equity_curve[i] = eq
        worst_float = min(worst_float, unreal)
        if pos != 0:
            max_bars = max(max_bars, i - entry_i)
        if eq <= 0 and ruined_at is None:
            ruined_at = i
            equity_curve[i:] = eq
            break

        if pos == 0 and i + 1 < n and not np.isnan(ema[i]):
            if cl[i] == ema[i]:
                continue
            above = cl[i] > ema[i]
            want = (1 if above else -1) if entry_mode == "ema5_trend" else (-1 if above else 1)
            nb = i + 1
            fill = o[nb]
            pos = want
            entry_px = fill
            entry_i = nb
            tgt_lvl = fill + want * TP_D
            mae_px = 0.0

    if pos != 0 and ruined_at is None:
        j = n - 1
        gross = pos * (cl[j] - entry_px) * lot * CONTRACT
        net = gross - _cost(lot, spr[entry_i], spr[j])
        realised += net
        trades.append((entry_i, j, pos, net, "eod", j - entry_i, mae_px * lot * CONTRACT))
        equity_curve[j] = start_equity + realised

    tdf = pd.DataFrame(trades, columns=["entry_i", "exit_i", "side", "net",
                                        "reason", "bars", "mae_usd"])
    wins = int((tdf["reason"] == "target").sum()) if len(tdf) else 0
    open_loss = float(tdf.loc[tdf["reason"] == "eod", "net"].sum()) if len(tdf) else 0.0
    return {
        "n_trades": len(tdf),
        "wins": wins,
        "still_open_at_end": int((tdf["reason"] == "eod").sum()) if len(tdf) else 0,
        "open_trade_pnl": round(open_loss, 2),
        "realised": round(realised, 2),
        "end_equity": round(float(equity_curve[min(i, n - 1)]), 2),
        "worst_floating_dd_usd": round(worst_float, 2),
        "max_bars_held": int(max_bars),
        "max_days_held": round(max_bars * 5 / 60 / 24, 1),
        "median_bars_to_target": int(tdf.loc[tdf.reason == "target", "bars"].median())
        if wins else None,
        "worst_single_mae_usd": round(float(tdf["mae_usd"].max()), 2) if len(tdf) else 0.0,
        "ruined_at": None if ruined_at is None else str(pd.Timestamp(ts[ruined_at])),
    }


def simulate_hold(df: pd.DataFrame, start_equity: float, sl_pips: int = 50,
                  ema_len: int = 5, entry_mode: str = "ema5_trend",
                  trail_pips: int | None = None, lot: float = BASE_LOT):
    """Enter on the 5-EMA relationship every time we're flat. 50-pip stop, NO
    target -- 'just hold'. Optional trailing stop (ratchet to running extreme
    -/+ trail_pips once that is tighter than the fixed stop). Exit only on the
    stop or at end-of-data. Floating P&L marked every bar for margin calls."""
    SL_D = sl_pips * PIP
    TR_D = None if trail_pips is None else trail_pips * PIP
    o = df["open"].to_numpy(float); hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float); cl = df["close"].to_numpy(float)
    spr = df["spread_mean"].to_numpy(float); ts = df["ts"].to_numpy()
    ema = pd.Series(cl).ewm(span=ema_len, adjust=False).mean().to_numpy()
    n = len(df)

    realised = 0.0; pos = 0; entry_px = np.nan; entry_i = -1
    stop_lvl = np.nan; run_ext = np.nan
    equity_curve = np.empty(n); trades = []
    worst_float = 0.0; max_bars = 0; ruined_at = None

    for i in range(n):
        if pos != 0:
            hit = (lo[i] <= stop_lvl) if pos > 0 else (hi[i] >= stop_lvl)
            if hit:
                gross = pos * (stop_lvl - entry_px) * lot * CONTRACT
                net = gross - _cost(lot, spr[entry_i], spr[i])
                realised += net
                trades.append((entry_i, i, pos, net, "stop", i - entry_i))
                pos = 0; entry_px = stop_lvl = run_ext = np.nan; entry_i = -1
            elif TR_D is not None:
                if pos > 0:
                    run_ext = cl[i] if np.isnan(run_ext) else max(run_ext, cl[i])
                    stop_lvl = max(stop_lvl, run_ext - TR_D)
                else:
                    run_ext = cl[i] if np.isnan(run_ext) else min(run_ext, cl[i])
                    stop_lvl = min(stop_lvl, run_ext + TR_D)

        unreal = pos * (cl[i] - entry_px) * lot * CONTRACT if pos != 0 else 0.0
        eq = start_equity + realised + unreal
        equity_curve[i] = eq
        worst_float = min(worst_float, unreal)
        if pos != 0:
            max_bars = max(max_bars, i - entry_i)
        if eq <= 0 and ruined_at is None:
            ruined_at = i; equity_curve[i:] = eq; break

        if pos == 0 and i + 1 < n and not np.isnan(ema[i]) and cl[i] != ema[i]:
            above = cl[i] > ema[i]
            want = (1 if above else -1) if entry_mode == "ema5_trend" else (-1 if above else 1)
            nb = i + 1; fill = o[nb]
            pos = want; entry_px = fill; entry_i = nb
            stop_lvl = fill - want * SL_D; run_ext = np.nan

    if pos != 0 and ruined_at is None:
        j = n - 1
        gross = pos * (cl[j] - entry_px) * lot * CONTRACT
        realised += gross - _cost(lot, spr[entry_i], spr[j])
        trades.append((entry_i, j, pos, gross, "eod", j - entry_i))
        equity_curve[j] = start_equity + realised

    tdf = pd.DataFrame(trades, columns=["entry_i", "exit_i", "side", "net", "reason", "bars"])
    wins = int((tdf["net"] > 0).sum()) if len(tdf) else 0
    return {
        "n_trades": len(tdf),
        "wins_net_positive": wins,
        "losers": len(tdf) - wins,
        "win_rate": round(wins / len(tdf), 3) if len(tdf) else None,
        "still_open_at_end": int((tdf["reason"] == "eod").sum()) if len(tdf) else 0,
        "realised": round(realised, 2),
        "end_equity": round(float(equity_curve[min(i, n - 1)]), 2),
        "avg_net_per_trade": round(float(tdf["net"].mean()), 3) if len(tdf) else None,
        "best_trade": round(float(tdf["net"].max()), 2) if len(tdf) else None,
        "worst_trade": round(float(tdf["net"].min()), 2) if len(tdf) else None,
        "worst_floating_dd_usd": round(worst_float, 2),
        "max_bars_held": int(max_bars),
        "max_days_held": round(max_bars * 5 / 60 / 24, 1),
        "ruined_at": None if ruined_at is None else str(pd.Timestamp(ts[ruined_at])),
    }


def run_ema5_hold():
    for split in ("walk_forward", "in_sample"):
        df = load_bars("5min", split=split).reset_index(drop=True)
        for mode in ("ema5_trend", "ema5_fade"):
            for trail in (None, 50):
                r = simulate_hold(df, 1_000, sl_pips=50, ema_len=5,
                                  entry_mode=mode, trail_pips=trail)
                tl = "fixed stop" if trail is None else f"trail {trail}p"
                print(f"\n===  5min / {split}  [5-EMA {mode}, 50p SL, NO TP, {tl}, "
                      f"0.01 lot, $1,000]  ({df['ts'].iloc[0].date()} -> "
                      f"{df['ts'].iloc[-1].date()})  ===")
                for k, v in r.items():
                    print(f"   {k:24s} {v}")


def run_ema5_nosl():
    for split in ("walk_forward", "in_sample"):
        df = load_bars("5min", split=split).reset_index(drop=True)
        for mode in ("ema5_trend", "ema5_fade"):
            r = simulate_nosl(df, 1_000, tp_pips=100, ema_len=5, entry_mode=mode)
            print(f"\n===  5min / {split}  [5-EMA {mode}, NO stop, +100 pip TP, "
                  f"0.01 lot, $1,000]  ({df['ts'].iloc[0].date()} -> "
                  f"{df['ts'].iloc[-1].date()})  ===")
            for k, v in r.items():
                print(f"   {k:24s} {v}")


def _report(tag, df, equities, stop_pips=STOP_PIPS, tp_pips=TP_PIPS,
            entry_mode="ema200", martingale=True):
    print(f"\n================  {tag}  [{entry_mode}, SL {stop_pips} / TP {tp_pips} pip, "
          f"{'martingale' if martingale else 'flat 0.01'}]  "
          f"({df['ts'].iloc[0].date()} -> {df['ts'].iloc[-1].date()}, "
          f"{len(df):,} bars)  ================")
    for eq0 in equities:
        r = simulate(df, eq0, stop_pips=stop_pips, tp_pips=tp_pips,
                     entry_mode=entry_mode, martingale=martingale)
        wl = r["wins"] + r["losses"]
        hit = r["wins"] / wl if wl else float("nan")
        print(f"\n start ${eq0:,.0f}")
        print(f"   trades {r['n_trades']:,}   win {r['wins']:,} / loss {r['losses']:,}   hit {hit:.3f}")
        print(f"   max lot reached      {r['max_lot']:.2f}")
        print(f"   longest loss streak  {r['max_loss_streak']}")
        print(f"   end equity           ${r['end_equity']:,.2f}   (realised ${r['realised']:,.2f})")
        print(f"   RUINED at            {r['ruined_at']}")
        print(f"   lot-cap STUCK at     {r['stuck_at']}")


def run_ema_grid():
    for sl, tp in [(20, 20), (20, 40)]:
        for tf in ("15min", "5min"):
            for split in ("walk_forward", "in_sample"):
                df = load_bars(tf, split=split).reset_index(drop=True)
                _report(f"{tf} / {split}", df, [1_000, 10_000, 100_000],
                        stop_pips=sl, tp_pips=tp)


def run_fade_1m():
    for split in ("walk_forward", "in_sample"):
        df = load_bars("1min", split=split).reset_index(drop=True)
        for mode in ("fade_candle", "fade_ret"):
            for mart in (True, False):
                _report(f"1min / {split}", df, [1_000, 10_000, 100_000],
                        stop_pips=30, tp_pips=30, entry_mode=mode, martingale=mart)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "fade1m":
        run_fade_1m()
    elif len(sys.argv) >= 2 and sys.argv[1] == "ema5nosl":
        run_ema5_nosl()
    elif len(sys.argv) >= 2 and sys.argv[1] == "ema5hold":
        run_ema5_hold()
    elif len(sys.argv) == 3:
        sl, tp = int(sys.argv[1]), int(sys.argv[2])
        for tf in ("15min", "5min"):
            for split in ("walk_forward", "in_sample"):
                df = load_bars(tf, split=split).reset_index(drop=True)
                _report(f"{tf} / {split}", df, [1_000, 10_000, 100_000],
                        stop_pips=sl, tp_pips=tp)
    else:
        run_ema_grid()
