"""
Config for the real-time market monitor.

News APIs used (all free):
  - ForexFactory weekly calendar  https://nfs.faireconomy.media/ff_calendar_thisweek.json
    no key. High/Medium/Low impact scheduled events -> event-proximity + blackout.
  - GDELT DOC 2.0 timelinetone    https://api.gdeltproject.org/api/v2/doc/doc
    no key, throttle >=5s. Rolling news tone + volume for "gold price".
  - Finnhub (optional)            set FINNHUB_API_KEY for /news + /news-sentiment.
  - Alpha Vantage (optional)      set ALPHAVANTAGE_API_KEY for NEWS_SENTIMENT.
"""
from __future__ import annotations

import os

SYMBOL = os.environ.get("MONITOR_SYMBOL", "XAUUSD")
TF = "5min"                       # base bar timeframe

POLL_SECONDS = 5.0               # market-feature loop
NEWS_REFRESH_SECONDS = 900       # calendar + GDELT refresh (respect GDELT throttle)

# feature windows (in M5 bars unless noted)
EMA_FAST, EMA_SLOW, EMA_TREND = 20, 50, 200
ATR_N = 14
RSI_N = 14
VOL_LOOKBACK_DAYS = 60           # ATR percentile regime
RANGE_LOOKBACK_BARS = 288        # 24h of M5 for range-position

# --- news / calendar ---
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_QUERY = "gold price"        # keep it simple - GDELT throttles complex queries harder
# currencies whose High-impact events move gold most
BLACKOUT_CURRENCIES = ("USD",)
BLACKOUT_IMPACTS = ("High",)
BLACKOUT_BEFORE_MIN = 15
BLACKOUT_AFTER_MIN = 15
# also treat these titles as always-blackout regardless of the feed's impact tag
ALWAYS_HIGH = ("FOMC", "Federal Funds Rate", "Non-Farm", "CPI m/m", "Core CPI", "PCE", "GDP")

FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")

# --- direction model ---
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.json")
PREDICT_HORIZON_BARS = 12        # predict sign of the next 12 M5 bars (~1h) return

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
SNAPSHOT = os.path.join(LOG_DIR, "snapshot.json")
HISTORY_CSV = os.path.join(LOG_DIR, "history.csv")
