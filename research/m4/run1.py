"""
M4 Run 1 — step 2 of 2:  compute the fingerprint-grid ledger.

Consumes research/m4/events.parquet.  For every frozen (state-bucket, anchor,
horizon, metric) cell:
  - effect vs §2G matched control, stratified by (block × session).  Instrument
    and anchor-type are mandatory & automatic; day-of-week / month-of-year are
    the two OPTIONAL match dims and are RELAXED for run 1 (recorded on the row).
  - per-block P1..P4 effects; Cochran Q / I² / leave-one-block-out robustness
  - ANALYTIC standard errors (delta-method for means/dispersion/skew/kurt;
    normal-approx for quantiles), each widened by the autocorrelation inflation
    factor √(1 + 2Σρ_k).  A full moving-block bootstrap is the v2 upgrade.
  - +1-step look-ahead shift test (uses the *_s bucket column)
  - ONE Benjamini–Hochberg FDR (q = 0.10) across the whole grid

Gates A (predictive) and B (economic; reference scenarios R≈0.30σ / L≈0.04σ).
No interpretation, no strategy.  Writes research/m4/ledger.csv + one-page tally.

Run:  python -m research.m4.run1
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd
from scipy import stats

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
warnings.filterwarnings("ignore", category=RuntimeWarning)

HORIZONS = [2, 4, 8, 16, 32, 96]
FDR_Q = 0.10
SHIFT_TOL = 0.25
MIN_N, MIN_N_BLOCK, MIN_STRAT = 60, 20, 2
# data hygiene (removes the same near-zero-range degeneracy flagged all through M3):
SIGMA_FLOOR_Q = 0.01       # drop anchor events whose ATR14 is in the bottom 1%
WINS_R = 20.0             # winsorise forward return / excursion (sigma units)
FRICTION_R, FRICTION_L = 0.30, 0.04
YEARS = (pd.Timestamp("2026-09-01") - pd.Timestamp("2009-01-01")).days / 365.25

GRID = [
    ("m1", "m1_s", ["A1", "A2", "A3", "A4", "A5"], [0, 1, 2]),
    ("m2", "m2_s", ["A1", "A2", "A3", "A4", "A5"], [0, 1, 2]),
    ("m3", "m3_s", ["A1", "A2", "A3", "A4", "A5"], [0, 1, 2]),
    ("m4", "m4_s", ["A1", "A2", "A3", "A4", "A5"], [0, 1, 2, 3, 4]),
    ("m5", "m5_s", ["A1", "A2", "A3", "A4", "A5"], [0, 1, 2]),
    ("t1", "t1_s", ["A6"], [0, 1, 2]),
    ("t2", "t2_s", ["A1", "A3"], [0, 1, 2]),
    ("e1", "e1_s", ["A1", "A4"], [0, 1, 2]),
    ("e2", "e2_s", ["A1", "A4"], [0, 1, 2]),
    ("e3", "e3_s", ["A1", "A4"], [0, 1, 2]),
]
BLOCKS = ["P1", "P2", "P3", "P4"]

MEAN_METRICS = [("location", "r"), ("rv_path", "rv_ratio"),
                ("p_tail_up", "tail_up"), ("p_tail_dn", "tail_dn"),
                ("E_mfe", "mfe"), ("E_mae", "mae"),
                ("E_t_mfe", "t_mfe"), ("E_t_mae", "t_mae"),
                ("p_mfe_first", "mfe_before_mae"),
                ("race_1_1", "race_1_1"), ("race_2_1", "race_2_1"), ("race_1_2", "race_1_2"),
                ("p_cross_sma", "cross_sma"), ("p_cross_sopen", "cross_sopen"),
                ("p_ret_origin", "ret_origin")]
QMAP = {"q05": .05, "q25": .25, "q50": .50, "q75": .75, "q95": .95}
DIR_METRICS = {"location_dir", "race_1_1", "race_2_1", "race_1_2"}


def _acf_infl(v, L):
    v = v[np.isfinite(v)]
    if len(v) < 30 or L < 1:
        return 1.0
    v = v - v.mean(); d = v @ v
    if d <= 0:
        return 1.0
    s = 1.0
    for k in range(1, min(L, len(v) - 1) + 1):
        s += 2.0 * (v[:-k] @ v[k:]) / d
    return float(min(max(1.0, s), 10.0))


def _mean_effect_se(vs, vc):
    """difference of means + delta-method SE (per stratum)."""
    vs = vs[np.isfinite(vs)]; vc = vc[np.isfinite(vc)]
    if len(vs) < 5 or len(vc) < 5:
        return None
    e = vs.mean() - vc.mean()
    var = vs.var(ddof=1) / len(vs) + vc.var(ddof=1) / len(vc)
    return e, var, len(vs)


def _r_effect_se(rs, rc, metric):
    rs = rs[np.isfinite(rs)]; rc = rc[np.isfinite(rc)]
    ns, nc = len(rs), len(rc)
    if ns < 20 or nc < 20:
        return None
    if metric == "dispersion":
        ss, sc = rs.std(ddof=1), rc.std(ddof=1)
        if sc <= 0:
            return None
        e = ss / sc - 1.0
        var = (ss / sc) ** 2 * (0.5 / ns + 0.5 / nc)          # log-var approx
        return e, var, ns
    if metric == "skew":
        e = stats.skew(rs) - stats.skew(rc)
        return e, 6.0 / ns + 6.0 / nc, ns
    if metric == "kurt":
        e = stats.kurtosis(rs) - stats.kurtosis(rc)
        return e, 24.0 / ns + 24.0 / nc, ns
    q = QMAP[metric]
    zq = stats.norm.ppf(q); phi = stats.norm.pdf(zq)
    xs = np.quantile(rs, q); xc = np.quantile(rc, q)
    e = xs - xc
    var = (rs.std(ddof=1) ** 2 * q * (1 - q) / (phi ** 2 * ns)
           + rc.std(ddof=1) ** 2 * q * (1 - q) / (phi ** 2 * nc))
    return e, var, ns


def cell_effects(S, C, mean_cols, dir_anchor, L):
    """Return {metric: (effect, se)} across all strata for one cell."""
    strata = S.groupby(["block", "session"]).groups
    acc = {}   # metric -> [num, den, var_num]
    def _add(m, e, var, w):
        a = acc.setdefault(m, [0.0, 0.0, 0.0])
        a[0] += e * w; a[1] += w; a[2] += var * w * w
    nstrat = 0
    for (blk, ses), idx in strata.items():
        Cm = (C["block"] == blk) & (C["session"] == ses)
        if not Cm.any():
            continue
        Sr = S.loc[idx]
        rs = Sr["r"].to_numpy(float); rc = C.loc[Cm, "r"].to_numpy(float)
        w = np.isfinite(rs).sum()
        if w < 5:
            continue
        nstrat += 1
        for mname, col in mean_cols:
            r = _mean_effect_se(Sr[col].to_numpy(float), C.loc[Cm, col].to_numpy(float))
            if r:
                _add(mname, r[0], r[1], r[2])
        if dir_anchor:
            r = _mean_effect_se((Sr["r"] * Sr["dir"]).to_numpy(float),
                                (C.loc[Cm, "r"] * C.loc[Cm, "dir"]).to_numpy(float))
            if r:
                _add("location_dir", r[0], r[1], r[2])
        for m in ("dispersion", "skew", "kurt", *QMAP):
            r = _r_effect_se(rs, rc, m)
            if r:
                _add(m, r[0], r[1], r[2])
    if nstrat < MIN_STRAT:
        return None
    infl_r = np.sqrt(_acf_infl(S["r"].to_numpy(float), L))
    out = {}
    for m, (num, den, vnum) in acc.items():
        if den <= 0:
            continue
        eff = num / den
        se = np.sqrt(vnum) / den
        col = dict(mean_cols).get(m, "r")
        se *= np.sqrt(_acf_infl(S[col].to_numpy(float), L)) if col != "r" else infl_r
        out[m] = (float(eff), float(se))
    return out


def _pval(e, se):
    return float(2 * stats.norm.sf(abs(e / se))) if np.isfinite(e) and np.isfinite(se) and se > 0 else np.nan


def _cochran(effs, ses):
    m = [(e, s) for e, s in zip(effs, ses) if np.isfinite(e) and np.isfinite(s) and s > 0]
    if len(m) < 2:
        return np.nan, np.nan, len(m)
    e = np.array([x[0] for x in m]); w = 1 / np.array([x[1] for x in m]) ** 2
    ebar = (w * e).sum() / w.sum()
    Q = float((w * (e - ebar) ** 2).sum()); df = len(m) - 1
    return float(stats.chi2.sf(Q, df)), (max(0.0, (Q - df) / Q) if Q > 0 else 0.0), len(m)


def _loo_ok(effs, ses, full):
    idx = [i for i in range(len(effs)) if np.isfinite(effs[i]) and np.isfinite(ses[i]) and ses[i] > 0]
    if len(idx) < 3 or not np.isfinite(full) or full == 0:
        return np.nan
    for drop in idx:
        keep = [i for i in idx if i != drop]
        w = 1 / np.array([ses[i] for i in keep]) ** 2
        loo = (w * np.array([effs[i] for i in keep])).sum() / w.sum()
        if np.sign(loo) != np.sign(full) or not (0.5 * abs(full) <= abs(loo) <= 1.5 * abs(full)):
            return False
    return True


def main():
    ev = pd.read_parquet("research/m4/events.parquet").reset_index(drop=True)
    n0 = len(ev)
    flo = ev["sigma"].quantile(SIGMA_FLOOR_Q)
    ev = ev[ev["sigma"] >= flo].copy()
    for c in ("r",):
        ev[c] = ev[c].clip(-WINS_R, WINS_R)
    for c in ("mfe", "mae"):
        ev[c] = ev[c].clip(0, 1.5 * WINS_R)
    ev["rv_ratio"] = ev["rv_ratio"].clip(0, 10)
    print(f"events.parquet: {n0:,} rows -> {len(ev):,} after sigma-floor "
          f"(ATR14>={flo:.3f}) + winsorise |r|<={WINS_R}; {ev['idx'].nunique():,} anchor events")
    rows = []
    ncell = 0
    for (state, scol, anchors, buckets) in GRID:
        for A in anchors:
            dir_anchor = A in ("A2", "A3", "A6")
            for H in HORIZONS:
                sub = ev[(ev["anchor"] == A) & (ev["H"] == H)].dropna(subset=["r"])
                if len(sub) < MIN_N * 2:
                    continue
                mean_cols = [(n, c) for (n, c) in MEAN_METRICS
                             if sub[c].notna().sum() >= MIN_N
                             and not (n in DIR_METRICS and not dir_anchor)]
                L = max(1, round(H / 4))
                for b in buckets:
                    Sn = sub[sub[state] == b]; Cn = sub[sub[state].notna() & (sub[state] != b)]
                    if len(Sn) < MIN_N or len(Cn) < MIN_N:
                        continue
                    full = cell_effects(Sn, Cn, mean_cols, dir_anchor, L)
                    if not full:
                        continue
                    blk = {}
                    for P in BLOCKS:
                        Sb, Cb = Sn[Sn["block"] == P], Cn[Cn["block"] == P]
                        blk[P] = (cell_effects(Sb, Cb, mean_cols, dir_anchor, L)
                                  if len(Sb) >= MIN_N_BLOCK and len(Cb) >= MIN_N_BLOCK else None)
                    Ss = sub[sub[scol] == b]; Cs = sub[sub[scol].notna() & (sub[scol] != b)]
                    shift = (cell_effects(Ss, Cs, mean_cols, dir_anchor, L)
                             if len(Ss) >= MIN_N and len(Cs) >= MIN_N else None)
                    for mname, (eff, se) in full.items():
                        ncell += 1
                        beff = [blk[P][mname][0] if blk[P] and mname in blk[P] else np.nan for P in BLOCKS]
                        bse = [blk[P][mname][1] if blk[P] and mname in blk[P] else np.nan for P in BLOCKS]
                        Qp, I2, nb = _cochran(beff, bse)
                        loo = _loo_ok(beff, bse, eff)
                        es = shift[mname][0] if shift and mname in shift else np.nan
                        sd = abs(es - eff) / max(abs(eff), 1e-9) if np.isfinite(es) else np.nan
                        rows.append(dict(state=state, anchor=A, bucket=int(b), H=H, metric=mname,
                                         n_S=len(Sn), n_C=len(Cn),
                                         events_per_year=round(len(Sn) / YEARS, 1),
                                         effect=eff, se=se, p=_pval(eff, se),
                                         blk_P1=beff[0], blk_P2=beff[1], blk_P3=beff[2], blk_P4=beff[3],
                                         cochran_p=Qp, I2=I2, n_blocks=nb, loo_ok=loo, shift_delta=sd))
    led = pd.DataFrame(rows)
    if led.empty:
        print("no cells"); return

    pv = led["p"].to_numpy(float); ok = np.isfinite(pv); m = int(ok.sum())
    order = np.argsort(np.where(ok, pv, np.inf))
    crit = FDR_Q * np.arange(1, len(pv) + 1) / max(m, 1)
    below = np.where(ok[order] & (pv[order] <= crit))[0]
    passed = np.zeros(len(pv), bool)
    if len(below):
        passed[order[: below.max() + 1]] = ok[order[: below.max() + 1]]
    led["fdr_sig"] = passed
    led["stability_ok"] = (led["cochran_p"] > 0.10) & (led["I2"] < 0.50) & (led["loo_ok"] == True)
    led["shift_ok"] = led["shift_delta"] < SHIFT_TOL
    led["A"] = led["fdr_sig"] & led["stability_ok"] & led["shift_ok"]

    def _b(r):
        if not r["A"]:
            return ""
        if r["metric"] == "location_dir":
            g = abs(r["effect"])
        elif r["metric"].startswith("race_"):
            x, y = map(int, r["metric"].split("_")[1:]); g = abs(r["effect"]) * (x + y)
        else:
            return "NON-DIRECTIONAL (see fingerprint)"
        if g >= FRICTION_R + 0.05:
            return f"MATTERS-AT-R ({g:.3f}σ)"
        if g >= FRICTION_L + 0.01:
            return f"MATTERS-AT-L-ONLY ({g:.3f}σ)"
        return f"NEGLIGIBLE ({g:.3f}σ)"
    led["B"] = led.apply(_b, axis=1)
    led.to_csv("research/m4/ledger.csv", index=False)

    print(f"\n================  M4 RUN 1 — LEDGER  ================")
    print(f"cells (finite p): {m:,} of {len(led):,}   |  FDR q = {FDR_Q}")
    print(f"FDR-significant:                         {int(led['fdr_sig'].sum())}")
    print(f"  + stable (Q p>0.10 & I²<0.50 & LOO):   {int((led['fdr_sig'] & led['stability_ok']).sum())}")
    print(f"  + shift-robust   ⇒  A = YES:           {int(led['A'].sum())}")
    if led["A"].any():
        a = led[led["A"]].copy()
        cols = ["state", "anchor", "bucket", "H", "metric", "effect", "se",
                "blk_P1", "blk_P2", "blk_P3", "blk_P4", "cochran_p", "I2",
                "shift_delta", "n_S", "events_per_year", "B"]
        print("\nA = YES cells:\n" + a[cols].sort_values(["state", "anchor", "H", "metric"]).to_string(index=False))
        cls = {"m": "MARKET", "t": "TEMPORAL", "e": "EVENT"}
        a["cls"] = a["state"].str[0].map(cls)
        print("\nby state:\n" + a.groupby(["cls", "state"], observed=True).size().to_string())
        print("\nby horizon:\n" + a.groupby("H").size().to_string())
        print("\nby metric:\n" + a.groupby("metric").size().to_string())
        print("\nB tally:\n" + a["B"].value_counts().to_string())
    else:
        print("\nNo cell cleared gate A — under this frozen protocol, no pre-registered "
              "state measurably reshapes XAUUSD's forward distribution beyond FDR noise "
              "at horizons 30m–24h.")
    print("\nwrote research/m4/ledger.csv")
    print("REMINDER: the grid is the result — do not mine individual sub-threshold cells.")


if __name__ == "__main__":
    main()
