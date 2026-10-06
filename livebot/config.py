"""
Configuration for the H1 (NY opening-range breakout) MT5 execution bot.

SAFETY: MODE defaults to "paper". No real order is ever sent to the broker
unless MODE == "live" AND the environment variable LIVEBOT_CONFIRM_LIVE == "yes"
(set both, deliberately, yourself). There is no account password anywhere in
this project — the bot attaches to an already-running, already-logged-in MT5
terminal via mt5.initialize().
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------- mode
#   "paper"  : attach to MT5 read-only, simulate fills from the live bid/ask.
#   "replay" : run the state machine over Postgres M5 bars, no MT5 at all.
#   "live"   : send real pending/market orders (also needs LIVEBOT_CONFIRM_LIVE=yes).
MODE = os.environ.get("LIVEBOT_MODE", "paper").lower()
CONFIRM_LIVE = os.environ.get("LIVEBOT_CONFIRM_LIVE", "").lower() == "yes"

SYMBOL = os.environ.get("LIVEBOT_SYMBOL", "XAUUSD").upper()
ORDER_COMMENT = "H1_ORB"

# ---------------------------------------------------------------- instruments
# The same H1 rules run on each instrument (one process per symbol - see fleet.py). Prices are in the
# instrument's own units: max_box / max_spread / slippage are $ for gold, price units for FX (0.0030 =
# 30 pips on EURUSD). Only XAUUSD's values come from the backtest; the FX guards are sane "this day is
# abnormal" caps, not tuned. quote_usd=False: P&L is in the quote currency and is converted to USD at the
# exit price (USDJPY -> JPY, USDCAD -> CAD).
INSTRUMENTS = {
    "XAUUSD": dict(contract=100.0, digits=2, pip=0.01, max_box=12.0, max_spread=0.60, slippage=0.02,
                   quote_usd=True, magic=910001),
    "EURUSD": dict(contract=100_000.0, digits=5, pip=0.0001, max_box=0.0030, max_spread=0.0002,
                   slippage=0.00002, quote_usd=True, magic=910002),
    "GBPUSD": dict(contract=100_000.0, digits=5, pip=0.0001, max_box=0.0040, max_spread=0.0003,
                   slippage=0.00002, quote_usd=True, magic=910003),
    "USDJPY": dict(contract=100_000.0, digits=3, pip=0.01, max_box=0.40, max_spread=0.03,
                   slippage=0.002, quote_usd=False, magic=910004),
    "AUDUSD": dict(contract=100_000.0, digits=5, pip=0.0001, max_box=0.0025, max_spread=0.0002,
                   slippage=0.00002, quote_usd=True, magic=910005),
    "USDCAD": dict(contract=100_000.0, digits=5, pip=0.0001, max_box=0.0030, max_spread=0.0003,
                   slippage=0.00002, quote_usd=False, magic=910006),
}
if SYMBOL not in INSTRUMENTS:
    raise SystemExit(f"LIVEBOT_SYMBOL={SYMBOL!r} has no settings in livebot/config.py INSTRUMENTS")
INSTRUMENT = INSTRUMENTS[SYMBOL]
CONTRACT = INSTRUMENT["contract"]      # units per 1.0 lot
DIGITS = INSTRUMENT["digits"]
PIP = INSTRUMENT["pip"]
QUOTE_USD = INSTRUMENT["quote_usd"]
MAGIC = INSTRUMENT["magic"]            # position/order tag — the bot only touches its own

# ---------------------------------------------------------------- H1 strategy
# These MUST match backtest/… H1: 13:30-14:00 UTC box, break 14:00-18:00,
# stop = opposite box extreme, flat 20:00 UTC, one trade per day.
BOX_START_UTC = "13:30"
BOX_END_UTC = "14:00"
BREAK_END_UTC = "18:00"               # no new entry at/after this
FLAT_UTC = "20:00"                    # force any open position flat at/after this
LOTS = 0.01
# Skip the day if the box is wider than this (backtest note: edge is thin on
# wide-box days). None disables the check.
MAX_BOX_WIDTH_USD = INSTRUMENT["max_box"]     # price units (the name predates FX)
# Spread guard. Blocks the FIRST arming of the day while the quote is wider than
# this, and pulls a working OCO if the spread spikes past it (news event). It is
# NOT a per-tick flap gate — set it to "something is clearly wrong" (~p99 of
# normal, ≈$0.60), not to the ~$0.34 typical. The backtest already charges the
# real spread; this only protects against pathological quotes.
MAX_SPREAD_USD = INSTRUMENT["max_spread"]     # price units

# ---------------------------------------------------------------- risk guards
MAX_TRADES_PER_DAY = 1
MAX_DAILY_LOSS_USD = 25.0             # halt new entries once realised P&L today <= -this
MAX_OPEN_POSITIONS = 1
# A file named STOP in the livebot/ dir halts all new entries (existing
# positions are still managed to flat). Delete it to resume.
KILL_SWITCH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "STOP")

# ---------------------------------------------------------------- execution
POLL_SECONDS = 2.0
PENDING_EXPIRY_MINUTES = 0            # 0 = GTC + we cancel at BREAK_END_UTC ourselves
ORDER_DEVIATION_POINTS = 20           # slippage tolerance for market (flat) orders
ORDER_RETRIES = 2

# ---------------------------------------------------------------- paper sim
PAPER_START_BALANCE = 1000.0
PAPER_COMMISSION_PER_LOT_RT = 6.0     # Vantage Raw ECN: $3/side => $6 round-turn/lot
PAPER_SLIPPAGE_USD = INSTRUMENT["slippage"]  # per side, price units, added to the fill

# ---------------------------------------------------------------- replay
REPLAY_TF = "5min"
REPLAY_START = os.environ.get("LIVEBOT_REPLAY_START", "2024-01-01")
REPLAY_END = os.environ.get("LIVEBOT_REPLAY_END", "2024-04-01")

_LOGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_DIR = _LOGS if SYMBOL == "XAUUSD" else os.path.join(_LOGS, SYMBOL)  # gold keeps the original location

# ---------------------------------------------------------------- unattended runs (fleet.py sets these)
# Exit once the day is finished (skipped, or traded and flat) instead of polling until killed.
EXIT_AFTER_DAY = os.environ.get("LIVEBOT_EXIT_AFTER_DAY", "") == "1"
# Run after each closed trade (e.g. start the video job); the trade's replay file is written first.
ON_TRADE_CMD = os.environ.get("LIVEBOT_ON_TRADE_CMD", "")
# Minutes of M1 history before the box saved with each trade's replay
REPLAY_LEAD_MIN = 15
