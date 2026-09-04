"""
Fetch Dukascopy DAILY OHLC for the H6 trend basket -> basket/<name>.parquet
(small, fast — daily bars, not ticks).

    python -m research.fetch_basket
"""
import os
import socket
import logging
from datetime import datetime, timezone

socket.setdefaulttimeout(45)
logging.disable(logging.INFO)

import pandas as pd
import dukascopy_python as dk
import dukascopy_python.instruments as I

from data_pipeline import config as C

OUT = os.path.join(C.ROOT, "basket")
START = datetime(2007, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 9, 4, tzinfo=timezone.utc)

BASKET = {
    "XAUUSD": I.INSTRUMENT_FX_METALS_XAU_USD,
    "XAGUSD": I.INSTRUMENT_FX_METALS_XAG_USD,
    "COPPER": I.INSTRUMENT_CMD_METALS_COPPER_CMD_USD,
    "EURUSD": I.INSTRUMENT_FX_MAJORS_EUR_USD,
    "GBPUSD": I.INSTRUMENT_FX_MAJORS_GBP_USD,
    "USDJPY": I.INSTRUMENT_FX_MAJORS_USD_JPY,
    "AUDUSD": I.INSTRUMENT_FX_MAJORS_AUD_USD,
    "SPX500": I.INSTRUMENT_IDX_AMERICA_E_SANDP_500,
    "NAS100": I.INSTRUMENT_IDX_AMERICA_E_NQ_100,
    "DAX40": I.INSTRUMENT_IDX_EUROPE_E_DAAX,
    "NIKKEI": I.INSTRUMENT_IDX_ASIA_E_N225JAP,
    "WTI": I.INSTRUMENT_CMD_ENERGY_E_LIGHT,
    "BRENT": I.INSTRUMENT_CMD_ENERGY_E_BRENT,
    "NATGAS": I.INSTRUMENT_CMD_ENERGY_GAS_CMD_USD,
}

CLASS = {
    "XAUUSD": "metal", "XAGUSD": "metal", "COPPER": "metal",
    "EURUSD": "fx", "GBPUSD": "fx", "USDJPY": "fx", "AUDUSD": "fx",
    "SPX500": "index", "NAS100": "index", "DAX40": "index", "NIKKEI": "index",
    "WTI": "energy", "BRENT": "energy", "NATGAS": "energy",
}


def fetch_one(name, instr):
    for attempt in range(4):
        try:
            df = dk.fetch(instr, dk.INTERVAL_DAY_1, dk.OFFER_SIDE_BID, START, END)
            if df is not None and len(df):
                d = df.rename(columns=str.lower)[["open", "high", "low", "close"]].copy()
                d.index = pd.to_datetime(d.index, utc=True).tz_convert("UTC").normalize()
                d = d[~d.index.duplicated(keep="last")].sort_index()
                d = d[(d["close"] > 0) & d["close"].notna()]
                return d
        except Exception as exc:
            print(f"  {name}: attempt {attempt+1} failed: {exc}")
    return None


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for name, instr in BASKET.items():
        d = fetch_one(name, instr)
        if d is None or len(d) < 500:
            print(f"{name:8s} FAILED / too short ({0 if d is None else len(d)})")
            continue
        d.to_parquet(os.path.join(OUT, f"{name}.parquet"))
        rows.append((name, CLASS[name], len(d), d.index[0].date(), d.index[-1].date()))
        print(f"{name:8s} {CLASS[name]:6s} {len(d):5d} bars  {d.index[0].date()} .. {d.index[-1].date()}")
    meta = pd.DataFrame(rows, columns=["name", "class", "bars", "start", "end"])
    meta.to_csv(os.path.join(OUT, "_meta.csv"), index=False)
    print(f"\nwrote {len(rows)}/{len(BASKET)} instruments -> {OUT}")


if __name__ == "__main__":
    main()
