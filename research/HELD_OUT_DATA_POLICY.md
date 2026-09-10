# Held-out data policy  (FROZEN 2026-09-10)

Project-wide.  Governs every future strategy / hypothesis, not just M4.
Referenced by `research/CONDITIONAL_RESEARCH_PROTOCOL.md` and
`research/m4/LAYER_C_ADDENDUM_primary_lead.md`.

## Current state — BOTH historical held-out windows are EXHAUSTED

`data_pipeline/config.py` `SPLITS`:

| split | window | status |
|---|---|---|
| `in_sample` | 2009-01-01 → 2023-01-01 | discovery / fitting — always was |
| `walk_forward` | 2023-01-01 → 2024-07-01 | **SPENT** — used as the routine second window all through M1–M3 (H1, H5, H6, H7, wf_diagnostic, indicator screen, …) and inspected as block **P3** during M4 Run 1 + v2. Never was touch-once; now fully contaminated. |
| `out_of_sample` | 2024-07-01 → 2026-09-04 | **SPENT ×3+** — the touch-once guard was overridden with `allow_oos=True` for (1) H7 carry final OOS test (2026-09-04), (2) H2 continuation pre-registered OOS test (2026-09-10), and (3) M4 `build_events.py` (Run 1 + v2 include it as block **P4**, and `primary_lead_signal.py --reference` reads it). Block-inspected during M4 discovery. |

**Consequence:** neither `walk_forward` nor `out_of_sample` can serve as an
independent held-out test for any hypothesis any more.  They are **historical
description only** from here on.

## Rules going forward

1. **No pass/fail decision may rest on `walk_forward` or `out_of_sample`.**  A
   strategy is not "validated" because it worked on either window.  They may be
   *read* for descriptive purposes (regime characterisation, feature
   distributions, event rates) but not used as a gate.

2. **Do not pass `allow_oos=True` again.**  Needing it means you are about to
   contaminate spent data — stop.  The guard now points here.

3. **The only valid out-of-sample test for anything new is forward-paper time:**
   data whose timestamps are strictly *after* the hypothesis AND its extraction
   rule are frozen and committed to git.  Pre-register the decision rule and the
   PASS / FAIL / INCONCLUSIVE criteria first (see the M4 addendum as the template),
   then let real time accumulate.

4. **Declaring a fresh held-out window** (if ever wanted) requires: a cutoff date
   `C` that post-dates every prior analysis touch; a dated note in this file
   fixing `C`; and from then on that window `[C, …)` is touch-once — one final
   validation run, recorded here, then done.

5. **New hypotheses discovered on `in_sample`** get their per-period robustness
   from *sub-blocks of `in_sample` itself* (e.g. 2009–15 vs 2016–22) plus forward
   paper — never from `walk_forward` / `out_of_sample` as if those were clean.

6. This policy is frozen.  Amend only with a dated entry below.

## Change log

- **2026-09-10 — v1.** Recorded WF + OOS exhaustion (H7, H2, M4). Rules 1–6 set.
