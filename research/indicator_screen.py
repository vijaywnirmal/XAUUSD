"""
Broad indicator-setup screen on gold daily bars.

~20 classic technical rules, DEFAULT parameters (no tuning), long/short/flat daily
positions. Each is scored vs buy-and-hold and vs a random-sign null (2000 shuffles
of the same position magnitudes) -> empirical p-value on Sharpe. Multiple-testing
is made explicit: with N rules, expect ~N*alpha false positives.

    python -m research.indicator_screen                 # in-sample
    python -m research.indicator_screen --split walk_forward
"""
import argparse
import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars

COST_BP = 2.0e-4          # round-trip, per unit turnover (gold ~1.5bp spread + slip)
CARRY_ANN = 0.02
TD = 252


def daily(split, start=None, end=None):
    df = load_bars("1min", split=split, start=start, end=end, allow_oos=False,
                   columns=["ts", "open", "high", "low", "close"])
    d = df.set_index("ts").resample("1D").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last")).dropna(subset=["close"])
    return d


# ---- indicator primitives (pure pandas) ---------------------------------------
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def sma(s, n): return s.rolling(n).mean()

def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))

def atr(d, n=14):
    tr = pd.concat([d.high - d.low, (d.high - d.close.shift()).abs(),
                    (d.low - d.close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def adx(d, n=14):
    up = d.high.diff(); dn = -d.low.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(d, n)
    pdi = 100 * pd.Series(plus, index=d.index).ewm(alpha=1/n, adjust=False).mean() / a
    mdi = 100 * pd.Series(minus, index=d.index).ewm(alpha=1/n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1/n, adjust=False).mean(), pdi, mdi

def stoch(d, n=14, k=3):
    ll = d.low.rolling(n).min(); hh = d.high.rolling(n).max()
    kf = 100 * (d.close - ll) / (hh - ll).replace(0, np.nan)
    return kf.rolling(k).mean()

def cci(d, n=20):
    tp = (d.high + d.low + d.close) / 3
    return (tp - tp.rolling(n).mean()) / (0.015 * tp.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True))


# ---- rules: return a daily target position in {-1,0,+1} (pre-shift) ----------
def rules(d):
    c = d.close
    R = {}
    R["SMA 50/200 cross (L/S)"] = np.sign(sma(c, 50) - sma(c, 200))
    R["EMA 20/50 cross (L/S)"] = np.sign(ema(c, 20) - ema(c, 50))
    R["price vs SMA200 (L/flat)"] = (c > sma(c, 200)).astype(float)
    R["price vs SMA200 (L/S)"] = np.where(c > sma(c, 200), 1.0, -1.0)
    R["ROC(20) sign (L/S)"] = np.sign(c / c.shift(20) - 1)
    R["ROC(120) sign (L/S)"] = np.sign(c / c.shift(120) - 1)
    macd = ema(c, 12) - ema(c, 26); sigl = ema(macd, 9)
    R["MACD > signal (L/S)"] = np.sign(macd - sigl)
    rs = rsi(c, 14)
    R["RSI14 momentum (>50 L, <50 S)"] = np.where(rs > 50, 1.0, -1.0)
    rev = pd.Series(np.nan, index=d.index)
    rev[rs < 30] = 1.0; rev[rs > 50] = 0.0
    R["RSI14 oversold-reversion (L/flat)"] = rev.ffill().fillna(0.0)
    rs2 = rsi(c, 2)
    r2 = pd.Series(np.nan, index=d.index)
    r2[(rs2 < 10) & (c > sma(c, 200))] = 1.0
    r2[c > sma(c, 5)] = 0.0
    R["Connors RSI2 (<10 & >SMA200; exit >SMA5)"] = r2.ffill().fillna(0.0)
    ma20 = sma(c, 20); sd20 = c.rolling(20).std()
    bb_rev = pd.Series(np.nan, index=d.index)
    bb_rev[c < ma20 - 2 * sd20] = 1.0; bb_rev[c > ma20] = 0.0
    R["Bollinger(20,2) reversion (L/flat)"] = bb_rev.ffill().fillna(0.0)
    bb_bo = pd.Series(np.nan, index=d.index)
    bb_bo[c > ma20 + 2 * sd20] = 1.0; bb_bo[c < ma20 - 2 * sd20] = -1.0
    R["Bollinger(20,2) breakout (L/S)"] = bb_bo.ffill().fillna(0.0)
    hh20 = d.high.rolling(20).max().shift(1); ll10 = d.low.rolling(10).min().shift(1)
    don = pd.Series(np.nan, index=d.index)
    don[c > hh20] = 1.0; don[c < ll10] = 0.0
    R["Donchian 20/10 (L/flat)"] = don.ffill().fillna(0.0)
    hh55 = d.high.rolling(55).max().shift(1); ll55 = d.low.rolling(55).min().shift(1)
    don2 = pd.Series(np.nan, index=d.index)
    don2[c > hh55] = 1.0; don2[c < ll55] = -1.0
    R["Donchian 55 (Turtle, L/S)"] = don2.ffill().fillna(0.0)
    st = stoch(d, 14, 3)
    R["Stochastic(14,3) >50 (L/S)"] = np.where(st > 50, 1.0, -1.0)
    ad, pdi, mdi = adx(d, 14)
    R["ADX>25 & +DI>-DI trend (L/S/flat)"] = np.where(ad > 25, np.sign(pdi - mdi), 0.0)
    cc = cci(d, 20)
    R["CCI(20) sign (L/S)"] = np.sign(cc)
    kc_mid = ema(c, 20); kc_r = atr(d, 20) * 1.5
    kc = pd.Series(np.nan, index=d.index)
    kc[c > kc_mid + kc_r] = 1.0; kc[c < kc_mid - kc_r] = -1.0
    R["Keltner(20,1.5) breakout (L/S)"] = kc.ffill().fillna(0.0)
    hi26 = d.high.rolling(26).max(); lo26 = d.low.rolling(26).min()
    hi9 = d.high.rolling(9).max(); lo9 = d.low.rolling(9).min()
    span_a = ((hi9 + lo9) / 2 + (hi26 + lo26) / 2) / 2
    R["Ichimoku price>span_a (L/S)"] = np.where(c > span_a, 1.0, -1.0)
    return {k: pd.Series(v, index=d.index).astype(float) for k, v in R.items()}


def score(pos, ret, n_shuffle=2000, seed=0):
    pos = pos.shift(1).fillna(0.0)
    turn = pos.diff().abs().fillna(pos.abs())
    net = pos * ret - turn * COST_BP - pos.abs() * (CARRY_ANN / TD)
    net = net.dropna()
    if len(net) < 60 or net.std() == 0:
        return None
    eq = (1 + net).cumprod()
    sh = net.mean() / net.std() * np.sqrt(TD)
    cagr = eq.iloc[-1] ** (TD / len(net)) - 1
    mdd = float(-(eq / eq.cummax() - 1).min())
    expo = float((pos != 0).mean())
    # random-sign null: shuffle the sign of pos each day, keep |pos|
    rng = np.random.default_rng(seed)
    mag = pos.abs().to_numpy(); r = ret.reindex(pos.index).fillna(0).to_numpy()
    tc = turn.to_numpy(); ca = CARRY_ANN / TD
    sh_null = np.empty(n_shuffle)
    for i in range(n_shuffle):
        sgn = rng.choice([-1.0, 1.0], size=len(mag))
        p = sgn * mag
        nn = p * r - np.abs(np.diff(p, prepend=0.0)) * COST_BP - np.abs(p) * ca
        sh_null[i] = nn.mean() / nn.std() * np.sqrt(TD) if nn.std() > 0 else 0.0
    p_emp = float((sh_null >= sh).mean())
    return dict(sharpe=sh, cagr=cagr, maxdd=mdd, expo=expo, p_null=p_emp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="in_sample")
    ap.add_argument("--start"); ap.add_argument("--end")
    a = ap.parse_args()
    d = daily(a.split if not a.start else None, a.start, a.end)
    ret = np.log(d.close).diff()
    print(f"daily bars {d.index[0].date()}..{d.index[-1].date()}  n={len(d)}\n")

    bh = score(pd.Series(1.0, index=d.index), ret)
    print(f"{'buy & hold':44s} Sharpe {bh['sharpe']:+.2f}  CAGR {bh['cagr']:+.3f}  maxDD {bh['maxdd']:.2f}\n")

    rows = []
    for name, pos in rules(d).items():
        s = score(pos, ret)
        if s is None:
            continue
        rows.append((name, s))
    rows.sort(key=lambda t: -t[1]["sharpe"])
    print(f"{'rule (default params)':44s} {'Sharpe':>7} {'CAGR':>7} {'maxDD':>6} {'expo':>5} {'p_null':>7} {'>BH?':>5}")
    for name, s in rows:
        print(f"{name:44s} {s['sharpe']:+7.2f} {s['cagr']:+7.3f} {s['maxdd']:6.2f} "
              f"{s['expo']:5.2f} {s['p_null']:7.3f} {'yes' if s['sharpe'] > bh['sharpe'] else '  -':>5}")
    N = len(rows)
    print(f"\nmultiple testing: {N} rules tested. Expected false positives at p<0.05: ~{N*0.05:.1f}.")
    print(f"Bonferroni p threshold for one real hit: {0.05/N:.4f}.")
    sig = [n for n, s in rows if s["p_null"] < 0.05 / N and s["sharpe"] > bh["sharpe"]]
    print("Rules beating BH AND surviving Bonferroni vs the null:", sig or "NONE")


if __name__ == "__main__":
    main()
