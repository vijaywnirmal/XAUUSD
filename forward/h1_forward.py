"""
H1 NY opening-range breakout - forward-test harness (0.01 lot).

This does NOT place orders. It (1) tells you exactly what order ticket to enter
on your broker, (2) logs what actually filled, (3) compares your realised fills
and costs to the backtest so you can see whether your live edge is real.

Backtest reference (in-sample 2009-2022, Dukascopy tick spreads, $6/lot RT):
    gross +$0.388 / trade   |   ~254 trades / yr   |   breakeven spread ~ $0.30
    net at spread $0.34 = -$0.03/trade ;  at $0.20 = +$0.11/trade (PF 1.04)

H1 spec (identical to backtest/…):
    box      = 13:30-14:00 UTC 5-min bars -> box_high / box_low
    entry    = OCO stop orders: BUY-STOP @ box_high , SELL-STOP @ box_low
               first one to trade wins; cancel the other
    stop     = the opposite box extreme (long -> box_low, short -> box_high)
    no entry after 18:00 UTC ; force flat at 20:00 UTC ; one trade / day
    size     = 0.01 lot (1 oz)   commission $0.06 round-trip

USAGE
    # just after 14:00 UTC, read the 13:30-14:00 box high/low off your chart:
    python -m forward.h1_forward plan --high 2648.90 --low 2644.10

    # after the trade closes (or the day ends with no fill):
    python -m forward.h1_forward log

    # any time:
    python -m forward.h1_forward report
"""
import argparse
import csv
import os
from datetime import datetime, timezone

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "h1_forward_log.csv")
LOT = 0.01
CONTRACT = 100.0                 # oz per 1.0 lot
COMMISSION_RT = 6.0 * LOT        # $0.06 round-trip on 0.01 lot
BACKTEST_GROSS = 0.388
BREAKEVEN_SPREAD = 0.30

FIELDS = ["date", "box_high", "box_low", "box_height", "filled", "side",
          "entry_time_utc", "entry_px", "entry_spread", "stop_px",
          "exit_time_utc", "exit_px", "exit_reason",
          "gross_pnl", "cost", "net_pnl", "slippage_vs_box", "notes"]


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ plan
def cmd_plan(a):
    hi, lo = a.high, a.low
    if hi <= lo:
        raise SystemExit("box high must be > box low")
    h = hi - lo
    print(f"""
  H1 order ticket - {datetime.now(timezone.utc):%Y-%m-%d} (box 13:30-14:00 UTC)
  ------------------------------------------------------------------
  box high  {hi:.2f}      box low   {lo:.2f}      height  {h:.2f}  (${h:.2f}/oz risk)

  Place BOTH as working stop orders (OCO - cancel the other on fill):
     BUY  STOP  @ {hi:.2f}   ->  if filled, STOP-LOSS @ {lo:.2f}
     SELL STOP  @ {lo:.2f}   ->  if filled, STOP-LOSS @ {hi:.2f}
  Size: {LOT} lot.   No new entry after 18:00 UTC.   Force FLAT at 20:00 UTC.

  Risk check: stop distance ${h:.2f}/oz  x {LOT} lot x {CONTRACT:g} oz = ${h*LOT*CONTRACT:.2f} max loss.
  If height > ~$12 the backtest edge is thin here - consider skipping the day.
  ------------------------------------------------------------------
  After it resolves:  python -m forward.h1_forward log
""")


# ------------------------------------------------------------------ log
def _ask(prompt, cast=str, default=None):
    raw = input(f"  {prompt}{' ['+str(default)+']' if default is not None else ''}: ").strip()
    if raw == "" and default is not None:
        return default
    if raw == "":
        return None
    try:
        return cast(raw)
    except ValueError:
        print("  ! could not parse, leaving blank")
        return None


def cmd_log(a):
    print("\n  Log a forward-test day (blank = skip field)\n")
    row = {k: "" for k in FIELDS}
    row["date"] = _ask("date (YYYY-MM-DD)", str, datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    row["box_high"] = _ask("box high", _f)
    row["box_low"] = _ask("box low", _f)
    if row["box_high"] and row["box_low"]:
        row["box_height"] = round(row["box_high"] - row["box_low"], 4)

    filled = _ask("did a side fill? (y/n)", str, "n").lower().startswith("y")
    row["filled"] = "y" if filled else "n"

    if filled:
        row["side"] = _ask("side (long/short)", str)
        row["entry_time_utc"] = _ask("entry time UTC (HH:MM)", str)
        row["entry_px"] = _ask("entry fill price", _f)
        row["entry_spread"] = _ask("spread at entry ($/oz, bid-ask)", _f)
        row["exit_px"] = _ask("exit price", _f)
        row["exit_time_utc"] = _ask("exit time UTC (HH:MM)", str)
        row["exit_reason"] = _ask("exit reason (stop/flat/manual)", str, "flat")

        side = 1 if str(row["side"]).lower().startswith("l") else -1
        row["stop_px"] = row["box_low"] if side > 0 else row["box_high"]
        ep, xp, sp = row["entry_px"], row["exit_px"], row["entry_spread"] or 0.0
        if ep and xp:
            gross = side * (xp - ep) * LOT * CONTRACT
            cost = COMMISSION_RT + sp * LOT * CONTRACT       # full spread charged once (entry+exit ≈ same)
            row["gross_pnl"] = round(gross, 4)
            row["cost"] = round(cost, 4)
            row["net_pnl"] = round(gross - cost, 4)
        box_lvl = row["box_high"] if side > 0 else row["box_low"]
        if ep and box_lvl is not None:
            # positive = filled worse than the box level (adverse slippage)
            row["slippage_vs_box"] = round(side * (ep - box_lvl), 4)
    row["notes"] = _ask("notes", str, "")

    new = not os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"\n  logged -> {LOG}\n")


# ------------------------------------------------------------------ report
def cmd_report(a):
    if not os.path.exists(LOG):
        raise SystemExit(f"no log yet at {LOG} - run `log` first")
    rows = list(csv.DictReader(open(LOG)))
    if not rows:
        raise SystemExit("log is empty")
    days = len(rows)
    fills = [r for r in rows if r["filled"] == "y" and _f(r["net_pnl"]) is not None]
    n = len(fills)
    print(f"\n  H1 forward test - {days} day(s) logged, {n} trade(s), {days-n} no-fill/skip\n")
    if n == 0:
        return
    net = [_f(r["net_pnl"]) for r in fills]
    gross = [_f(r["gross_pnl"]) for r in fills]
    spr = [_f(r["entry_spread"]) for r in fills if _f(r["entry_spread"]) is not None]
    slp = [_f(r["slippage_vs_box"]) for r in fills if _f(r["slippage_vs_box"]) is not None]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x <= 0]
    pf = (sum(wins) / -sum(losses)) if losses and sum(losses) != 0 else float("inf")
    avg = lambda v: sum(v) / len(v) if v else float("nan")

    print(f"    realised  gross ${avg(gross):+.3f}/trade   net ${avg(net):+.3f}/trade   "
          f"PF {pf:.2f}   hit {len(wins)/n:.0%}   cum net ${sum(net):+.2f}")
    print(f"    backtest  gross ${BACKTEST_GROSS:+.3f}/trade   (in-sample 2009-2022)")
    print()
    if spr:
        print(f"    avg entry spread     ${avg(spr):.3f}/oz")
    if slp:
        print(f"    avg slippage vs box  ${avg(slp):+.3f}/oz   (+ = filled worse than the box level)")
    eff = COMMISSION_RT / (LOT * CONTRACT) + avg(spr or [0]) + max(avg(slp or [0]), 0)
    print(f"    -> effective round-trip cost  ~${eff:.3f}/oz  (commission {COMMISSION_RT/(LOT*CONTRACT):.2f} "
          f"+ spread {avg(spr or [0]):.2f} + adverse slip {max(avg(slp or [0]),0):.2f})")
    print(f"       backtest breakeven spread ~${BREAKEVEN_SPREAD:.2f}; "
          f"you are {'BELOW (edge intact)' if eff < BREAKEVEN_SPREAD else 'ABOVE (edge eroded)'}.")
    print()
    print("    caveat: needs ~60-100 trades before realised expectancy is worth trusting;")
    print("    a handful of trades is dominated by variance, not by your edge.\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="h1_forward")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("--high", type=float, required=True); p.add_argument("--low", type=float, required=True)
    sub.add_parser("log")
    sub.add_parser("report")
    args = ap.parse_args()
    {"plan": cmd_plan, "log": cmd_log, "report": cmd_report}[args.cmd](args)
