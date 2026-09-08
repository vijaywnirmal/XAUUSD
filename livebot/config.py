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

SYMBOL = os.environ.get("LIVEBOT_SYMBOL", "XAUUSD")
MAGIC = 910001                         # position/order tag — the bot only touches its own
ORDER_COMMENT = "H1_ORB"

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
MAX_BOX_WIDTH_USD = 12.0
# Spread guard. Blocks the FIRST arming of the day while the quote is wider than
# this, and pulls a working OCO if the spread spikes past it (news event). It is
# NOT a per-tick flap gate — set it to "something is clearly wrong" (~p99 of
# normal, ≈$0.60), not to the ~$0.34 typical. The backtest already charges the
# real spread; this only protects against pathological quotes.
MAX_SPREAD_USD = 0.60

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
PAPER_SLIPPAGE_USD = 0.02            # per side, added to the fill

# ---------------------------------------------------------------- replay
REPLAY_TF = "5min"
REPLAY_START = os.environ.get("LIVEBOT_REPLAY_START", "2024-01-01")
REPLAY_END = os.environ.get("LIVEBOT_REPLAY_END", "2024-04-01")

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
