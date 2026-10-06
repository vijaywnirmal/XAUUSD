"""
Run the H1 paper bot on several instruments at once: one `python -m livebot` process per symbol, each
with its own logs (livebot/logs/ for XAUUSD, livebot/logs/<SYMBOL>/ for the rest). Every bot exits
once its day is done, and so does the fleet - schedule it shortly before the 13:30 UTC box.

    python -m livebot.fleet                                  # all instruments in config.INSTRUMENTS
    python -m livebot.fleet --symbols XAUUSD,EURUSD
    python -m livebot.fleet --on-trade "schtasks /Run /TN \\NiftyReels\\22 MT5 Replay"

Paper mode only (MODE is forced to paper): it reads quotes from the open MT5 terminal and sends nothing.
Exit codes: 0 all bots finished their day, 2 MT5 unavailable, 1 a bot failed.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

from livebot import config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def mt5_ready() -> str | None:
    """None if a logged-in terminal answers, else why not. initialize() starts the terminal if it's
    closed and it logs in with its own saved account - no credentials here."""
    import MetaTrader5 as mt5
    try:
        if not mt5.initialize():
            return f"MT5 didn't start: {mt5.last_error()}"
        term = mt5.terminal_info()
        if term is None or not term.connected:
            return "MT5 is open but not connected to the broker - log in"
        return None
    finally:
        mt5.shutdown()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols", default=",".join(config.INSTRUMENTS))
    ap.add_argument("--on-trade", default="", help="command to run after each closed trade")
    args = ap.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    unknown = [s for s in symbols if s not in config.INSTRUMENTS]
    if unknown:
        print(f"no settings for {', '.join(unknown)} in config.INSTRUMENTS", file=sys.stderr)
        return 1

    for attempt in range(3):  # a terminal that was just launched needs a moment to connect
        why = mt5_ready()
        if why is None:
            break
        time.sleep(20)
    if why:
        print(why, file=sys.stderr)
        return 2

    procs = {}
    for sym in symbols:
        env = {**os.environ, "LIVEBOT_SYMBOL": sym, "LIVEBOT_MODE": "paper", "LIVEBOT_EXIT_AFTER_DAY": "1",
               "LIVEBOT_ON_TRADE_CMD": args.on_trade, "PYTHONUNBUFFERED": "1"}
        env.pop("LIVEBOT_CONFIRM_LIVE", None)
        logs = config._LOGS if sym == "XAUUSD" else os.path.join(config._LOGS, sym)
        os.makedirs(logs, exist_ok=True)
        out = open(os.path.join(logs, "run.log"), "a", encoding="utf-8")
        procs[sym] = (subprocess.Popen([sys.executable, "-m", "livebot"], cwd=ROOT, env=env,
                                       stdout=out, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)), out)
        print(f"{sym:7} pid {procs[sym][0].pid}")

    code = 0
    for sym, (p, out) in procs.items():
        rc = p.wait()
        out.close()
        print(f"{sym:7} exited {rc}")
        code = max(code, 1 if rc else 0)
    return code


if __name__ == "__main__":
    sys.exit(main())
