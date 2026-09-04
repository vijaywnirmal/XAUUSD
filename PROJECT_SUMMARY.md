# XAUUSD Trading-Edge Project — Full Summary

**Period:** 2026-09-04 (single intensive build)
**Goal:** find a repeatable, fully-mechanical intraday trading edge for XAUUSD on a
small ($100–1,000) Vantage Raw ECN account, with **capital preservation** (shallow,
short drawdowns) as the defining priority.
**Outcome:** no deployable edge found. A rigorous negative result, plus reusable
infrastructure and a documented research trail. The one marginal exception — an
NFP-release breakout straddle — beats its null but is too small and too
slippage-fragile to fund (see §2).

---

## 1. What we built

### M1 — Data foundation (`data_pipeline/`, `./canonical/`, `./bars/`)

| Piece | What it is |
|---|---|
| `download_mt5_ticks.py` | Vantage MT5 tick downloader — adaptive chunking, resumable, `--probe-earliest`, daily Task-Scheduler install. (Vantage archive later retired.) |
| `download_dukascopy_ticks.py` | Dukascopy tick archiver — per-month Parquet, process-pool, rate-limit hardened (socket timeout, exponential backoff, pool-recycle, lockfile). Pulled **2009-01 → 2026-09, 213 months, ~504 M ticks/side, ~16 GB**. |
| `verify_sources.py` | Cross-checks the Vantage feed against Dukascopy; this is how the server-time (non-UTC) problem was found. |
| `data_pipeline/config.py` | Frozen data splits, source rules, cleaning thresholds. |
| `data_pipeline/build_canonical.py` | → `./canonical/{bid,ask}/` — true-UTC, cleaned (dedup, crossed-quote removal, price sanity) tick store. 213 months, ~685 M ticks/side. |
| `data_pipeline/build_bars.py` | → `./bars/{1min,5min,15min}/` — OHLC of mid, bid/ask close, tick count, mean/median spread, volume. 6.3 M 1-min bars. |
| `data_pipeline/dataset.py` | `load_bars(tf, split=…)` — enforces the frozen splits; **out-of-sample is touch-once** (raises without `allow_oos=True`). |
| `data_pipeline/qa_report.py` | → `qa/M1_QA_REPORT.md` — coverage, gap map, UTC-sanity histogram, spread-by-year, seam checks. |

**Data splits (frozen):** in-sample 2009-01 → 2022-12 · walk-forward 2023-01 →
2024-06 · out-of-sample 2024-07 → 2026-09 (**spent once, on H7**).

### M2 — Research harness (`backtest/`)

| Piece | What it is |
|---|---|
| `backtest/engine.py` | Event-driven bar backtester. Entries fill at **t+1 open** (no look-ahead). Exits: signal, stop, target, trailing stop, time-stop, session-flat, reverse-on-opposite. **Stop wins on a bar that touches both stop and target.** Ruin guard. Costs = one explicit friction charge per trade: real per-bar Dukascopy spread + slippage + $6/lot commission (+ swap/carry on multi-day holds). |
| `backtest/metrics.py` | Metrics, the Section-6 success-bar table (PASS/FAIL), Monte-Carlo on trade order. |
| `backtest/strategy.py`, `backtest/run.py` | Strategy registry + CLI runner. |
| `backtest/tests/test_engine.py` | Hand-checked correctness: exact PnL on a synthetic trade, look-ahead safety, stop-pessimism, trailing stop, and **"a no-edge strategy loses exactly its costs"**. All pass. |

### M3 — Research scripts (`research/`)

`h1.py`, `h1b.py`, `h2.py`, `h3.py`, `h5.py`, `h5_forensics.py`, `h6.py`,
`fetch_basket.py`, `h7_carry.py`, `h8_macro.py`, `indicator_screen.py`,
`wf_diagnostic.py`, `nfp_study.py`, `nfp_straddle.py` — plus one `H*_RESULT.md` /
`*_RESULT.md` write-up per hypothesis, and the `basket/` (14 daily-bar
instruments), `carry/rates_3m.csv` (7-currency 3-month rates, from FRED) and
`macro/gold_drivers.csv` (real yield + broad dollar, from FRED) datasets.

---

## 2. What we tested — and the verdict on each

| # | Hypothesis | Mechanism | Verdict |
|---|---|---|---|
| **H1 / H1b** | NY opening-range breakout (13:30–14:00 UTC range, break during 14:00–18:00, flat 20:00) | US data + equity-open flow → range break continues | **KILL.** Break direction had a real but tiny signal (beat random-direction null, Welch t = +2.36; gross +0.05 R/trade) — smaller than the ~0.10 R cost. H1b's "sensible" filters (close-confirm, daily-bias, trail) *collapsed* the t-stat to +1.01. |
| **H2** | London→NY momentum continuation (decisive 07:00–12:00 move → enter 12:00 UTC with-trend) | month-end / institutional flow persists into NY | **KILL.** London direction carries **no information** about NY direction — Welch t = **−0.49** vs random. P&L rode on 2013 alone. |
| **H3** | Asian-quiet → NY range expansion (quiet Asian night → two-sided straddle) | volatility contraction precedes expansion (NR7 / squeeze) | **KILL.** Mechanism runs **backwards** — a quiet Asian night is followed by a *smaller* NY range (0.89 vs 1.01 ATR). Gold intraday vol *persists*; the quiet filter was counter-productive. |
| **H4** | Turn-of-month drift | calendar-locked rebalancing flows | **Not run.** Feasibility: window drift +26 bps but p ≈ 0.09–0.19; day-of-week ANOVA p = 0.36. Skipped by choice. |
| — | Short-horizon reversion (fade > 2.5 σ 5-min moves) | overreaction reverses | **Dead.** −0.13 bps over 5 min (≈ 1/10 of cost), noise thereafter. |
| — | NFP-day behaviour (descriptive study) | scheduled macro shock | **Mostly empty.** ~2× volatility (stable across 17 yrs), direction unpredictable, no pre-drift. One weak signal: the knee-jerk move *continues* to the session close (t = 2.24), not reverses. |
| **H5** | Daily long/short vol-targeted trend on gold (3m + 12m sign blend) | time-series momentum — under-reaction + flow feedback | **KILL.** A *real* edge — beat buy-and-hold **+65 % vs +1 %**, drawdown **28 % vs 45 %**, profit factor 1.58, beat the random-sign null. But Sharpe only **0.32** after costs, a **3.6-year** drawdown, and **all the edge is 2009–2015** (2016–2022 flat). |
| — | H5 + "trade only good environments" filter | learn the winners' regime, gate to it | **KILL.** Winners concentrated in low-vol entries. A fitted gate improved in-sample (Sharpe 0.32 → 0.40, DD 28 % → 18 %) and made the **walk-forward worse** (0.65 → 0.57). An unfitted threshold did nothing. Textbook overfit. |
| **H6** | 14-instrument trend book (metals, FX, indices, energy) — vol-targeted portfolio | trend is a *cross-asset* premium; diversification lifts Sharpe | **KILL.** Sharpe **0.19** — *worse* than gold alone. Not a correlation (ρ = 0.17) or concentration failure. The **trend premium was absent industry-wide 2011–2020** ("CTA winter"). The equal-weight buy-and-hold basket lost 27 % in-sample. |
| — | 19 classic indicator rules (SMA/EMA cross, RSI, MACD, Bollinger, Donchian, Stochastic, ADX, CCI, Keltner, Ichimoku, Connors RSI2), default params | technical analysis | **KILL.** In-sample **and** walk-forward: **none** beat buy-and-hold *and* survive Bonferroni multiple-testing correction. Top rules differ between windows = noise. Buy-and-hold beat almost every rule after costs. |
| **H7** | G7 FX carry (rank EUR/GBP/JPY/AUD/NZD/CAD by rate vs USD; long high-carry, short low-carry) | the carry risk premium | **KILL.** Dead 2009–2022 (Sharpe −0.05 — G7 rates were ~zero, no differential to harvest). **Sharpe +1.00 on the 2023–24 walk-forward** (rates had diverged). **Sharpe −0.01 out-of-sample** (2024–26): rates converged, the Aug-2024 yen carry unwind hit the short-JPY leg, skew **−1.12**. |

| **NFP straddle** | On every NFP release, OCO stop orders around the pre-release 30-min box (+$0.50), $30 stop, flat 20:00 UTC, 0.01 lot. 212 events. | capture the direction of the NFP break and ride the documented post-spike continuation | **MARGINAL — the only non-negative result.** Beats the random-direction null ~10× (in-sample 2009–2022 **+$1.79/trade, PF 1.47, t = 1.87**, positive in both halves, 13/18 years green). But: the $30 stop hits only 13/212 (it's really "ride to the close with a disaster stop"); slippage-bound — in-sample edge falls to **+$0.85/trade, PF 1.20** at $0.50 adverse fill, and NFP is the worst moment for retail fills; ~**2%/yr at minimum lot** vs a 12% drawdown; a take-profit *hurts*; the strong 2023–26 numbers are partly a fixed-$ artifact of gold's price doubling. **Not deployable alone** — at best a tiny satellite overlay after paper-trading live NFP fills. Full write-up: `research/NFP_STRADDLE_RESULT.md`. |

The walk-forward diagnostic (`research/WF_DIAGNOSTIC_RESULT.md`) confirmed trend
also fails on 2023–24 and **loses to buy-and-hold** even there.

---

## 3. What we learned

### About the data
- **Broker tick archives are in server time, not UTC**, and their retention window
  rolls forward — Vantage now only serves XAUUSD ticks from 2025-03. Capturing and
  archiving data is load-bearing; you cannot rebuild it later.
- Vantage's server-time DST policy *changed* over the years (GMT+2 flat through
  ~2018, then GMT+2/+3 with summer DST). Detected per-month by cross-correlating
  against Dukascopy.
- **`volume` in FX/CFD tick data is usually unusable** (MT5 feed = all zeros).
- Dukascopy is a viable free source back to ~2009 for FX, metals, indices and
  commodities; it soft-throttles sustained pulls, and an IP change resets it.

### About cost
- Retail round-trip cost on XAUUSD ≈ **$0.30–0.60 per trade** at 0.01 lot ≈
  **1.5–3 bps**. **Every intraday edge found was smaller than this.**
- A no-edge strategy loses **≈ exactly its transaction cost** — validated in the
  engine and reproduced by every random/coin-flip/fixed-target variant tested.
- "No stop loss + fixed target + alternate direction" produces a 96 % win rate
  and **−$1,173 on a single trade** (117 % of a $1,000 account). High win rate is
  a warning sign, not a feature — the tricks move the loss into a fat left tail,
  they don't remove it.

### About gold's predictability
- **Intraday direction (5-min / session scale) is close to a random walk.** Every
  directional intraday hypothesis came in at or below the cost/noise threshold.
- **Intraday volatility persists** (it does *not* contract-then-expand at this
  scale) — the opposite of the equity NR7 effect.
- **Daily trend** on gold has a genuine edge that beats buy-and-hold on return and
  drawdown, but it is low-Sharpe (~0.3–0.4 after costs), has multi-year drawdowns,
  and is concentrated in one 2009–2015 regime.

### About trend and carry as premia
- **2011–2020 was a documented, industry-wide drought for trend-following** ("CTA
  winter") and **2012–2021 had no FX carry to harvest** (synchronised zero rates).
  Our entire in-sample window sits inside this drought.
- Both premia **revived in the 2023–24 rate-normalisation window** (trend weakly,
  carry to Sharpe 1.0) and **both failed again in the 2024–26 out-of-sample** as
  rates converged. Their viability is contingent on a macro regime nobody can
  forecast, and carry's crash tail materialised out of sample.

### About diversification
- The portfolio-Sharpe math — single-instrument Sharpe × √(N / (1 + (N−1)ρ)) —
  needs **N ≈ 50–300 uncorrelated** instruments to turn Sharpe 0.4 into ~1.0.
  Fourteen correlated CFDs from one broker made things *worse*, not better.

### About overfitting (demonstrated three times on our own data)
- H1b — adding "confirmation" filters to H1 collapsed the edge (t 2.36 → 1.01).
- H5 forensics — a filter fitted to the winning trades improved in-sample and hurt
  the walk-forward.
- Indicator screen — the best rule in-sample was not the best on walk-forward;
  nothing survived multiple-testing correction.
- **This is why the blueprint reserved held-out data and pre-registered every
  hypothesis.** It stopped ~10 promising-looking backtests — including one at
  Sharpe 1.0 — from being deployed.

### About market structure
- Professionals profit through **speed** (HFT — you pay the spread they earn),
  **breadth** (200+ uncorrelated pods / 300 markets), **leverage** (5–15× on
  diversified books at cheap institutional financing), and **alt-data budgets**.
  None of these are available on a small retail CFD account.
- A $100–1,000 account, one asset, high costs, no useful leverage, ~20 correlated
  instruments, free daily data, and retail latency is close to the **single
  hardest version** of the systematic-trading problem — and gold is one of the
  most-analysed instruments in the world.
- What *is* retail-accessible is **risk premia** (equity, gold's long drift,
  volatility selling, carry) — modest returns, real drawdowns, no "edge" required.

### About the success bar
- The original bar (Sharpe ≥ 1.0, Sortino ≥ 1.5, DD ≤ 20 %) is **structurally
  unreachable by any single-instrument strategy**. It was split into §6a
  (single-asset: beats buy-and-hold on return *and* DD, Sharpe ≥ 0.5, DD ≤ 30 %)
  and §6b (portfolio target = the original). Even §6a was not cleared
  out-of-sample.

---

## 4. Bottom line

**No systematic strategy in the space that could be tested — intraday price
patterns, single- and multi-asset time-series trend, technical indicators, FX
carry, macro-conditioned gold — robustly clears even the recalibrated bar on data
it was not fitted to, at retail costs.** The closest thing to an exception, an
NFP-release breakout straddle, beats its random-direction null and is positive
in-sample across both halves, but its edge is ~$1–2 per trade (≈ 2%/yr at minimum
lot), it nearly evaporates under realistic NFP slippage, and its t-stat sits just
under the significance bar — a candidate for a tiny satellite overlay after live
forward-testing, not a fundable standalone edge.

This is a **negative result, and the process produced it on purpose.** Roughly ten
strategies looked good in some window; none survived honest validation. The
discipline (dated falsifiable hypotheses, cost-realistic backtests, a touch-once
out-of-sample, multiple-testing awareness) is what turned "promising backtests"
into "do not fund these."

### Recommendation
1. **Do not deploy systematic capital** on anything tested here.
2. **For gold exposure:** dollar-cost-average a physical-backed gold ETF — no
   spread, no swap, no leverage decay. H5 tried to beat this and could not do so
   robustly.
3. If the search resumes later, the honest options are all *harder*, not easier:
   options-volatility selling (needs an options account + tail hedging), a
   genuinely broad futures trend book (needs a futures broker + 50+ markets), or
   discretionary macro (not mechanical).

### What keeps its value
The M1 data pipeline, the M2 backtester, and the full `research/` log — reusable
immediately if the search resumes under different constraints.

---

## 5. File index

```
PROJECT_BLUEPRINT.md        charter, milestones, recalibrated success bar
M3_CONCLUSION.md            the edge-search conclusion (this doc's short form)
PROJECT_SUMMARY.md          this file

data_pipeline/              M1 — canonical store, bars, splits, QA
  build_canonical.py  build_bars.py  dataset.py  qa_report.py  config.py
  mt5_utc_offsets.csv       historical record of the Vantage server-time finding
download_dukascopy_ticks.py / download_mt5_ticks.py   data fetchers
verify_sources.py           Vantage vs Dukascopy cross-check

canonical/  bars/  dukascopy/   the data (true-UTC ticks, bars, raw Dukascopy)
qa/                          M1_QA_REPORT.md + supporting CSVs
_fetch_state/               fetcher state / logs

backtest/                   M2 — engine, metrics, strategies, tests
  engine.py  metrics.py  strategy.py  run.py  M2_VALIDATION.md
  tests/test_engine.py

research/                   M3 — one script + one RESULT.md per hypothesis
  H1_*  H1b_*  H2_*  H3_*  H4_*  H5_*  H5_FORENSICS_*  H6_*
  INDICATOR_SCREEN_*  WF_DIAGNOSTIC_*  H7_CARRY_*  H8_MACRO_*
  NFP_STUDY_RESULT.md      descriptive NFP behaviour study (+ nfp_days.csv)
  nfp_straddle.py  NFP_STRADDLE_RESULT.md  nfp_straddle_trades.csv
  basket/                   14 daily-bar instruments (Dukascopy)
  carry/rates_3m.csv        7-currency 3-month interbank rates (FRED)
  macro/gold_drivers.csv    10y real yield + broad dollar (FRED)
```
