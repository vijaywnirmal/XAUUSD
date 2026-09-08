"""
Historical high-impact US event schedule (FOMC / NFP / CPI), 2009-2027, and the
per-timestamp event-proximity features that get fed to BOTH the direction model
and the volatility model.

ForexFactory only serves the current week, so for training we generate the
schedule from known rules:
  FOMC  - the 8 scheduled decision days per year (hardcoded, exact).
  NFP   - first Friday of the month, 08:30 US Eastern (12:30 UTC EDT / 13:30 EST).
  CPI   - ~13th of the month, same 08:30 ET release slot (date approximate; the
          minute-level blackout still lands in the right hour).
Weight: FOMC 3, NFP 2, CPI 1.
"""
from __future__ import annotations

import functools
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

FOMC_DATES = [
 "2009-01-28","2009-03-18","2009-04-29","2009-06-24","2009-08-12","2009-09-23","2009-11-04","2009-12-16",
 "2010-01-27","2010-03-16","2010-04-28","2010-06-23","2010-08-10","2010-09-21","2010-11-03","2010-12-14",
 "2011-01-26","2011-03-15","2011-04-27","2011-06-22","2011-08-09","2011-09-21","2011-11-02","2011-12-13",
 "2012-01-25","2012-03-13","2012-04-25","2012-06-20","2012-08-01","2012-09-13","2012-10-24","2012-12-12",
 "2013-01-30","2013-03-20","2013-05-01","2013-06-19","2013-07-31","2013-09-18","2013-10-30","2013-12-18",
 "2014-01-29","2014-03-19","2014-04-30","2014-06-18","2014-07-30","2014-09-17","2014-10-29","2014-12-17",
 "2015-01-28","2015-03-18","2015-04-29","2015-06-17","2015-07-29","2015-09-17","2015-10-28","2015-12-16",
 "2016-01-27","2016-03-16","2016-04-27","2016-06-15","2016-07-27","2016-09-21","2016-11-02","2016-12-14",
 "2017-02-01","2017-03-15","2017-05-03","2017-06-14","2017-07-26","2017-09-20","2017-11-01","2017-12-13",
 "2018-01-31","2018-03-21","2018-05-02","2018-06-13","2018-08-01","2018-09-26","2018-11-08","2018-12-19",
 "2019-01-30","2019-03-20","2019-05-01","2019-06-19","2019-07-31","2019-09-18","2019-10-30","2019-12-11",
 "2020-01-29","2020-03-15","2020-04-29","2020-06-10","2020-07-29","2020-09-16","2020-11-05","2020-12-16",
 "2021-01-27","2021-03-17","2021-04-28","2021-06-16","2021-07-28","2021-09-22","2021-11-03","2021-12-15",
 "2022-01-26","2022-03-16","2022-05-04","2022-06-15","2022-07-27","2022-09-21","2022-11-02","2022-12-14",
 "2023-02-01","2023-03-22","2023-05-03","2023-06-14","2023-07-26","2023-09-20","2023-11-01","2023-12-13",
 "2024-01-31","2024-03-20","2024-05-01","2024-06-12","2024-07-31","2024-09-18","2024-11-07","2024-12-18",
 "2025-01-29","2025-03-19","2025-05-07","2025-06-18","2025-07-30","2025-09-17","2025-11-05","2025-12-17",
 "2026-01-28","2026-03-18","2026-04-29","2026-06-17","2026-07-29","2026-09-16","2026-11-04","2026-12-16",
]


def _us_dst(d: pd.Timestamp) -> bool:
    y = d.year
    mar = pd.Timestamp(y, 3, 1)
    start = mar + pd.Timedelta(days=(6 - mar.weekday()) % 7 + 7)     # 2nd Sun Mar
    nov = pd.Timestamp(y, 11, 1)
    end = nov + pd.Timedelta(days=(6 - nov.weekday()) % 7)          # 1st Sun Nov
    return start <= d.tz_localize(None).normalize() < end if d.tzinfo else start <= d.normalize() < end


def _release_utc(day: pd.Timestamp) -> pd.Timestamp:
    """08:30 US Eastern on `day` -> UTC."""
    hour = 12 if _us_dst(day) else 13
    return pd.Timestamp(day.year, day.month, day.day, hour, 30, tz="UTC")


@functools.lru_cache(maxsize=1)
def schedule() -> pd.DataFrame:
    rows = []
    for s in FOMC_DATES:
        d = pd.Timestamp(s)
        rows.append((_release_utc(d).replace(hour=18, minute=0), "FOMC", 3))   # ~14:00 ET decision
    for m in pd.date_range("2009-01-01", "2027-12-01", freq="MS"):
        first = m
        while first.weekday() != 4:
            first += pd.Timedelta(days=1)
        rows.append((_release_utc(first), "NFP", 2))
        rows.append((_release_utc(m + pd.Timedelta(days=12)), "CPI", 1))        # ~13th
    df = pd.DataFrame(rows, columns=["when", "kind", "weight"]).sort_values("when").reset_index(drop=True)
    # store as tz-naive UTC numpy datetime64[ns] for unit-safe arithmetic
    df["when_ns"] = df["when"].dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ns]")
    return df


_KIND_ORD = {"": 0, "CPI": 1, "NFP": 2, "FOMC": 3}


def event_features_frame(ts: pd.DatetimeIndex) -> pd.DataFrame:
    """Vectorised: for each ts, minutes to/from the nearest high-impact event,
    the next event's weight, and window flags. Times capped at 1 day."""
    sch = schedule()
    ev = sch["when_ns"].to_numpy().astype("datetime64[ns]")
    w = sch["weight"].to_numpy()
    tt = ts.tz_convert("UTC").tz_localize(None) if ts.tz is not None else ts
    t = tt.values.astype("datetime64[ns]")
    minute = np.timedelta64(60, "s")
    nxt = np.searchsorted(ev, t, side="left")
    prv = nxt - 1
    BIG = 1e6
    to_next = np.where(nxt < len(ev),
                       (ev[np.clip(nxt, 0, len(ev) - 1)] - t) / minute, BIG).astype(float)
    from_prev = np.where(prv >= 0,
                         (t - ev[np.clip(prv, 0, len(ev) - 1)]) / minute, BIG).astype(float)
    next_w = np.where(nxt < len(ev), w[np.clip(nxt, 0, len(ev) - 1)], 0)
    to_next_c = np.minimum(to_next, 1440.0)
    from_prev_c = np.minimum(from_prev, 1440.0)
    return pd.DataFrame({
        "ev_mins_to": to_next_c,
        "ev_mins_from": from_prev_c,
        "ev_next_weight": next_w,
        "ev_pre2h": ((to_next > 0) & (to_next <= 120)).astype(float),
        "ev_post2h": (from_prev <= 120).astype(float),
        "ev_window60": ((to_next <= 60) | (from_prev <= 60)).astype(float),
        "ev_imminent": ((to_next > 0) & (to_next <= 30)).astype(float),
    }, index=ts)


def live_event_summary(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    sch = schedule()
    fut = sch[sch["when"] >= pd.Timestamp(now)]
    nxt = fut.iloc[0] if len(fut) else None
    row = event_features_frame(pd.DatetimeIndex([pd.Timestamp(now)])).iloc[0].to_dict()
    row["next_kind"] = None if nxt is None else nxt["kind"]
    row["next_when_utc"] = None if nxt is None else nxt["when"].isoformat()
    return row
