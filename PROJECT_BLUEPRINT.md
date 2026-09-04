# XAUUSD Trading Edge — Project Blueprint

**Status:** M0–M2 ✅ · **M3 in progress — intraday family exhausted (H1–H3 KILLED, H4 skipped), PIVOTED TO SWING.**
· **H1/H1b** NY opening-range breakout — thin break-direction edge (t=+2.36), sub-cost, non-robust.
· **H2** London→NY momentum continuation — falsified: London direction ⇏ NY direction (t=−0.49 vs random).
· **H3** Asian-quiet → NY range expansion — mechanism reversed: quiet Asian night → *smaller* NY range; gold intraday vol persists.
· **H4** turn-of-month drift — **drafted, not run** (`research/H4_turn_of_month.md`): feasibility check showed a weak signal (window drift +26 bps, p≈0.09–0.19; day-of-week ANOVA p=0.36). Operator chose to skip and pivot rather than spend a cycle.
· **H5** daily L/S vol-targeted trend on gold — KILLED (§6a). Real edge (beats buy-hold +65% vs +1%, DD 28% vs 57%, PF 1.58) but DD duration 3.6 yrs, Sharpe 0.32, all edge in 2009–2015.
· **H6** 14-instrument trend book (metals/FX/indices/energy, Dukascopy daily) — KILLED (§6b). **Worse than gold alone** (Sharpe 0.19 vs 0.43). Not a correlation or concentration failure — the **trend premium was largely absent 2011–2020** ("CTA winter", documented industry-wide). Equal-wt buy-hold basket lost 27% in-sample. `research/H6_RESULT.md`.
**Walk-forward diagnostic (2023-01→2024-06, OOS untouched) — `research/WF_DIAGNOSTIC_RESULT.md`:** trend did **not** clear the bar even in this favourable window (H5 Sharpe 0.65, H6 0.49) and **lost to plain buy-and-hold** on return and Sharpe in both cases. The "2009–2022 was a drought" explanation is not supported — trend was mediocre in 2023–24 too; the only thing that worked recently was being long gold (the bull market).

**M3 SEARCH PHASE COMPLETE — negative result. Full write-up: `M3_CONCLUSION.md`.**
7 hypothesis families + feasibility checks, all KILLED: intraday breakout/momentum/vol/calendar/reversion/event (H1–H4 + checks), single-asset gold trend (H5), 14-instrument trend book (H6), 19-rule indicator screen, G7 FX carry (H7). The only ideas with any life — trend and carry — are regime-contingent premia: unpaid 2009–2022 (ZIRP / trend drought), revived in the 2023–24 rate-divergence walk-forward, then **failed the locked out-of-sample** (H7 carry OOS Sharpe −0.01; Aug-2024 yen unwind hit its short-JPY leg, skew −1.12). **Out-of-sample is now spent — one touch, on H7, as designed.**

**Bottom line:** no systematic strategy in the testable space clears the recalibrated bar on data it wasn't fitted to, at retail costs. The disciplined process prevented deploying ~10 strategies that looked good in one window and failed honest validation — that is the project's real output. Recommendation: don't deploy systematic capital; for gold exposure, DCA a physical-backed ETF. M4–M8 not entered (no validated edge to carry forward). What was built keeps its value: the M1 data pipeline, the M2 backtester, and a fully documented research log.
**Date:** 2026-09-04
**Owner:** Vijay

---

## 1. Verdict on the original 6-step plan

The 6 steps (pick market → form idea → gather data → build/test rules → measure/refine → live small) are a correct skeleton and match the standard systematic-trading workflow. They are not *wrong*, but as written they leave out the parts where retail edge projects usually fail. Corrections applied in this blueprint:

| # | Original step | Correction / addition |
|---|---------------|----------------------|
| 0 | *(missing)* | **Add a Charter step.** Fix capital, max tolerable drawdown, target return, screen time, kill criteria *before* touching data — otherwise rules have no pass/fail bar. |
| 1 | Pick market/asset | Done (XAUUSD spot, MT5 tick feed). Nail down instrument spec, data timezone, session definitions, and the real drivers (USD, real yields, risk sentiment). |
| 2 | Form a core idea | State each idea as a **dated, falsifiable hypothesis with a mechanism**, one at a time. "Gold mean-reverts in the Asian session" — not "gold mean-reverts". |
| 3 | Gather historical data | **Reserve the out-of-sample slice before any testing.** Run a data-quality report (gaps, bad ticks, timezone). Confirm ≥200–300 trades available, not just ≥N years. Label market regimes. |
| 4 | Build and test rules | Define the **full trade**: entry, initial stop, exit/target, time stop, position sizing. **Model spread + commission + slippage from the first backtest run**, not at step 6. Guard against look-ahead bias. Prefer walk-forward over a single backtest. |
| 5 | Measure and refine | Expand metrics (expectancy, profit factor, Sharpe/Sortino, drawdown depth **and** duration, trade count). Add robustness tests: parameter sensitivity, Monte Carlo on trade order, one locked out-of-sample run. Cap parameters and iteration count to fight overfitting. |
| 6 | Test with live money | Insert a **paper / forward-test stage on unseen live data first**. Then micro-size. Define **kill criteria upfront**. |
| — | *(cross-cutting)* | Risk framework (per-trade %, daily loss cap, max exposure). Trade journal + review cadence. Version-control the rules and the dataset for reproducibility. |

---

## 2. Data inventory — Dukascopy (sole source, verified 2026-09-04)

| Property | Finding |
|----------|---------|
| Location | `./dukascopy/{bid,ask}/year=YYYY/month=MM/ticks.parquet` (Hive-partitioned) |
| Format | Parquet: `time_msc` (int64 ms), `time` (datetime, UTC), `price` (double), `volume` (double, relative units — **non-zero, usable**), `flags` (0). Access flags as `df["flags"]`. |
| Content | `bid/` = bid-price ticks, `ask/` = ask-price ticks; pair on time for spread. |
| Timezone | **Native true UTC** — no correction needed. |
| Coverage | **2009-01 → 2026-09, COMPLETE**: 213/213 month-files, no gaps, bid=ask=213, ~16 GB, ~504M ticks/side. |
| QA spot-check | monotonic timestamps every month; zero negative spreads; price path matches real gold ($883 in 2009 → $4.5k in 2026). |
| Regimes covered | 2011–15 gold bear, 2013 crash, 2018 hikes, 2020 COVID, 2022 USD surge, 2023–25 bull — full cycle. |
| Fetcher | `download_dukascopy_ticks.py` — per-month Parquet, resumable, process-pool (lib not thread-safe), rate-limit hardened (45s socket timeout, exp backoff, per-day timeout + pool recycle, lockfile). Dukascopy soft-throttles heavy pulls; an IP change clears it. |
| Keep current | `python download_dukascopy_ticks.py --daily --workers 3` (schedule it). |

**History:** the project began on a Vantage/MT5 tick archive (2017-08 → 2026-09). Cross-checking it against Dukascopy exposed that its timestamps were **Vantage server time, not UTC** (GMT+2 flat through ~2018, then GMT+2/+3 DST — see `SOURCE_VERIFICATION.md` / `data_pipeline/mt5_utc_offsets.csv`). On 2026-09-04 that archive was **deleted** and Dukascopy made the sole source of truth. Vantage's history is anyway broker-limited (ticks served only from 2025-03-10 onward now), so it could not be rebuilt.

**Source rule — SINGLE SOURCE (2026-09-04):** the Vantage/MT5 tick archive was deleted; **Dukascopy is the sole source of truth**, 2009-01 → present, native true UTC. No source seams, no timezone correction.
- Canonical store = `./canonical/{bid,ask}/…`, true UTC, `source` column uniformly `1` (duka). 213 months.
- Cost model uses **Dukascopy spreads** (`qa/spread_by_year.csv`) — these run **~1 bp wider than Vantage Raw ECN** (per the earlier cross-check), so backtest costs are **conservative**: a validated edge should look slightly better live. Re-measure vs real Vantage fills at the forward-test stage.
- `data_pipeline/mt5_utc_offsets.csv` and `SOURCE_VERIFICATION.md` are retained only as historical record of the Vantage-server-time finding.

**M1 data-quality findings (Dukascopy):**
- Native UTC, zero duplicate timestamps, no bad-price prints.
- Crossed quotes: a few thousand total, concentrated in the March-2020 crisis — dropped.
- The earlier finding that *Vantage* ran GMT+2 through ~2018 then GMT+2/+3 DST is preserved in `mt5_utc_offsets.csv` for the record but no longer affects the pipeline.

**Data splits — extended vs the original blueprint** (now that pre-2017 exists): in-sample **2009-01 → 2022-12** (includes the 2011–15 bear), walk-forward **2023-01 → 2024-06**, out-of-sample **2024-07 → 2026-09** (touch-once, enforced in `dataset.load_bars`).

---

## 3. Charter — objectives, scope, constraints (Step 0 + Step 1)

| Item | Value |
|------|-------|
| Primary market / instrument | **XAUUSD spot CFD** on Vantage, **Raw ECN** account |
| Trading style | **Intraday first** (flat by session end). Swing / position are later, separate edges, only after the intraday pipeline is proven. |
| Execution | **Fully mechanical / automated.** Rules are code from day one; live via MT5 API or EA on Vantage MT5. |
| Number of edges | **One** edge, XAUUSD only. |
| Starting capital | **USD 100** for the ops test; **~USD 1,000 in the live account once a positive edge is found** (that is the size the edge is validated against). |
| Capital additions | Monthly deposits into this account only (amount TBC — Section 11). |
| Max drawdown you can stomach | **50%** (mental hard limit) |
| Target return | Any positive net growth above cumulative deposits. No fixed % target. |
| Screen time available | **9–12 hours/day**, trader in **IST (UTC+5:30)**. Fully automated, so this bounds session choice and monitoring windows, not manual trading. |
| Session focus | **New York** (leaning — most volatile), to be confirmed empirically in Phase 3. |
| Success bar priority | **Capital preservation** — shallow, short drawdowns first; return second. |
| Backtester | **Custom event-driven** (confirmed). |
| Toolchain | DuckDB (tick → bar aggregation, QA) · pandas (research) · custom event-driven backtester with real bid/ask fills · Python · MT5 for live. All rule logic version-controlled. |

### Live account facts (verified via MT5, 2026-09-04)

| Item | Value |
|------|-------|
| Broker / server | Vantage, `VantageMarkets-Live 7` (a **live**, not demo, account) |
| Account currency | **INR** — P&L, margin and USD commission are converted to INR. "USD 100 / 1,000" figures are notional; size against the INR equivalent. |
| Account max leverage | 1:2000 (setting); **gold is capped at 1:100** per your account — confirm the exact figure in-platform. |
| XAUUSD contract | contract size 100, digits 2, point 0.01, min lot 0.01, lot step 0.01 |
| Swap (if ever held overnight) | long −80.5 / short +32.7 (points) — intraday only, so not in scope now |

### Vantage Raw ECN — XAUUSD contract spec (from public sources, confirm in-platform)

| Spec | Value |
|------|-------|
| Contract size (standard XAUUSD) | **100 oz per 1.0 lot** → 0.01 lot = 1 oz; a $1.00 gold move = **$1.00** P&L on 0.01 lot |
| Min lot / step | 0.01 / 0.01 |
| Commission (Raw ECN) | ~**$3 per side** per 1.0 lot → **$6 round-turn** per lot → **$0.06 round-turn** per 0.01 lot |
| Typical spread | ~0.12–0.25 (use the **real per-tick spread from our own data** in backtests, not this average) |
| Leverage on gold | Stepped, up to ~100:1 depending on size/region — **confirm your account's actual gold leverage** (100:1 → ~$25 margin per 0.01 lot at $2,500; 500:1 → ~$5) |
| Trading hours | Standard XAUUSD ≈ 23h/day Mon–Fri with a ~1h daily break and weekend close (a separate 24/7 "XAUUSD247" product exists — not assumed here) |
| Swap / rollover | Applies to positions held past the daily rollover — irrelevant for pure intraday, relevant if a swing edge is added later |

---

## 3a. Reality check — $100 on a standard-contract gold account

This is the single biggest constraint on the project and it changes how we run the live phase.

- **Minimum-lot risk is coarse.** A sane intraday gold stop is ~$2–$8 wide. On the 0.01-lot minimum that is **$2–$8 of risk = 2%–8% of a $100 account per trade.** A 0.5% per-trade risk rule is impossible at this size — it would need a ~$0.50 stop, which is inside the spread. Fine-grained risk control only becomes possible around **$600–$1,200** of equity.
- **Cost drag is severe.** Round-turn friction ≈ $0.06 commission + ~$0.15–0.25 spread ≈ **$0.25–0.35 per 0.01-lot trade ≈ ~0.3% of a $100 account, per trade.** At 2 trades/day that is ~12%+ of the account per month in pure costs. The edge cannot be judged fairly at this size.
- **Margin head-room is thin.** At 100:1 gold leverage, each 0.01 lot ties up ~$25 — only ~3 minimum positions before margin exhaustion, and a normal losing streak can force a margin stop-out well before your 50% mental limit.

Since you'll fund the live account to **~$1,000 once an edge is found**, the edge is validated and sized against $1,000 from the start; the $100 only exists as an earlier hardware/plumbing check if you want one.

**Decision:** treat the $100 as a **live-fire operations test, not an edge test**.

| | Purpose | How results are judged |
|---|---------|------------------------|
| $100 live phase (M7) | Does the automation connect, place/modify/close orders, respect the kill switch; do live fills match backtest fills | Fill quality, latency, slippage vs model, zero operational bugs. **Not** P&L. |
| Edge validation (M2–M6) | Is the strategy actually profitable after real costs | Full Section 6 success bar, sized against a **realistic $1,000–$2,000 account** (your expected balance after ~6–12 monthly top-ups) |

Graduate from test-size to real risk sizing when equity clears **~$1,000**. Optional: ask Vantage whether a **1-oz contract / cent-style gold product** is available on Raw ECN — a 1-oz contract makes $100 genuinely viable by giving 100× finer position granularity.

---

## 4. Data split (frozen at M1, never re-drawn)

| Slice | Period | Purpose | Access rule |
|-------|--------|---------|-------------|
| In-sample / build | 2017-08 → 2022-12 | Develop and iterate rules | Unlimited |
| Walk-forward / tune | 2023-01 → 2024-06 | Parameter selection, robustness | Repeated, but no rule redesign |
| Out-of-sample / locked | 2024-07 → 2026-09 | Final honest estimate | **Touched once**, at M5 |

---

## 5. Risk framework (capital-preservation calibration)

**Edge-validation / real-account sizing (equity ≥ ~$1,000):**
- Risk per trade: **≤ 1%** of account equity (target 0.5%).
- Max daily loss: **3%** → stop trading for the day.
- Max concurrent positions: **1** (intraday phase).
- Backtest max-drawdown design target: **≤ 20%**. (A backtested 20% often becomes 35–45% live — that must stay under your 50% limit.)
- No martingale / no averaging into losers. Fixed-fractional or volatility-scaled sizing only.

**$100 live-fire test sizing (M7 only, not an edge test):**
- Fixed **0.01 lot**, hard stop **≤ $5** (≤ 5% of $100), 1 position at a time.
- Daily loss cap: **1 trade** or **$5**, whichever first.
- Expect variance + cost drag alone can take this account to −30% to −50%. That is acceptable for a test; it is why P&L is not the metric here.

---

## 6. Success bar

### 6a. Single-asset XAUUSD strategy — recalibrated (2026-09-04)

M1–M4 showed the original bar (§6b) is not reachable by *any* single-instrument
strategy on XAUUSD — a single volatile asset structurally tops out near Sharpe
0.4–0.5. Sharpe ≥ 1.0 needs a portfolio of uncorrelated edges (§11 secondary
goal), pursued **after** one edge is validated. The recalibrated bar below matches
the charter's actual priorities (capital preservation *relative to holding gold*;
any positive return; 50 % DD tolerable). A single-asset strategy must clear ALL:

| Metric | Threshold |
|--------|-----------|
| **Core** | Beats buy-and-hold XAUUSD on **both** total return **and** max drawdown, in-sample |
| Max drawdown (0.5 %-risk / vol-targeted run) | ≤ 30 % (vs buy-hold ~45 %; well under the 50 % limit) |
| Max drawdown duration | ≤ ~12 months |
| Profit factor | ≥ 1.15 |
| Annualized Sharpe / Sortino | ≥ 0.5 / ≥ 0.7 |
| Expectancy / CAGR after costs (spread + $6/lot + slippage + swap on holds) | > 0 |
| Robustness across regimes | net-positive in **both** 2009–2015 and 2016–2022 |
| Out-of-sample degradation | CAGR / Sharpe retains ≥ 60 % of in-sample |
| Parameter robustness | survives ±25 % on every parameter (plateau, not spike) |

### 6b. Portfolio target (original bar) — for a combined book of ≥ 2 uncorrelated edges

| Metric | Threshold |
|--------|-----------|
| Max drawdown (out-of-sample) | ≤ 20 %, target ≤ 12 % |
| Max drawdown duration | ≤ ~3 months |
| Profit factor | ≥ 1.25 |
| Annualized Sharpe / Sortino | ≥ 1.0 / ≥ 1.5 |
| Expectancy after costs | > 0 |
| Out-of-sample degradation | retains ≥ 65 % of in-sample |
| Parameter robustness | ±25 % plateau |

## 7. Kill criteria — stop a live strategy immediately if ANY trigger

- Live drawdown exceeds **1.5×** the backtested max drawdown, **or hits 35% of equity** (whichever first — leaves buffer under your 50% limit and under margin stop-out).
- **6** consecutive losing weeks.
- Live expectancy drops below **50%** of the backtested value over a rolling 50-trade window.
- A data or execution bug is found that invalidated prior results.
- **50% equity drawdown = absolute stop.** Shut the system off, full review before any restart.

---

## 8. Phases

- **Phase 0 — Charter.** This document, signed off. Define objectives, risk, success bar, kill criteria.
- **Phase 1 — Data foundation.** Tick loader; **UTC normalisation of the MT5 archive** (per-month offset table cross-checked vs Dukascopy, snap to nearest 15 min at corr > 0.95, manual review below that); merge per the source-precedence rule; cleaning (gaps, bad ticks, outliers); spread series from the Vantage feed; tick→bar aggregation (1m/5m/15m). QA report (seam checks at 2017-08 and 2020-02, session coverage, gap map). Freeze the three splits.
- **Phase 2 — Research harness.** Event-driven backtester that fills at real bid/ask, applies commission + slippage. Metrics module. Validate the harness against a known trivial strategy (e.g. buy-and-hold, random entries) so we trust the numbers.
- **Phase 3 — Hypothesis #1.** Write it dated and falsifiable. Run end-to-end on in-sample. Record the result **whether or not it works** — a clean negative is a valid outcome.
- **Phase 4 — Validation.** Walk-forward tune, parameter-sensitivity grid, Monte Carlo on trade order. Strategy must clear the in-sample + walk-forward bar.
- **Phase 5 — Locked out-of-sample.** One run on 2024-07 → 2026-09. Pass or discard.
- **Phase 6 — Forward test.** Paper-trade on the live MT5 feed, ≥ 20 trading days, compare live fills and expectancy to backtest.
- **Phase 7 — Live-fire ops test ($100).** 0.01 lot fixed. Purpose: prove the automation (connect, order, modify, close, kill switch) and measure live fill quality vs the backtest model. **P&L is not the pass criterion.**
- **Phase 8 — Scale to real sizing.** Once equity ≥ ~$1,000 (via growth + monthly deposits) and ops are clean, move to the Section 5 real-account risk rules. Size up only while live tracks the backtest; otherwise shelve this edge and return to Phase 3 with the next hypothesis.

---

## 9. Milestones (gate-based, not calendar-based)

| ID | Milestone | Done when |
|----|-----------|-----------|
| **M0** | Charter signed off | ✅ 2026-09-04 |
| **M1** | Data pipeline live | ✅ 2026-09-04 — single-source Dukascopy. `./canonical/` true-UTC cleaned store (213 months, 685M ticks/side); `./bars/{1min,5min,15min}/` (6.3M/1.3M/428k bars, 2009–2026); `dataset.load_bars(tf, split=…)` with frozen splits + OOS touch-once guard; `qa/M1_QA_REPORT.md` (+4 CSVs). QA: session coverage median 98.9%, no unexplained outages, UTC verified (peak 14:00 UTC), zero source seams. |
| **M2** | Backtester trusted | ✅ 2026-09-04 — `backtest/` event-driven engine (t+1-open fills, stop/target/time/session exits, mid-to-mid PnL + single friction charge = real Dukascopy spread + $6/lot + slippage, ruin guard). Validated: hand-checked trade exact, look-ahead-safe, buy&hold gross = raw move, **random entries lose exactly their costs** (gross≈0). `metrics.py` emits full success-bar table + Monte-Carlo. See `backtest/M2_VALIDATION.md`. |
| **M3** | First edge that clears the in-sample bar | 🔄 in progress. Intraday family exhausted: **H1/H1b** breakout, **H2** momentum, **H3** vol-cycle all KILLED; **H4** calendar drafted-not-run (weak feasibility). Write-ups `research/H*_RESULT.md`. **Pivoted to swing** (charter's later phase, brought forward). Next: **H5** = daily-bar long/short vol-targeted time-series momentum on gold — directly targets the capital-preservation priority. Open question: a single-asset system may not clear Sharpe ≥ 1.0; if it clears expectancy + DD + PF, that triggers an M3→M4 bar-recalibration / portfolio discussion rather than an auto-KILL. |
| **M4** | A strategy clears in-sample + walk-forward | Meets every success-bar threshold on build + tune slices; passes parameter-plateau and Monte-Carlo checks |
| **M5** | Out-of-sample pass | Single locked run on 2024-07 → 2026-09 meets the bar with ≤ 35% degradation |
| **M6** | Forward test pass | ≥ 20 live-feed paper-trading days; live expectancy within tolerance of backtest |
| **M7** | Live-fire ops test passed | 0.01-lot automated execution on the $100 account for ≥ 20 trading days: fills match model within tolerance, kill switch verified, zero operational bugs |
| **M8** | Scale / shelve decision | Equity ≥ ~$1,000 and documented decision to move to real-sizing rules, hold, or shelve and move to next hypothesis |

---

## 10. Goals

**Project goal:** Produce at least one fully mechanical intraday XAUUSD strategy that clears the Section 6 success bar on locked out-of-sample data and survives a live forward test, with capital preservation (shallow, short drawdowns) as the defining constraint.

**Process goals:**
1. Every result is reproducible from version-controlled code + the frozen data splits.
2. The out-of-sample slice is touched exactly once per strategy.
3. No more than ~5 build iterations per hypothesis before it is accepted or rejected (overfitting guard).
4. Negative results are documented and kept, not discarded.
5. Costs are modelled from real per-tick spread on every backtest — never assumed.

**Secondary / later goals (after the intraday pipeline is proven):**
- Reuse the harness to develop a swing edge (H1–D1).
- Combine uncorrelated edges into a small portfolio to further reduce drawdown.

---

## 11. Open items (nice-to-have, do not block M1)

1. **Exact gold leverage** for XAUUSD on your account — confirm the 1:100 figure in-platform (sets margin head-room and max position count).
2. **Approx monthly deposit** — informs how fast the live account can be scaled after go-live.
3. **Hard flat-by time (UTC)** for the intraday edge once we settle on the NY session in Phase 3 (e.g. 21:00 UTC).
4. **1-oz / cent gold product on Raw ECN?** — optional question to Vantage support; would let the $100 phase double as a small edge test.

Resolved: capital ($100 ops / ~$1,000 live), max DD (50%), one edge XAUUSD only, fully automated, IST trader with 9–12h/day, NY-session lean, custom event-driven backtester.
