"""
PRE-REGISTERED TEST — Hypothesis H2   (run ONCE on untouched 2024-2026 OOS)

    Instrument      : XAUUSD
    Regime          : original 4H gate (build_trades, unchanged)
    Impulse         : original 1H definition (unchanged)
    Pullback        : retracement >= 0.62
    Duration        : confirmation delay >= 6 bars
    Entry           : break of pullback extreme (unchanged)
    Stop            : structural swing +/- 0.2 ATR (unchanged)
    Exit            : fixed 2R  (exit "A")
    Costs / sizing  : unchanged

    NO new indicators, session filter, ADX/vol optimisation, extra confirmation,
    exit optimisation, or parameter tuning.  H2 is frozen.

Decision rule (defined BEFORE seeing the data):
    PASS         : net expectancy >= +0.05 R/trade AND n >= 50 AND no
                   concentration in a tiny subset (top-3 trades < ~60% of PnL)
    INCONCLUSIVE : positive but n < 50, or 95% CI comfortably includes 0
    FAIL         : <= 0 R/trade at a reasonable sample size

Also reported (NOT part of the frozen test): the incremental-information check —
does H2 need BOTH "deep" and "slow", or is one of them carrying it?

Usage:  python -m research.h2_oos_test
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars
from research.gold_trend_continuation import build_trades

warnings.filterwarnings("ignore", message=".*timezones available for np.datetime64.*")

RETR_MIN = 0.62
DELAY_MIN = 6
EXIT = "A"          # fixed 2R


def _ci(x: np.ndarray, boot=20000, seed=0):
    x = np.asarray(x, float)
    n = len(x)
    m = x.mean()
    se = x.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    normal = (m - 1.96 * se, m + 1.96 * se)
    rng = np.random.default_rng(seed)
    bs = rng.choice(x, size=(boot, n), replace=True).mean(axis=1)
    return m, se, normal, (np.percentile(bs, 2.5), np.percentile(bs, 97.5))


def _describe(d: pd.DataFrame, label: str):
    if len(d) == 0:
        print(f"  {label:34s}  n=0"); return
    net = d[f"{EXIT}_net"].to_numpy()
    hit = (d[f"{EXIT}_R"] > 0).mean()
    m, se, nrm, bsi = _ci(net)
    print(f"  {label:34s}  n={len(d):4d}  hit={hit:.3f}  netR={m:+.3f}  "
          f"95%CI[{nrm[0]:+.3f},{nrm[1]:+.3f}]  boot[{bsi[0]:+.3f},{bsi[1]:+.3f}]")


def main():
    # THE single authorised spend of the touch-once out-of-sample window.
    # Pre-registered test of frozen Hypothesis H2; run once, result accepted as-is.
    d15 = load_bars("15min", split="out_of_sample", allow_oos=True)
    t = build_trades(d15, "out_of_sample")
    t["year"] = pd.to_datetime(t["ts"]).dt.year
    print(f"OOS window: {t['ts'].min()}  ->  {t['ts'].max()}")
    print(f"total continuation entries generated (all, pre-filter): {len(t)}")

    h2 = t[(t["retr"] >= RETR_MIN) & (t["conf_delay"] >= DELAY_MIN)].copy()

    print("\n" + "=" * 74)
    print("FROZEN H2  —  retr >= 0.62  AND  confirmation delay >= 6 bars,  exit 2R")
    print("=" * 74)
    if len(h2) == 0:
        print("no qualifying trades in OOS — INCONCLUSIVE (no data)")
        return
    net = h2[f"{EXIT}_net"].to_numpy()
    gross = h2[f"{EXIT}_R"].to_numpy()
    hit = (h2[f"{EXIT}_R"] > 0).mean()
    m, se, nrm, bsi = _ci(net)
    tot = net.sum()
    order = np.sort(net)[::-1]
    top3 = order[:3].sum() / tot if tot > 0 else np.nan
    top5 = order[:5].sum() / tot if tot > 0 else np.nan

    print(f"n                     {len(h2)}")
    print(f"hit rate (>0)         {hit:.3f}")
    print(f"gross R / trade       {gross.mean():+.3f}")
    print(f"NET R / trade         {m:+.3f}")
    print(f"  std / trade         {net.std(ddof=1):.3f}")
    print(f"  95% CI (normal)     [{nrm[0]:+.3f}, {nrm[1]:+.3f}]")
    print(f"  95% CI (bootstrap)  [{bsi[0]:+.3f}, {bsi[1]:+.3f}]")
    print(f"total NET R           {tot:+.2f}")
    print(f"concentration         top-3 trades = {top3:.0%} of positive PnL, top-5 = {top5:.0%}")
    print(f"avg cost              {h2['cost_r'].mean():.3f}R")
    print("\nby year:")
    print(h2.groupby("year").agg(n=(f"{EXIT}_net", "size"),
                                 hit=(f"{EXIT}_R", lambda x: (x > 0).mean()),
                                 netR=(f"{EXIT}_net", "mean")).round(3).to_string())

    # ---- pre-registered verdict -------------------------------------------
    print("\n" + "-" * 74)
    powered = len(h2) >= 50
    positive = m >= 0.05
    ci_excludes_0 = nrm[0] > 0
    concentrated = (top3 is not np.nan) and top3 > 0.60
    if m <= 0 and len(h2) >= 30:
        verdict = "FAIL  — non-positive at a usable sample size. Retire H2."
    elif positive and powered and not concentrated and ci_excludes_0:
        verdict = "PASS  — positive, powered, not concentrated, CI excludes 0."
    elif positive and powered and not concentrated:
        verdict = "PASS (weak) — positive & powered & not concentrated, but 95% CI still includes 0."
    elif positive:
        verdict = "INCONCLUSIVE — positive but underpowered (n<50) or concentrated. Do not deploy, do not discard."
    else:
        verdict = "INCONCLUSIVE — near zero / underpowered."
    print("VERDICT:", verdict)
    print("-" * 74)

    # ---- incremental-information check (NOT part of the frozen test) ------
    print("\nincremental-information check on the SAME OOS data (context only):")
    _describe(t[t.index.isin(t.index)], "ALL continuation entries")
    _describe(t[t["conf_delay"] >= DELAY_MIN], "slow only  (delay >= 6)")
    _describe(t[t["retr"] >= RETR_MIN], "deep only  (retr >= 0.62)")
    _describe(h2, "deep AND slow  (= H2)")
    _describe(t[(t["conf_delay"] >= DELAY_MIN) & (t["retr"] < RETR_MIN)], "slow & NOT deep")
    _describe(t[(t["retr"] >= RETR_MIN) & (t["conf_delay"] < DELAY_MIN)], "deep & NOT slow")

    t.to_csv("research/h2_oos_trades.csv", index=False)
    print("\nsaved research/h2_oos_trades.csv   (OOS is now spent)")


if __name__ == "__main__":
    main()
