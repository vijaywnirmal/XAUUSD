"""
Real-time XAUUSD monitor: features + patterns + a direction lean + news.

    python -m monitor                     # live, MT5 terminal (read-only)
    python -m monitor --source pg --start 2024-03-01 --end 2024-04-01   # offline replay

Writes monitor/logs/snapshot.json (live) and monitor/logs/history.csv.
Run `python -m monitor.calibrate` first to build the direction model.
"""
import argparse

from monitor.engine import Mt5Source, PgSource, run


def main():
    ap = argparse.ArgumentParser(prog="monitor")
    ap.add_argument("--source", choices=["mt5", "pg"], default="mt5")
    ap.add_argument("--start", default="2024-03-01")
    ap.add_argument("--end", default="2024-04-01")
    a = ap.parse_args()
    src = PgSource(a.start, a.end) if a.source == "pg" else Mt5Source()
    run(src)


if __name__ == "__main__":
    main()
