"""
Indicator library for chart overlays and the strategy builder.
Formulas reused from research/indicator_screen.py where present; Bollinger,
MACD and Donchian added (standard formulas, not present there).
"""
import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int = 20) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int = 20) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([high - low, (high - close.shift()).abs(),
                    (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(df: pd.DataFrame, n: int = 14):
    high, low = df["high"], df["low"]
    up = high.diff()
    dn = -low.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(df, n)
    pdi = 100 * pd.Series(plus, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    mdi = 100 * pd.Series(minus, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, mdi


def stoch(df: pd.DataFrame, n: int = 14, k: int = 3) -> pd.Series:
    ll = df["low"].rolling(n).min()
    hh = df["high"].rolling(n).max()
    kf = 100 * (df["close"] - ll) / (hh - ll).replace(0, np.nan)
    return kf.rolling(k).mean()


def cci(df: pd.DataFrame, n: int = 20) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    return (tp - tp.rolling(n).mean()) / (
        0.015 * tp.rolling(n).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True))


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    mid = sma(close, n)
    sd = close.rolling(n).std()
    return mid + k * sd, mid, mid - k * sd


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def donchian(df: pd.DataFrame, n: int = 20):
    return df["high"].rolling(n).max(), df["low"].rolling(n).min()


def supertrend(df: pd.DataFrame, smooth_n: int = 20, atr_n: int = 30, mult: float = 3.0):
    """Supertrend built on SMOOTHED OHLC: each of high/low/close is first
    SMA-smoothed over `smooth_n` bars (reduces noise), then an ATR-like
    volatility band of width `mult` x (an `atr_n`-period true-range average
    of the smoothed series) is built around the smoothed hl2. Price above
    the active band = bullish regime, below = bearish — the band itself
    ratchets like a trailing stop and only moves in the trend's favor,
    exactly like the standard Supertrend indicator, just fed smoothed
    inputs instead of raw candles.
    Returns (line, direction): line = the active trailing-stop price level;
    direction = +1.0 (bullish) / -1.0 (bearish) / NaN during warm-up. A
    reversal (direction changing sign) is the standard Supertrend entry
    signal — compare "direction" cross_above/cross_below 0 in the builder."""
    sh = sma(df["high"], smooth_n)
    sl = sma(df["low"], smooth_n)
    sc = sma(df["close"], smooth_n)

    tr = pd.concat([sh - sl, (sh - sc.shift()).abs(), (sl - sc.shift()).abs()], axis=1).max(axis=1)
    vol = tr.ewm(alpha=1 / atr_n, adjust=False).mean()

    hl2 = (sh + sl) / 2
    basic_upper = (hl2 + mult * vol).to_numpy()
    basic_lower = (hl2 - mult * vol).to_numpy()
    close = sc.to_numpy()
    n = len(df)

    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)
    direction = np.full(n, np.nan)
    line = np.full(n, np.nan)

    for i in range(n):
        if np.isnan(basic_upper[i]) or np.isnan(basic_lower[i]) or np.isnan(close[i]):
            continue
        if np.isnan(final_upper[i - 1]) if i > 0 else True:
            final_upper[i] = basic_upper[i]
            final_lower[i] = basic_lower[i]
            direction[i] = 1.0 if close[i] > final_upper[i] else -1.0
            line[i] = final_lower[i] if direction[i] == 1 else final_upper[i]
            continue
        final_upper[i] = (basic_upper[i] if (basic_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1])
                          else final_upper[i - 1])
        final_lower[i] = (basic_lower[i] if (basic_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1])
                          else final_lower[i - 1])
        if close[i] > final_upper[i - 1]:
            direction[i] = 1.0
        elif close[i] < final_lower[i - 1]:
            direction[i] = -1.0
        else:
            direction[i] = direction[i - 1]
        line[i] = final_lower[i] if direction[i] == 1 else final_upper[i]

    return pd.Series(line, index=df.index), pd.Series(direction, index=df.index)


def yearly_range(df: pd.DataFrame):
    """Where the current close sits relative to the PREVIOUS calendar year's
    high/low range: range_pos=0 at last year's low, 1 at last year's high
    (can go outside 0-1 if price has since broken past that range). NaN for
    bars in the data's first calendar year (no previous year to compare)."""
    year = pd.DatetimeIndex(df["ts"]).year
    year_s = pd.Series(year, index=df.index)
    yearly_high = pd.Series(df["high"].to_numpy(), index=year).groupby(level=0).max()
    yearly_low = pd.Series(df["low"].to_numpy(), index=year).groupby(level=0).min()
    prev_high = year_s.map(lambda y: yearly_high.get(y - 1, np.nan))
    prev_low = year_s.map(lambda y: yearly_low.get(y - 1, np.nan))
    rng = (prev_high - prev_low).replace(0, np.nan)
    pos = (df["close"] - prev_low) / rng
    return pos, prev_high, prev_low


# ---- registry consumed by /indicators and the strategy builder ---------------
INDICATOR_REGISTRY = {
    "sma": {"name": "SMA", "params": [{"name": "n", "type": "int", "default": 20, "min": 2, "max": 500}],
            "outputs": ["sma"], "needs": "close"},
    "ema": {"name": "EMA", "params": [{"name": "n", "type": "int", "default": 20, "min": 2, "max": 500}],
            "outputs": ["ema"], "needs": "close"},
    "rsi": {"name": "RSI", "params": [{"name": "n", "type": "int", "default": 14, "min": 2, "max": 200}],
            "outputs": ["rsi"], "needs": "close"},
    "atr": {"name": "ATR", "params": [{"name": "n", "type": "int", "default": 14, "min": 2, "max": 200}],
            "outputs": ["atr"], "needs": "ohlc"},
    "adx": {"name": "ADX", "params": [{"name": "n", "type": "int", "default": 14, "min": 2, "max": 200}],
            "outputs": ["adx", "plus_di", "minus_di"], "needs": "ohlc"},
    "stoch": {"name": "Stochastic", "params": [{"name": "n", "type": "int", "default": 14, "min": 2, "max": 200},
                                                {"name": "k", "type": "int", "default": 3, "min": 1, "max": 20}],
              "outputs": ["stoch"], "needs": "ohlc"},
    "cci": {"name": "CCI", "params": [{"name": "n", "type": "int", "default": 20, "min": 2, "max": 200}],
            "outputs": ["cci"], "needs": "ohlc"},
    "bollinger": {"name": "Bollinger Bands",
                  "params": [{"name": "n", "type": "int", "default": 20, "min": 2, "max": 200},
                             {"name": "k", "type": "float", "default": 2.0, "min": 0.5, "max": 5.0}],
                  "outputs": ["bb_upper", "bb_mid", "bb_lower"], "needs": "close"},
    "macd": {"name": "MACD",
             "params": [{"name": "fast", "type": "int", "default": 12, "min": 2, "max": 100},
                        {"name": "slow", "type": "int", "default": 26, "min": 2, "max": 200},
                        {"name": "signal", "type": "int", "default": 9, "min": 2, "max": 100}],
             "outputs": ["macd_line", "macd_signal", "macd_hist"], "needs": "close"},
    "donchian": {"name": "Donchian Channel",
                 "params": [{"name": "n", "type": "int", "default": 20, "min": 2, "max": 500}],
                 "outputs": ["donchian_upper", "donchian_lower"], "needs": "ohlc"},
    "supertrend": {"name": "Supertrend (smoothed)",
                   "params": [{"name": "smooth_n", "type": "int", "default": 20, "min": 1, "max": 200},
                              {"name": "atr_n", "type": "int", "default": 30, "min": 2, "max": 300},
                              {"name": "mult", "type": "float", "default": 3.0, "min": 0.5, "max": 10.0}],
                   "outputs": ["line", "direction"], "needs": "ohlc"},
    "yearly_range": {"name": "Prior-Year Range Position",
                     "params": [],
                     "outputs": ["range_pos", "prev_year_high", "prev_year_low"], "needs": "ohlc"},
}


def compute_indicator(df: pd.DataFrame, indicator_id: str, params: dict) -> dict:
    """Returns {output_name: pd.Series} aligned to df.index."""
    p = params or {}
    if indicator_id == "sma":
        return {"sma": sma(df["close"], int(p.get("n", 20)))}
    if indicator_id == "ema":
        return {"ema": ema(df["close"], int(p.get("n", 20)))}
    if indicator_id == "rsi":
        return {"rsi": rsi(df["close"], int(p.get("n", 14)))}
    if indicator_id == "atr":
        return {"atr": atr(df, int(p.get("n", 14)))}
    if indicator_id == "adx":
        a, pdi, mdi = adx(df, int(p.get("n", 14)))
        return {"adx": a, "plus_di": pdi, "minus_di": mdi}
    if indicator_id == "stoch":
        return {"stoch": stoch(df, int(p.get("n", 14)), int(p.get("k", 3)))}
    if indicator_id == "cci":
        return {"cci": cci(df, int(p.get("n", 20)))}
    if indicator_id == "bollinger":
        u, m, l = bollinger(df["close"], int(p.get("n", 20)), float(p.get("k", 2.0)))
        return {"bb_upper": u, "bb_mid": m, "bb_lower": l}
    if indicator_id == "macd":
        line, sig, hist = macd(df["close"], int(p.get("fast", 12)), int(p.get("slow", 26)), int(p.get("signal", 9)))
        return {"macd_line": line, "macd_signal": sig, "macd_hist": hist}
    if indicator_id == "donchian":
        u, l = donchian(df, int(p.get("n", 20)))
        return {"donchian_upper": u, "donchian_lower": l}
    if indicator_id == "supertrend":
        line, direction = supertrend(df, int(p.get("smooth_n", 20)), int(p.get("atr_n", 30)), float(p.get("mult", 3.0)))
        return {"line": line, "direction": direction}
    if indicator_id == "yearly_range":
        pos, ph, pl = yearly_range(df)
        return {"range_pos": pos, "prev_year_high": ph, "prev_year_low": pl}
    raise ValueError(f"unknown indicator {indicator_id}")
