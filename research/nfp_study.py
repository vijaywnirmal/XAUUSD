"""
How XAUUSD behaves around NFP (US non-farm payrolls) - descriptive study, not a
strategy backtest. 5-min canonical bars, true UTC, full history 2009-2026.

NFP = first Friday of the month, 08:30 ET.  In UTC that is 12:30 during US DST
(2nd Sun Mar .. 1st Sun Nov) and 13:30 otherwise - handled per date.

    python -m research.nfp_study
"""
import numpy as np
import pandas as pd
from datetime import date, timedelta

from data_pipeline.dataset import load_bars


def us_dst(d: date) -> bool:
    y = d.year
    mar = date(y, 3, 8)
    dst_start = mar + timedelta(days=(6 - mar.weekday()) % 7)      # 2nd Sunday March
    nov = date(y, 11, 1)
    dst_end = nov + timedelta(days=(6 - nov.weekday()) % 7)        # 1st Sunday November
    return dst_start <= d < dst_end


def first_fridays(dates):
    out = {}
    s = pd.Series(dates)
    for (y, m), g in s.groupby([s.dt.year, s.dt.month]):
        fri = [d for d in g if d.weekday() == 4]
        if not fri:
            continue
        f = fri[0]
        # first Friday landing on Jan 1-3 -> NFP is the next Friday (holiday shift)
        if f.month == 1 and f.day <= 3 and len(fri) > 1:
            f = fri[1]
        out[f.date()] = True
    return out


def main():
    df = load_bars("5min", allow_oos=True,
                   columns=["ts", "open", "high", "low", "close", "spread_mean"])
    df["d"] = df["ts"].dt.normalize()
    df["tmin"] = df["ts"].dt.hour * 60 + df["ts"].dt.minute
    df["dow"] = df["ts"].dt.dayofweek
    daily_dates = pd.Series(sorted(df["d"].unique()))
    nfp = first_fridays(daily_dates)

    # 20-day ATR for normalisation
    dd = df.groupby("d").agg(H=("high", "max"), L=("low", "min"), C=("close", "last"))
    dd["pc"] = dd["C"].shift(1)
    dd["tr"] = np.maximum(dd.H - dd.L, np.maximum((dd.H - dd.pc).abs(), (dd.L - dd.pc).abs()))
    dd["atr20"] = dd["tr"].rolling(20).mean().shift(1)

    rows = []
    for dt, g in df.groupby("d"):
        d0 = dt.date()
        g = g.sort_values("ts")
        rel = 750 if us_dst(d0) else 810           # 12:30 or 13:30 UTC, in minutes
        atr = dd["atr20"].get(dt, np.nan)
        if np.isnan(atr) or atr <= 0:
            continue

        def px(tm):
            r = g[g.tmin == tm]
            return float(r["open"].iloc[0]) if len(r) else np.nan

        def clx(tm):
            r = g[(g.tmin >= tm) & (g.tmin < tm + 10)]
            return float(r["close"].iloc[0]) if len(r) else np.nan

        p08 = px(480); p_rel = px(rel)
        p_r5 = clx(rel + 5); p_r15 = clx(rel + 15); p_r30 = clx(rel + 30)
        p_r90 = clx(rel + 90); p_r180 = clx(rel + 180); p_r360 = clx(rel + 360)
        p1300 = clx(max(rel, 780)); p2000 = clx(1200)
        spr_rel = g.loc[g.tmin.between(rel, rel + 5), "spread_mean"].mean()
        spr_pre = g.loc[g.tmin.between(rel - 60, rel - 5), "spread_mean"].mean()

        if np.isnan(p_rel) or np.isnan(p_r30):
            continue
        spike5 = (p_r5 / p_rel - 1) if not np.isnan(p_r5) else np.nan
        spike30 = p_r30 / p_rel - 1
        sdir = np.sign(spike30) if spike30 != 0 else 1.0
        rows.append(dict(
            date=d0, nfp=d0 in nfp, dow=dt.dayofweek, atr=atr,
            pre_bps=(p_rel / p08 - 1) * 1e4 if not np.isnan(p08) else np.nan,
            spike5_abs_atr=abs(spike5) * p_rel / atr if not np.isnan(spike5) else np.nan,
            spike15_abs_atr=abs(p_r15 / p_rel - 1) * p_rel / atr if not np.isnan(p_r15) else np.nan,
            spike30_abs_atr=abs(spike30) * p_rel / atr,
            spike30_bps=spike30 * 1e4,
            cont_90_bps=(sdir * (p_r90 / p_r30 - 1)) * 1e4 if not np.isnan(p_r90) else np.nan,
            cont_180_bps=(sdir * (p_r180 / p_r30 - 1)) * 1e4 if not np.isnan(p_r180) else np.nan,
            cont_360_bps=(sdir * (p_r360 / p_r30 - 1)) * 1e4 if not np.isnan(p_r360) else np.nan,
            day_bps=(p2000 / p1300 - 1) * 1e4 if not (np.isnan(p2000) or np.isnan(p1300)) else np.nan,
            spread_blowout=spr_rel / spr_pre if spr_pre and spr_pre > 0 else np.nan,
        ))
    x = pd.DataFrame(rows)
    x["yr"] = pd.to_datetime(x["date"]).dt.year
    q = x[x.nfp].copy()
    other_fri = x[(~x.nfp) & (x.dow == 4)]
    alld = x

    def T(a):
        a = pd.Series(a).dropna()
        return a.mean() / a.std() * np.sqrt(len(a)) if len(a) > 2 and a.std() > 0 else np.nan

    print(f"NFP days found: {len(q)}  ({q.date.min()} .. {q.date.max()})\n")

    print("=== 1. THE RELEASE SPIKE (|move| in ATR units, and in bps) ===")
    print(f"  {'window':10s} {'NFP median(ATR)':>16} {'NFP p90(ATR)':>13} {'other-Fri median':>17}")
    for col, w in [("spike5_abs_atr", "0-5 min"), ("spike15_abs_atr", "0-15 min"), ("spike30_abs_atr", "0-30 min")]:
        print(f"  {w:10s} {q[col].median():16.2f} {q[col].quantile(.9):13.2f} {other_fri[col].median():17.2f}")
    print(f"  0-30 min move in bps: NFP median |{q.spike30_bps.abs().median():.0f}|  p90 |{q.spike30_bps.abs().quantile(.9):.0f}|  "
          f"max |{q.spike30_bps.abs().max():.0f}|   (other Fri median |{other_fri.spike30_bps.abs().median():.0f}|)")

    print("\n=== 2. PRE-NFP (08:00 UTC -> release), bps ===")
    print(f"  NFP:       mean {q.pre_bps.mean():+.2f}   median {q.pre_bps.median():+.2f}   t_vs0 {T(q.pre_bps):+.2f}   n={q.pre_bps.notna().sum()}")
    print(f"  other Fri: mean {other_fri.pre_bps.mean():+.2f}   median {other_fri.pre_bps.median():+.2f}   t_vs0 {T(other_fri.pre_bps):+.2f}")
    print("  -> is there a directional drift into the print?")

    print("\n=== 3. AFTER THE SPIKE - does the 0-30min move CONTINUE (+) or REVERSE (-)?  bps ===")
    for col, w in [("cont_90_bps", "+30 to +120 min"), ("cont_180_bps", "+30 to +210 min"), ("cont_360_bps", "+30 to +390 min")]:
        s = q[col]
        print(f"  {w:16s} mean {s.mean():+.2f}   median {s.median():+.2f}   t_vs0 {T(s):+.2f}   %positive {100*(s>0).mean():.0f}")
    print("  (negative mean = the knee-jerk partially reverses;  positive = it keeps running)")

    print("\n=== 4. WHOLE NFP SESSION (13:00 -> 20:00 UTC), bps ===")
    print(f"  NFP:       mean {q.day_bps.mean():+.2f}   median {q.day_bps.median():+.2f}   t_vs0 {T(q.day_bps):+.2f}   std {q.day_bps.std():.0f}")
    print(f"  all days:  mean {alld.day_bps.mean():+.2f}   median {alld.day_bps.median():+.2f}   t_vs0 {T(alld.day_bps):+.2f}")

    print("\n=== 5. SPREAD BLOW-OUT at the release (x its pre-release level) ===")
    print(f"  NFP:       median {q.spread_blowout.median():.1f}x   p90 {q.spread_blowout.quantile(.9):.1f}x   max {q.spread_blowout.max():.1f}x")
    print(f"  other Fri: median {other_fri.spread_blowout.median():.1f}x")

    print("\n=== 6. BY ERA (NFP 0-30min |move| in ATR; session bps mean; pre bps mean) ===")
    for lo, hi, lab in [(2009, 2015, "2009-2014"), (2015, 2022, "2015-2021"), (2022, 2027, "2022-2026")]:
        e = q[(q.yr >= lo) & (q.yr < hi)]
        print(f"  {lab}:  n={len(e):3d}   spike30(ATR) med {e.spike30_abs_atr.median():.2f}   "
              f"session mean {e.day_bps.mean():+.1f} bps (t {T(e.day_bps):+.2f})   "
              f"pre mean {e.pre_bps.mean():+.1f} bps   post-30 cont(90) mean {e.cont_90_bps.mean():+.1f}")

    print("\n=== 7. DISTRIBUTION of the 0-30 min signed move (bps) on NFP days ===")
    for p in [5, 10, 25, 50, 75, 90, 95]:
        print(f"  p{p:>2}: {q.spike30_bps.quantile(p/100):+7.0f} bps")

    out = x[x.nfp][["date", "pre_bps", "spike5_abs_atr", "spike30_abs_atr", "spike30_bps",
                    "cont_90_bps", "cont_180_bps", "day_bps", "spread_blowout"]]
    out.to_csv("research/nfp_days.csv", index=False)
    print("\nwrote research/nfp_days.csv  (per-NFP-day detail)")


if __name__ == "__main__":
    main()
