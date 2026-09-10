"""
MEAN-REVERSION research  —  STAGE A (phenomenon) + STAGE B (period robustness)

NOT a strategy. No entry/exit rules, no parameter search. One question:

    After an unusually large short-term displacement in XAUUSD, does price
    exhibit statistically AND economically meaningful reversion toward a
    fair-value anchor — more than a non-extreme bar would?

Method (15-min bars, leak-free):
  * displacement = k-bar return ending at t, standardised by the trailing std
    of k-bar returns (computed through t-1) -> move_sd ;   also move_atr =
    k-bar move / ATR14 measured BEFORE the move.
  * reference point = close[t] (end of the displacement).  origin = close[t-k].
  * forward, signed so POSITIVE = reversion (against the move):
        rev_h  = -sign(move) * (close[t+h]-close[t]) / ATR14[t]   for h in H_LIST
        max_rev / max_cont over the next MAXH bars (opposite / same excursion)
        crossed_origin, retraced_50pct within MAXH
  * de-clustered event set: keep an extreme only if >= GAP bars since the last
    kept one (extreme moves cluster; raw n overstates independence).
  * baseline: the SAME rev_h measured on ALL bars, bucketed by |move_sd|.
    If reversion doesn't grow with displacement size, there is no phenomenon.

STAGE B: repeat the reversion curve for P1 2009-15, P2 2016-22, P3 2023-24,
P4 2024-07..2026-08 — a real effect keeps its sign in all four.

Economic bar: round-trip cost at 0.01 lot ~= $0.44 ; ATR14(15m) ~= $1.0-1.4,
so ~0.35 ATR. Mean reversion must clear ~0.4 ATR to matter.

Usage:  python -m research.mr_stage_a
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from research.ema5_winner_analysis import _atr

warnings.filterwarnings("ignore", message=".*timezones available for np.datetime64.*")

K_LIST = [1, 4, 8]            # displacement windows (15m, 1h, 2h)
H_LIST = [2, 4, 8, 16, 32, 96]
MAXH = 32                     # 8h reversion window
SD_WIN = 480                  # ~5 trading days of 15m bars
GAP = 16                      # de-cluster spacing (4h)
THRESH = [1.5, 2.0, 2.5, 3.0, 4.0]


def _fwd_extreme(arr, H, kind):
    s = pd.Series(arr[::-1])
    r = (s.rolling(H).max() if kind == "max" else s.rolling(H).min())
    return r[::-1].shift(-1).to_numpy()


def load_all():
    parts = []
    for sp in ("in_sample", "walk_forward"):
        d = load_bars("15min", split=sp); d["split"] = sp
        parts.append(d)
    d = load_bars("15min", split="out_of_sample", allow_oos=True); d["split"] = "oos"
    parts.append(d)
    df = pd.concat(parts, ignore_index=True).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    return df


def build(df, k):
    o = df["open"].to_numpy(float); hi = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float); cl = df["close"].to_numpy(float)
    ts = pd.DatetimeIndex(df["ts"]); n = len(df)
    atr = _atr(hi, lo, cl, 14)[0]
    sma20 = pd.Series(cl).rolling(20).mean().to_numpy()
    sma100 = pd.Series(cl).rolling(100).mean().to_numpy()
    atr100 = _atr(hi, lo, cl, 100)[0]

    ret_k = cl / np.roll(cl, k) - 1.0
    ret_k[:k] = np.nan
    sd_prev = pd.Series(ret_k).rolling(SD_WIN).std().shift(1).to_numpy()
    move_sd = ret_k / sd_prev
    move_atr = (cl - np.roll(cl, k)) / np.roll(atr, k)
    move_atr[:k] = np.nan
    sign = np.sign(cl - np.roll(cl, k))

    fmax = _fwd_extreme(hi, MAXH, "max")
    fmin = _fwd_extreme(lo, MAXH, "min")
    origin = np.roll(cl, k)

    max_rev = np.where(sign < 0, (fmax - cl), (cl - fmin)) / atr
    max_cont = np.where(sign < 0, (cl - fmin), (fmax - cl)) / atr
    crossed = np.where(sign < 0, fmax >= origin, fmin <= origin).astype(float)
    disp_atr = np.abs(cl - origin) / atr
    retr50 = (max_rev >= 0.5 * disp_atr).astype(float)

    out = {"ts": ts, "split": df["split"].to_numpy(), "sign": sign,
           "move_sd": move_sd, "move_atr": move_atr, "atr": atr,
           "max_rev": max_rev, "max_cont": max_cont, "crossed_origin": crossed,
           "retr50": retr50, "disp_atr": disp_atr,
           "hour": ts.hour.to_numpy(),
           "dist_sma20_atr": (cl - sma20) / atr * sign,     # + = displaced away from MA
           "dist_sma100_atr": (cl - sma100) / atr * sign,
           "prevol_ratio": atr / atr100,
           "postvol_ratio": _fwd_extreme(atr, 12, "max") / atr}
    for h in H_LIST:
        fh = pd.Series(cl).shift(-h).to_numpy()
        out[f"rev_{h}"] = -sign * (fh - cl) / atr
    return pd.DataFrame(out)


def _decluster(idx, gap=GAP):
    keep, last = [], -10 ** 9
    for i in idx:
        if i - last >= gap:
            keep.append(i); last = i
    return np.array(keep)


def _t(x):
    x = x[~np.isnan(x)]
    return x.mean(), x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan, len(x)


def stage_a(f: pd.DataFrame, k: int):
    print(f"\n{'='*82}\nSTAGE A  —  displacement window k={k} bars "
          f"({k*15}min)   |   n bars = {f['move_sd'].notna().sum():,}\n{'='*82}")
    amsd = f["move_sd"].abs()
    print(f"\nbaseline reversion (mean rev_h, ATR units) by |move_sd| bucket — "
          f"de-clustered, t in ():")
    buckets = [(0.0, 0.5, "quiet <0.5"), (0.5, 1.0, "0.5-1.0"), (1.0, 1.5, "1.0-1.5"),
               (1.5, 2.0, "1.5-2.0"), (2.0, 2.5, "2.0-2.5"), (2.5, 3.0, "2.5-3.0"),
               (3.0, 4.0, "3.0-4.0"), (4.0, 99, "4.0+")]
    hdr = f"{'bucket':11s} {'n_ev':>6} " + " ".join(f"{'rev_'+str(h):>13}" for h in H_LIST) \
          + f" {'max_rev':>9} {'max_cont':>9} {'cross%':>7} {'retr50%':>8}"
    print(hdr)
    for lo, hi, name in buckets:
        m = (amsd >= lo) & (amsd < hi) & f["move_sd"].notna()
        idx = _decluster(np.where(m.to_numpy())[0])
        if len(idx) < 20:
            continue
        g = f.iloc[idx]
        cells = []
        for h in H_LIST:
            mu, se, nn = _t(g[f"rev_{h}"].to_numpy())
            tval = mu / se if se and not np.isnan(se) else np.nan
            cells.append(f"{mu:+.3f}({tval:+.1f})")
        print(f"{name:11s} {len(idx):>6} " + " ".join(f"{c:>13}" for c in cells)
              + f" {np.nanmean(g['max_rev']):>9.2f} {np.nanmean(g['max_cont']):>9.2f}"
              + f" {100*np.nanmean(g['crossed_origin']):>6.1f} {100*np.nanmean(g['retr50']):>7.1f}")

    print(f"\ndirectional symmetry (|move_sd|>=2.5, de-clustered): "
          f"mean rev_16 up-moves vs down-moves")
    ext = (amsd >= 2.5) & f["move_sd"].notna()
    idx = _decluster(np.where(ext.to_numpy())[0]); g = f.iloc[idx]
    for s, lab in [(-1, "down-move (revert up)"), (1, "up-move (revert down)")]:
        gg = g[g["sign"] == s]
        mu, se, nn = _t(gg["rev_16"].to_numpy())
        print(f"  {lab:24s} n={nn:5d}  rev_16 = {mu:+.3f} ATR  (t={mu/se:+.2f})" if se else f"  {lab} thin")


def stage_b(f: pd.DataFrame, k: int, thr=2.5):
    print(f"\n{'-'*82}\nSTAGE B  —  |move_sd| >= {thr}, de-clustered, by period "
          f"(k={k})   rev_h mean (ATR), t in ()\n{'-'*82}")
    P = {"P1 2009-15": lambda t: t.year <= 2015,
         "P2 2016-22": lambda t: (t.year >= 2016) & (t.year <= 2022),
         "P3 2023-24wf": lambda t: (t >= pd.Timestamp("2023-01-01", tz="UTC")) & (t < pd.Timestamp("2024-07-01", tz="UTC")),
         "P4 2024-26oos": lambda t: t >= pd.Timestamp("2024-07-01", tz="UTC")}
    ext = (f["move_sd"].abs() >= thr) & f["move_sd"].notna()
    idx = _decluster(np.where(ext.to_numpy())[0]); g = f.iloc[idx].copy()
    tsi = pd.DatetimeIndex(g["ts"])
    print(f"{'period':14s} {'n':>6} " + " ".join(f"{'rev_'+str(h):>13}" for h in H_LIST)
          + f" {'max_rev':>8} {'cross%':>7}")
    for name, fn in P.items():
        gg = g[fn(tsi if 'wf' in name or 'oos' in name else tsi.year if False else tsi)]
        # simpler: build mask directly
        if "P1" in name:
            mask = tsi.year <= 2015
        elif "P2" in name:
            mask = (tsi.year >= 2016) & (tsi.year <= 2022)
        elif "P3" in name:
            mask = (tsi >= pd.Timestamp("2023-01-01", tz="UTC")) & (tsi < pd.Timestamp("2024-07-01", tz="UTC"))
        else:
            mask = tsi >= pd.Timestamp("2024-07-01", tz="UTC")
        gg = g[mask]
        if len(gg) < 15:
            print(f"{name:14s} {len(gg):>6}  (thin)"); continue
        cells = []
        for h in H_LIST:
            mu, se, nn = _t(gg[f"rev_{h}"].to_numpy())
            cells.append(f"{mu:+.3f}({mu/se:+.1f})" if se and not np.isnan(se) else "  --  ")
        print(f"{name:14s} {len(gg):>6} " + " ".join(f"{c:>13}" for c in cells)
              + f" {np.nanmean(gg['max_rev']):>8.2f} {100*np.nanmean(gg['crossed_origin']):>6.1f}")


def stage_d_peek(f: pd.DataFrame, k: int, thr=2.5):
    print(f"\n{'-'*82}\nSTAGE D PEEK (context only, NOT the phenomenon test) — |move_sd|>={thr}, "
          f"rev_16 by crude condition (k={k})\n{'-'*82}")
    ext = (f["move_sd"].abs() >= thr) & f["move_sd"].notna()
    idx = _decluster(np.where(ext.to_numpy())[0]); g = f.iloc[idx].copy()
    g["sess"] = np.where(g.hour < 7, "asia", np.where(g.hour < 12, "london",
                         np.where(g.hour < 17, "ny_am", "ny_pm")))
    g["prevol_hi"] = (g.prevol_ratio >= 1.2).map({True: "vol already hi", False: "vol normal"})
    g["far_from_ma"] = (g.dist_sma20_atr >= 1.5).map({True: ">=1.5 ATR from SMA20", False: "<1.5 ATR"})
    for col in ["sess", "prevol_hi", "far_from_ma"]:
        print(f"\n[{col}]")
        for v, gg in g.groupby(col):
            mu, se, nn = _t(gg["rev_16"].to_numpy())
            mr = np.nanmean(gg["max_rev"])
            print(f"  {str(v):22s} n={nn:5d}  rev_16={mu:+.3f} (t={mu/se:+.2f})  max_rev={mr:.2f}"
                  if se and not np.isnan(se) else f"  {v}: thin")


if __name__ == "__main__":
    df = load_all()
    print(f"loaded {len(df):,} 15m bars   {df['ts'].min()} -> {df['ts'].max()}")
    for k in K_LIST:
        f = build(df, k)
        stage_a(f, k)
        stage_b(f, k, thr=2.5)
        if k == 4:
            stage_d_peek(f, k, thr=2.5)
            f.to_csv("research/mr_stage_a_k4.csv", index=False)
            print("\nsaved research/mr_stage_a_k4.csv")
