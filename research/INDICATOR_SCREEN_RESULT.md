# Indicator-setup screen — gold daily bars

**Run:** 2026-09-04. 19 classic technical rules, **default parameters (no tuning)**,
long/short/flat daily positions, ~2 bp round-trip cost + 2 %/yr carry. Each scored
vs buy-and-hold and vs a **random-sign null** (2,000 shuffles of the same position
magnitudes → empirical p-value on Sharpe). Multiple testing made explicit.

Rules: SMA 50/200, EMA 20/50, price vs SMA200 (L/flat and L/S), ROC(20) & ROC(120)
sign, MACD > signal, RSI14 momentum, RSI14 oversold-reversion, Connors RSI2,
Bollinger(20,2) reversion & breakout, Donchian 20/10 & 55 (Turtle),
Stochastic(14,3), ADX>25 + DI, CCI(20), Keltner(20,1.5), Ichimoku.

---

## In-sample 2009–2022

Buy & hold: Sharpe **+0.15**, CAGR +1.1 %, maxDD 54 %.

| Best rules | Sharpe | CAGR | maxDD | in-mkt | p_null | beats BH? |
|---|---|---|---|---|---|---|
| Connors RSI2 | +0.23 | +1.0 % | 15 % | 10 % | 0.044 | yes |
| price vs SMA200 (L/flat) | +0.19 | +1.4 % | 34 % | 57 % | 0.009 | yes |
| SMA 50/200 cross (L/S) | +0.12 | +0.8 % | 54 % | 96 % | 0.002 | no |
| Donchian 20/10 | +0.12 | +0.6 % | 24 % | 41 % | 0.035 | no |
| *(15 more, Sharpe ≤ +0.06 down to −0.34)* | | | | | | |

**19 rules tested → ~1 false positive expected at p < 0.05. Bonferroni threshold
= 0.0026. Rules that beat buy-and-hold AND survive the correction: NONE.**

The rules with tiny p_null (SMA 50/200 = 0.002, Stochastic = 0.006) are just the
*trend* rules — their low p reflects "being mostly-long during a gold bull market
beats a random sign", not an edge; they don't beat buy-and-hold and carry a 54 %
drawdown.

## Walk-forward 2023-01 → 2024-06

Buy & hold: Sharpe **+0.87**, CAGR +10.8 %, maxDD 12 %.

| Best rules | Sharpe | in-mkt | p_null | beats BH? |
|---|---|---|---|---|
| RSI14 oversold-reversion | +1.10 | **6 %** | 0.038 | yes |
| price vs SMA200 (L/flat) | +0.85 | 47 % | 0.051 | no |
| Connors RSI2 | +0.76 | 7 % | 0.108 | no |
| *(16 more, ≤ +0.66 down to −0.96)* | | | | |

**Again: NONE survive Bonferroni.** The single rule that "beats" buy-and-hold
(RSI14 oversold-reversion, Sharpe 1.10) is in the market **6 % of the time** —
CAGR +3.5 % vs buy-and-hold's +10.8 % — so it barely participates, and it does not
survive multiple-testing correction.

**No consistency between windows.** The in-sample top rules (Connors RSI2,
price>SMA200) are not the walk-forward top rules and vice versa. Rank order is
essentially random across the two periods → noise.

---

## Verdict

The full classic indicator toolkit, tested honestly on gold — default parameters
(so no curve-fitting), realistic costs, random-sign null, Bonferroni multiple-
testing correction, on two independent windows — produces **nothing that beats
buy-and-hold on a risk-adjusted basis beyond what chance explains.** In both
windows, buy-and-hold beat almost every indicator rule after costs.

This closes the "indicator setups" category, consistent with the peer-reviewed
technical-analysis literature (after data-snooping correction, indicator rules do
not beat buy-and-hold on liquid developed markets). Combined with H1–H6, the
reversion check, the NFP check, and the H5 forensics, essentially the entire
retail-accessible systematic strategy space on XAUUSD has now been screened.

**Genuinely untested, with a real prior:** carry (FX/commodity), cross-sectional
relative value, options-volatility selling (needs different data). Everything
price-and-indicator-based on gold itself has been checked.
