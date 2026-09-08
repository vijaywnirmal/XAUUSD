"""
H1 NY opening-range breakout - MT5 execution bot.

    python -m livebot                 # paper mode (default) - attaches to MT5 read-only
    LIVEBOT_MODE=replay python -m livebot        # backtest the state machine on PG bars
    LIVEBOT_MODE=live LIVEBOT_CONFIRM_LIVE=yes python -m livebot   # real orders (you set both)

Reads config from livebot/config.py. No account password anywhere - it attaches
to the already-running, already-logged-in MetaTrader 5 desktop terminal.
"""
from livebot import config
from livebot.runner import Runner


def main():
    print(f"livebot H1  |  MODE={config.MODE}  symbol={config.SYMBOL}  lots={config.LOTS}  "
          f"magic={config.MAGIC}")
    if config.MODE == "live":
        print("  !! LIVE MODE - real orders" if config.CONFIRM_LIVE else
              "  live mode but LIVEBOT_CONFIRM_LIVE!=yes -> sends are blocked, run is a no-op")
    Runner().run()


if __name__ == "__main__":
    main()
