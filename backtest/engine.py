"""
Event-driven bar backtester for XAUUSD.

Design / anti-look-ahead:
  * A strategy sees bars [0..t] and emits signals for bar t.
  * Entries fill at bar t+1's OPEN (mid) after crossing the spread + slippage.
  * Stops / targets / time-stop / session-flat are checked on bars t+1, t+2, ...
    using each bar's own mid high/low/open — no future information.
  * If a bar touches both stop and target, the STOP is assumed first (pessimistic).

Costs (all applied per trade, in USD):
    spread   : (spread_mean[entry_bar]/2 + spread_mean[exit_bar]/2) * size_lots * contract
    slippage : 2 * slippage_ticks * tick_size * size_lots * contract
    commission: commission_roundtrip_per_lot * size_lots
PnL is computed at mid levels; the three costs above are then subtracted.

Money is modelled in USD. The live account is INR-denominated — convert at
review time; it does not change relative results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class BTConfig:
    contract_size: float = 100.0          # oz per 1.0 lot (Vantage XAUUSD)
    tick_size: float = 0.01
    commission_roundtrip_per_lot: float = 6.0   # USD, Vantage Raw ECN ($3/side)
    slippage_ticks: float = 1.0           # per side
    size_lots: float = 0.01               # used when size_mode == "fixed"
    size_mode: str = "fixed"              # "fixed" | "risk_pct"
    risk_pct: float = 0.005               # of equity, when size_mode == "risk_pct" (needs stop)
    initial_equity: float = 1000.0        # USD
    allow_short: bool = True
    reverse_on_opposite: bool = True      # opposite entry signal closes & flips
    max_hold_bars: Optional[int] = None
    session_flat_hour_utc: Optional[int] = None   # force flat at/after this UTC hour
    one_trade_per_day: bool = False               # block re-entry on the same UTC date
    # trailing stop: once favourable excursion reaches trail_activate_r * R,
    # ratchet the stop to (running extreme of `trail_ref`) -/+ trail_dist[entry_bar].
    trail_activate_r: Optional[float] = None
    trail_ref: str = "close"                       # "close" | "hl"
    min_lots: float = 0.01
    lot_step: float = 0.01


@dataclass
class Trade:
    side: int                 # +1 long, -1 short
    entry_i: int
    exit_i: int
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_mid: float
    exit_mid: float
    size_lots: float
    bars_held: int
    gross_pnl: float
    cost: float
    net_pnl: float
    r_multiple: float         # net_pnl / initial risk ($), nan if no stop
    mae: float                # max adverse excursion, price
    mfe: float                # max favourable excursion, price
    exit_reason: str
    stop_lvl: float = float("nan")   # stop price in effect at exit (nan if none), for charting
    tgt_lvl: float = float("nan")    # target price in effect at exit (nan if none), for charting


def _round_lots(x, step, lo):
    if x <= 0:
        return 0.0
    return max(lo, round(x / step) * step)


class Backtester:
    def __init__(self, cfg: BTConfig | None = None):
        self.cfg = cfg or BTConfig()

    def run(self, df: pd.DataFrame, signals: dict) -> dict:
        """
        df: bars with columns ts, open, high, low, close, spread_mean (UTC ts).
        signals: dict of equal-length arrays:
            long_entry (bool), short_entry (bool), exit_signal (bool),
            stop_dist (float, price; nan/None = none),
            target_dist (float, price; nan/None = none)
        Returns {"trades": DataFrame, "equity": Series, "config": BTConfig}.
        """
        c = self.cfg
        n = len(df)
        ts = df["ts"].to_numpy()
        o = df["open"].to_numpy(float)
        hi = df["high"].to_numpy(float)
        lo = df["low"].to_numpy(float)
        cl = df["close"].to_numpy(float)
        spr = df["spread_mean"].to_numpy(float)
        hour = pd.DatetimeIndex(df["ts"]).hour.to_numpy()
        day = pd.DatetimeIndex(df["ts"]).floor("D").asi8

        le = np.asarray(signals.get("long_entry", np.zeros(n, bool)), bool)
        se = np.asarray(signals.get("short_entry", np.zeros(n, bool)), bool)
        xs = np.asarray(signals.get("exit_signal", np.zeros(n, bool)), bool)

        def _arr(key):
            v = signals.get(key, None)
            return (np.full(n, np.nan) if v is None
                    else np.broadcast_to(np.asarray(v, float), (n,)).copy())

        stop_d = _arr("stop_dist")
        tgt_d = _arr("target_dist")
        trail_d = _arr("trail_dist")
        # resting stop-order entry levels (price). Fill when the bar trades through.
        l_stop = _arr("long_stop")
        s_stop = _arr("short_stop")
        if not c.allow_short:
            se[:] = False
            s_stop[:] = np.nan

        last_trade_day = -1

        half_slip = c.slippage_ticks * c.tick_size

        trades: list[Trade] = []
        realized = 0.0
        equity = np.empty(n, float)

        pos = 0                    # 0 flat, +1 long, -1 short
        entry_i = -1
        entry_mid = np.nan
        size_lots = 0.0
        stop_lvl = np.nan
        tgt_lvl = np.nan
        risk_usd = np.nan
        mae = mfe = 0.0
        run_ext = np.nan           # running favourable extreme for the trail

        def close_trade(i, exit_mid, reason):
            nonlocal pos, realized, entry_i, entry_mid, size_lots, stop_lvl, tgt_lvl, risk_usd, mae, mfe, run_ext
            gross = pos * (exit_mid - entry_mid) * size_lots * c.contract_size
            cost = ((spr[entry_i] / 2 + spr[i] / 2) + 2 * half_slip) * size_lots * c.contract_size \
                + c.commission_roundtrip_per_lot * size_lots
            net = gross - cost
            realized += net
            trades.append(Trade(
                side=pos, entry_i=entry_i, exit_i=i,
                entry_ts=pd.Timestamp(ts[entry_i]), exit_ts=pd.Timestamp(ts[i]),
                entry_mid=entry_mid, exit_mid=exit_mid, size_lots=size_lots,
                bars_held=i - entry_i, gross_pnl=gross, cost=cost, net_pnl=net,
                r_multiple=(net / risk_usd if risk_usd and not np.isnan(risk_usd) else np.nan),
                mae=mae, mfe=mfe, exit_reason=reason,
                stop_lvl=stop_lvl, tgt_lvl=tgt_lvl,
            ))
            pos = 0
            entry_i = -1
            entry_mid = size_lots = stop_lvl = tgt_lvl = risk_usd = run_ext = np.nan
            mae = mfe = 0.0

        def open_trade(i, side, fill=None, dist_idx=None):
            nonlocal pos, entry_i, entry_mid, size_lots, stop_lvl, tgt_lvl, risk_usd, mae, mfe, last_trade_day, run_ext
            if fill is None:
                fill = o[i]                  # mid; all friction is charged in `cost`
            di = (i - 1) if dist_idx is None else dist_idx
            sd = stop_d[di] if di >= 0 else np.nan
            td = tgt_d[di] if di >= 0 else np.nan
            if c.size_mode == "risk_pct" and sd and not np.isnan(sd) and sd > 0:
                eq_now = c.initial_equity + realized
                raw = (c.risk_pct * eq_now) / (sd * c.contract_size)
                sz = _round_lots(raw, c.lot_step, c.min_lots)
            else:
                sz = c.size_lots
            pos = side
            entry_i = i
            entry_mid = fill
            size_lots = sz
            stop_lvl = fill - side * sd if sd and not np.isnan(sd) else np.nan
            tgt_lvl = fill + side * td if td and not np.isnan(td) else np.nan
            risk_usd = (sd * sz * c.contract_size) if sd and not np.isnan(sd) else np.nan
            last_trade_day = day[i]
            run_ext = fill
            mae = mfe = 0.0

        for i in range(n):
            # ---- manage an open position on bar i --------------------------
            if pos != 0:
                # excursions (price, adverse/favourable) using this bar's range
                adv = (entry_mid - lo[i]) if pos > 0 else (hi[i] - entry_mid)
                fav = (hi[i] - entry_mid) if pos > 0 else (entry_mid - lo[i])
                mae = max(mae, adv)
                mfe = max(mfe, fav)

                exited = False
                # stop first (pessimistic), then target
                if not np.isnan(stop_lvl):
                    hit = (lo[i] <= stop_lvl) if pos > 0 else (hi[i] >= stop_lvl)
                    if hit:
                        close_trade(i, stop_lvl, "stop")
                        exited = True
                if not exited and not np.isnan(tgt_lvl):
                    hit = (hi[i] >= tgt_lvl) if pos > 0 else (lo[i] <= tgt_lvl)
                    if hit:
                        close_trade(i, tgt_lvl, "target")
                        exited = True
                if not exited and c.session_flat_hour_utc is not None and hour[i] >= c.session_flat_hour_utc:
                    close_trade(i, o[i], "session_flat")
                    exited = True
                if not exited and c.max_hold_bars is not None and (i - entry_i) >= c.max_hold_bars:
                    close_trade(i, o[i], "time_stop")
                    exited = True
                if not exited and i >= 1 and xs[i - 1]:
                    close_trade(i, o[i], "signal")
                    exited = True

                # ---- trailing stop: ratchet stop_lvl for the NEXT bar ------
                if not exited and c.trail_activate_r is not None and entry_i >= 0:
                    td_trail = trail_d[entry_i]
                    if not np.isnan(td_trail) and risk_usd and not np.isnan(risk_usd):
                        sd_price = risk_usd / (size_lots * c.contract_size)
                        ref = cl[i] if c.trail_ref == "close" else (hi[i] if pos > 0 else lo[i])
                        if pos > 0:
                            run_ext = max(run_ext, ref)
                            if (run_ext - entry_mid) >= c.trail_activate_r * sd_price:
                                cand = run_ext - td_trail
                                stop_lvl = cand if np.isnan(stop_lvl) else max(stop_lvl, cand)
                        else:
                            run_ext = min(run_ext, ref)
                            if (entry_mid - run_ext) >= c.trail_activate_r * sd_price:
                                cand = run_ext + td_trail
                                stop_lvl = cand if np.isnan(stop_lvl) else min(stop_lvl, cand)

            # ---- ruin guard: a real account is margin-called at 0 ---------
            ruined = (c.initial_equity + realized) <= 0
            day_blocked = c.one_trade_per_day and day[i] == last_trade_day

            # ---- resting stop-order entry (fills intrabar on THIS bar) ----
            if not ruined and not day_blocked and pos == 0:
                if not np.isnan(l_stop[i]) and hi[i] >= l_stop[i]:
                    open_trade(i, +1, fill=max(o[i], l_stop[i]), dist_idx=i)
                elif not np.isnan(s_stop[i]) and lo[i] <= s_stop[i]:
                    open_trade(i, -1, fill=min(o[i], s_stop[i]), dist_idx=i)

            # ---- act on yesterday's market entry signal ------------------
            if not ruined and not day_blocked and i >= 1 and pos == 0:
                if le[i - 1]:
                    open_trade(i, +1)
                elif se[i - 1]:
                    open_trade(i, -1)
            elif not ruined and i >= 1 and pos != 0 and c.reverse_on_opposite:
                want = 1 if le[i - 1] else (-1 if se[i - 1] else 0)
                if want != 0 and want != pos:
                    close_trade(i, o[i], "reverse")
                    if (c.initial_equity + realized) > 0:
                        open_trade(i, want)

            # ---- mark equity ---------------------------------------------
            unreal = 0.0
            if pos != 0:
                unreal = pos * (cl[i] - entry_mid) * size_lots * c.contract_size
            equity[i] = c.initial_equity + realized + unreal

        # close any position at the last bar
        if pos != 0:
            close_trade(n - 1, cl[n - 1], "eod")
            equity[n - 1] = c.initial_equity + realized

        tdf = pd.DataFrame([t.__dict__ for t in trades])
        eq = pd.Series(equity, index=pd.DatetimeIndex(df["ts"]), name="equity")
        return {"trades": tdf, "equity": eq, "config": c}
