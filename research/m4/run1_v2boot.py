"""
M4 Run 1 — v2 inference:  moving-block-bootstrap replication of the grid.

Validation layer ONLY (per RUN1_SUMMARY.md "next stage").  Same grid, same
states/anchors/horizons/metrics/buckets, same matched-control logic, same three
gates.  No re-ranking, no new metrics, no threshold changes.

What changes: standard errors / p-values for the cells that could plausibly pass
are recomputed with a **moving-block bootstrap** (block length ≥ H bars) on the
(block × session)-stratified, time-ordered event series — the protocol §4.1
method — instead of Run 1's analytic delta-method + ACF inflation.

Procedure:
  1. read events.parquet (same hygiene) and ledger.csv (Run 1).
  2. for every Run-1 FDR-significant cell, recompute effect + moving-block
     bootstrap SE / p, and the same per-block P1..P4 → Cochran Q / I² / LOO.
     (shift_delta is a point-estimate property → reuse Run 1's value.)
  3. combined p-vector = bootstrap p for those cells, Run-1 analytic p for the
     rest; re-run ONE Benjamini–Hochberg FDR (q = 0.10) over the whole grid.
  4. re-apply stability + shift gates → v2 A = YES.
  5. compare v2 A=YES with Run 1's 305; report survivors / drops and the state
     of the PRIMARY LEAD (M1 low-vol regime × A3 new-1-day-extreme → continuation).

Writes research/m4/ledger_v2.csv + research/m4/RUN1_V2_SUMMARY.md

Run:  python -m research.m4.run1_v2boot
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

from research.m4.run1 import (MEAN_METRICS, QMAP, DIR_METRICS, HORIZONS, BLOCKS,
                              FDR_Q, SHIFT_TOL, MIN_N, MIN_N_BLOCK,
                              SIGMA_FLOOR_Q, WINS_R, YEARS,
                              _cochran, _loo_ok, _pval)

B_BOOT = 400
STRAT_CAP = 1400          # systematic-thin a stratum to <= this for the resample (time order kept)
RNG = np.random.default_rng(1)
FRICTION_R, FRICTION_L = 0.30, 0.04


def _mbb_idx(n, block, B, rng):
    """moving-block bootstrap resample indices, shape (B, n)."""
    if n <= block or block < 2:
        return rng.integers(0, max(n, 1), (B, n))
    k = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, (B, k))
    offs = np.arange(block)
    return (starts[:, :, None] + offs[None, None, :]).reshape(B, k * block)[:, :n]


def _r_stat(mat, metric):
    if metric == "dispersion":
        return np.std(mat, axis=-1, ddof=1)
    if metric == "skew":
        return stats.skew(mat, axis=-1)
    if metric == "kurt":
        return stats.kurtosis(mat, axis=-1)
    return np.quantile(mat, QMAP[metric], axis=-1)


def cell_boot(S, C, mean_cols, dir_anchor, H, want):
    """Moving-block bootstrap over (block,session) strata.
    Returns {metric: (effect, se)} for the metrics in `want`."""
    idxcol = "idx"
    mc_names = [n for (n, c) in mean_cols]
    mc_cols = [c for (n, c) in mean_cols]
    r_metrics = [m for m in ("dispersion", "skew", "kurt", *QMAP) if m in want]
    need_mean = [(n, c) for (n, c) in mean_cols if n in want]
    need_locdir = ("location_dir" in want) and dir_anchor
    strata = S.groupby(["block", "session"]).groups

    pt = {m: [0.0, 0.0] for m in want}       # [num, den]
    bt = {m: np.zeros(B_BOOT) for m in want}
    bden = 0
    for (blk, ses), gi in strata.items():
        Sg = S.loc[gi].sort_values(idxcol)
        Cm = C[(C["block"] == blk) & (C["session"] == ses)].sort_values(idxcol)
        # point estimate uses all events; the RESAMPLE is on a time-ordered
        # systematic thin to keep the moving-block bootstrap tractable.
        if len(Sg) > STRAT_CAP:
            Sg_b = Sg.iloc[:: int(np.ceil(len(Sg) / STRAT_CAP))]
        else:
            Sg_b = Sg
        if len(Cm) > STRAT_CAP:
            Cm_b = Cm.iloc[:: int(np.ceil(len(Cm) / STRAT_CAP))]
        else:
            Cm_b = Cm
        nS, nC = len(Sg), len(Cm)
        nSb, nCb = len(Sg_b), len(Cm_b)
        if nS < 5 or nC < 5:
            continue
        # block length: >= H bars of real time, in units of (thinned) events
        sp = np.median(np.diff(Sg_b[idxcol].to_numpy())) if nSb > 1 else 4
        blkS = int(min(max(3, np.ceil(H / max(sp, 1))), max(3, nSb // 3)))
        spc = np.median(np.diff(Cm_b[idxcol].to_numpy())) if nCb > 1 else 4
        blkC = int(min(max(3, np.ceil(H / max(spc, 1))), max(3, nCb // 3)))
        iS = _mbb_idx(nSb, blkS, B_BOOT, RNG)
        iC = _mbb_idx(nCb, blkC, B_BOOT, RNG)

        for (n_, c) in need_mean:
            e = np.nanmean(Sg[c].to_numpy(float)) - np.nanmean(Cm[c].to_numpy(float))
            pt[n_][0] += e * nS; pt[n_][1] += nS
            vs = Sg_b[c].to_numpy(float); vc = Cm_b[c].to_numpy(float)
            bt[n_] += (np.nanmean(vs[iS], 1) - np.nanmean(vc[iC], 1)) * nS
        if need_locdir:
            e = (np.nanmean((Sg["r"] * Sg["dir"]).to_numpy(float))
                 - np.nanmean((Cm["r"] * Cm["dir"]).to_numpy(float)))
            pt["location_dir"][0] += e * nS; pt["location_dir"][1] += nS
            vs = (Sg_b["r"] * Sg_b["dir"]).to_numpy(float)
            vc = (Cm_b["r"] * Cm_b["dir"]).to_numpy(float)
            bt["location_dir"] += (np.nanmean(vs[iS], 1) - np.nanmean(vc[iC], 1)) * nS
        if r_metrics:
            rsf = Sg["r"].to_numpy(float); rsf = rsf[np.isfinite(rsf)]
            rcf = Cm["r"].to_numpy(float); rcf = rcf[np.isfinite(rcf)]
            brS = Sg_b["r"].to_numpy(float)[iS]; brC = Cm_b["r"].to_numpy(float)[iC]
            for m in r_metrics:
                sS = _r_stat(rsf, m); sC = _r_stat(rcf, m)
                pt[m][0] += ((sS / sC - 1.0) if m == "dispersion" else (sS - sC)) * nS
                pt[m][1] += nS
                bS = _r_stat(brS, m); bC = _r_stat(brC, m)
                bt[m] += ((bS / bC - 1.0) if m == "dispersion" else (bS - bC)) * nS
        bden += nS
    if bden == 0:
        return {}
    out = {}
    for m in want:
        num, den = pt[m]
        if den <= 0:
            continue
        eff = num / den
        se = float((bt[m] / bden).std(ddof=1))
        out[m] = (float(eff), se)
    return out


def main():
    ev = pd.read_parquet("research/m4/events.parquet").reset_index(drop=True)
    flo = ev["sigma"].quantile(SIGMA_FLOOR_Q)
    ev = ev[ev["sigma"] >= flo].copy()
    ev["r"] = ev["r"].clip(-WINS_R, WINS_R)
    for c in ("mfe", "mae"):
        ev[c] = ev[c].clip(0, 1.5 * WINS_R)
    ev["rv_ratio"] = ev["rv_ratio"].clip(0, 10)

    led = pd.read_csv("research/m4/ledger.csv")
    # validation layer: re-do inference ONLY for Run-1's A=YES cells (the 305).
    # everything else keeps its Run-1 analytic p for the combined FDR context.
    sig = led[led["A"]].copy()
    print(f"Run-1 ledger: {len(led):,} cells  |  Run-1 A=YES to re-validate: {len(sig):,}")

    GBUCK = {"m1": [0, 1, 2], "m2": [0, 1, 2], "m3": [0, 1, 2], "m4": [0, 1, 2, 3, 4],
             "m5": [0, 1, 2], "t1": [0, 1, 2], "t2": [0, 1, 2],
             "e1": [0, 1, 2], "e2": [0, 1, 2], "e3": [0, 1, 2]}
    boot = {}   # (state,anchor,bucket,H) -> {metric: dict(effect, se, p, blk_*, cochran_p, I2, loo_ok)}
    groups = sig.groupby(["state", "anchor", "bucket", "H"])
    for gi, (key, grp) in enumerate(groups):
        state, A, b, H = key
        want = set(grp["metric"])
        sub = ev[(ev["anchor"] == A) & (ev["H"] == H)].dropna(subset=["r"])
        dir_anchor = A in ("A2", "A3", "A6")
        mean_cols = [(n, c) for (n, c) in MEAN_METRICS
                     if c in sub.columns and sub[c].notna().sum() >= MIN_N
                     and not (n in DIR_METRICS and not dir_anchor)]
        Sn = sub[sub[state] == b]; Cn = sub[sub[state].notna() & (sub[state] != b)]
        if len(Sn) < MIN_N or len(Cn) < MIN_N:
            continue
        full = cell_boot(Sn, Cn, mean_cols, dir_anchor, H, want)
        blk = {}
        for P in BLOCKS:
            Sb, Cb = Sn[Sn["block"] == P], Cn[Cn["block"] == P]
            blk[P] = (cell_boot(Sb, Cb, mean_cols, dir_anchor, H, want)
                      if len(Sb) >= MIN_N_BLOCK and len(Cb) >= MIN_N_BLOCK else {})
        for m in want:
            if m not in full:
                continue
            eff, se = full[m]
            beff = [blk[P].get(m, (np.nan, np.nan))[0] for P in BLOCKS]
            bse = [blk[P].get(m, (np.nan, np.nan))[1] for P in BLOCKS]
            Qp, I2, nb = _cochran(beff, bse)
            loo = _loo_ok(beff, bse, eff)
            boot[(state, A, int(b), int(H), m)] = dict(
                effect_v2=eff, se_v2=se, p_v2=_pval(eff, se),
                b1=beff[0], b2=beff[1], b3=beff[2], b4=beff[3],
                cochran_p_v2=Qp, I2_v2=I2, n_blocks_v2=nb, loo_ok_v2=loo)
        if (gi + 1) % 40 == 0:
            print(f"  ...{gi + 1} groups")

    # merge back
    led["key"] = list(zip(led["state"], led["anchor"], led["bucket"], led["H"], led["metric"]))
    for col in ["effect_v2", "se_v2", "p_v2", "b1", "b2", "b3", "b4",
                "cochran_p_v2", "I2_v2", "n_blocks_v2", "loo_ok_v2"]:
        led[col] = led["key"].map(lambda k: boot.get(k, {}).get(col, np.nan))
    # combined p: bootstrap where available, Run-1 analytic elsewhere
    led["p_combined"] = np.where(led["p_v2"].notna(), led["p_v2"], led["p"])

    pv = led["p_combined"].to_numpy(float); ok = np.isfinite(pv); m = int(ok.sum())
    order = np.argsort(np.where(ok, pv, np.inf))
    crit = FDR_Q * np.arange(1, len(pv) + 1) / max(m, 1)
    below = np.where(ok[order] & (pv[order] <= crit))[0]
    passed = np.zeros(len(pv), bool)
    if len(below):
        passed[order[: below.max() + 1]] = ok[order[: below.max() + 1]]
    led["fdr_sig_v2"] = passed

    # stability: prefer v2 Cochran/LOO where computed, else Run-1
    cp = led["cochran_p_v2"].where(led["cochran_p_v2"].notna(), led["cochran_p"])
    i2 = led["I2_v2"].where(led["I2_v2"].notna(), led["I2"])
    lo = led["loo_ok_v2"].where(led["loo_ok_v2"].notna(), led["loo_ok"])
    led["stability_ok_v2"] = (cp > 0.10) & (i2 < 0.50) & (lo == True)
    led["shift_ok_v2"] = led["shift_delta"] < SHIFT_TOL      # reuse Run-1 point-estimate test
    led["A_v2"] = led["fdr_sig_v2"] & led["stability_ok_v2"] & led["shift_ok_v2"]

    led.drop(columns=["key"]).to_csv("research/m4/ledger_v2.csv", index=False)

    a1, a2 = set(led.index[led["A"]]), set(led.index[led["A_v2"]])
    surv = a1 & a2
    drop = a1 - a2
    new = a2 - a1
    lead_mask = (led["state"] == "m1") & (led["anchor"] == "A3") & (led["bucket"] == 0) & \
                (led["metric"].isin(["location_dir"]))
    lead = led[lead_mask]

    lines = []
    P = lines.append
    P("# M4 Run 1 — v2 moving-block-bootstrap inference  (2026-09-10)\n")
    P(f"Bootstrap: moving-block, B = {B_BOOT}, block ≥ H bars, (block×session)-stratified.\n")
    P(f"Re-validated the {len(sig):,} Run-1 FDR-significant cells; the other "
      f"{len(led) - len(sig):,} keep their Run-1 analytic p for the combined FDR.\n")
    P("## Gate counts\n")
    P("| gate | Run 1 (analytic) | v2 (block bootstrap) |")
    P("|---|---|---|")
    P(f"| FDR-significant | {int(led['fdr_sig'].sum())} | {int(led['fdr_sig_v2'].sum())} |")
    P(f"| + stable | {int((led['fdr_sig'] & led['stability_ok']).sum())} | "
      f"{int((led['fdr_sig_v2'] & led['stability_ok_v2']).sum())} |")
    P(f"| + shift-robust ⇒ A=YES | {int(led['A'].sum())} | {int(led['A_v2'].sum())} |\n")
    P(f"**A=YES survival:** {len(surv)} of {len(a1)} Run-1 A=YES cells survive the "
      f"block bootstrap; {len(drop)} drop; {len(new)} newly qualify.\n")
    if len(surv):
        s = led.loc[sorted(surv)]
        cls = s["state"].str[0].map({"m": "MARKET", "t": "TEMPORAL", "e": "EVENT"})
        P("### surviving A=YES by state class")
        P(s.assign(cls=cls).groupby("cls").size().to_string() + "\n")
        P("### surviving A=YES: directional vs non-directional")
        dirm = s["metric"].isin(["location", "location_dir", "race_1_1", "race_2_1", "race_1_2"])
        P(f"directional: {int(dirm.sum())}   non-directional: {int((~dirm).sum())}\n")
        if dirm.any():
            P("### surviving DIRECTIONAL A=YES cells")
            cols = ["state", "anchor", "bucket", "H", "metric", "effect", "effect_v2",
                    "se_v2", "p_v2", "b1", "b2", "b3", "b4", "cochran_p_v2", "I2_v2",
                    "shift_delta", "n_S", "events_per_year"]
            P(s.loc[dirm, cols].to_string(index=False) + "\n")
    P("## PRIMARY LEAD — M1 LOW-vol regime × A3 new-1-day-extreme → location_dir\n")
    if len(lead):
        cols = ["H", "effect", "effect_v2", "se_v2", "p_v2", "b1", "b2", "b3", "b4",
                "cochran_p_v2", "I2_v2", "loo_ok_v2", "shift_delta",
                "fdr_sig_v2", "stability_ok_v2", "A_v2", "n_S", "events_per_year"]
        P(lead[cols].sort_values("H").to_string(index=False) + "\n")
        surv_lead = lead["A_v2"].sum()
        P(f"**Primary lead: {int(surv_lead)} of {len(lead)} horizon-cells survive as A=YES "
          f"under the block bootstrap.**\n")
    else:
        P("(no rows matched the primary-lead mask — check ledger)\n")
    txt = "\n".join(lines)
    open("research/m4/RUN1_V2_SUMMARY.md", "w", encoding="utf-8").write(txt)
    print("\n" + txt)
    print("\nwrote research/m4/ledger_v2.csv , research/m4/RUN1_V2_SUMMARY.md")


if __name__ == "__main__":
    main()
