"""
H14 - "just buy 0.01 lot every month, and separately add $100 cash every
month, never sell." A CFD accumulation simulation, not a signal test - no
entry/exit logic, just monthly buys held forever, per the operator's literal
spec (0.01-lot purchase and the $100 cash top-up are two separate things,
confirmed via clarification).

Mechanics:
  * On the first bar of each calendar month, buy 0.01 lot (mid price),
    paying real entry friction (half the spread + half the round-trip
    commission - there's no exit cost since the position is never closed).
  * Separately, $100 of new cash is added to the account that same month.
  * Positions are NEVER closed. Account equity at any date =
        (cumulative cash added) - (cumulative entry costs paid)
        + (unrealized mark-to-market P&L of every lot bought so far)
  * This is a CFD/leveraged accumulation (0.01 lot is a notional position,
    not a $-for-$ gold purchase) - the notional exposure this builds up is
    tracked explicitly and compared against the cash actually contributed,
    because that comparison is the interesting risk finding here.

For contrast, also computes the DIFFERENT thing this could have meant:
"$100/month buys $100 of gold" (classic unleveraged dollar-cost-averaging,
oz purchased = $100/price) - the operator declined this reading, but it's
cheap to show alongside as the natural benchmark.

    python -m research.h14_dca_accumulate
"""
import argparse
import numpy as np
import pandas as pd

from data_pipeline.dataset import load_bars

LOT_PER_MONTH = 0.01
CASH_PER_MONTH = 100.0     # overridden by --cash-per-month
CONTRACT_SIZE = 100.0
COMMISSION_ROUNDTRIP_PER_LOT = 6.0
TICK_SIZE = 0.01


def monthly_entries(df):
    df = df.sort_values("ts").reset_index(drop=True)
    df["ym"] = df["ts"].dt.to_period("M")
    first = df.groupby("ym").head(1).reset_index(drop=True)
    return first


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cash-per-month", type=float, default=CASH_PER_MONTH)
    ap.add_argument("--lot-per-month", type=float, default=LOT_PER_MONTH)
    args = ap.parse_args()
    cash_per_month = args.cash_per_month
    lot_per_month = args.lot_per_month

    df = load_bars("15min", allow_oos=True,
                   columns=["ts", "open", "high", "low", "close", "spread_mean"])
    months = monthly_entries(df)
    last_price = df["close"].iloc[-1]
    last_ts = df["ts"].iloc[-1]

    # --- literal spec: fixed lot/month (CFD), cash added separately ---
    cash_added = 0.0
    cost_paid = 0.0
    lots = 0.0
    basis_notional = 0.0     # sum of (lot*contract*entry_price) at each buy
    rows = []
    for _, r in months.iterrows():
        price = r["open"]
        entry_cost = (r["spread_mean"] / 2) * lot_per_month * CONTRACT_SIZE \
            + (COMMISSION_ROUNDTRIP_PER_LOT / 2) * lot_per_month
        cash_added += cash_per_month
        cost_paid += entry_cost
        lots += lot_per_month
        basis_notional += lot_per_month * CONTRACT_SIZE * price
        notional_now = lots * CONTRACT_SIZE * price
        unrl = notional_now - basis_notional
        equity = cash_added - cost_paid + unrl
        rows.append(dict(ts=r["ts"], price=price, lots=lots,
                         notional=notional_now, cash_added=cash_added,
                         equity=equity))
    eq = pd.DataFrame(rows)
    eq["dd"] = eq["equity"] - eq["equity"].cummax()

    final_notional = eq["lots"].iloc[-1] * CONTRACT_SIZE * last_price
    final_unrl = final_notional - basis_notional
    final_equity = eq["cash_added"].iloc[-1] - cost_paid + final_unrl
    n_months = len(months)

    print(f"=== H14  {lot_per_month:g} lot/month (never sold) + ${cash_per_month:g} cash/month, separate ===")
    print(f"  {n_months} months, {months['ts'].iloc[0].date()} -> {last_ts.date()}")
    print(f"  gold price: {months['open'].iloc[0]:.0f} -> {last_price:.0f}  "
          f"({(last_price/months['open'].iloc[0]-1)*100:+.0f}%)\n")
    print(f"  cash contributed:        ${eq['cash_added'].iloc[-1]:,.0f}")
    print(f"  entry costs paid:        ${cost_paid:,.0f}")
    print(f"  lots accumulated:        {eq['lots'].iloc[-1]:.2f}  "
          f"(= {eq['lots'].iloc[-1]*CONTRACT_SIZE:.0f} oz notional)")
    print(f"  notional exposure now:   ${final_notional:,.0f}")
    print(f"  unrealized P&L on gold:  ${final_unrl:+,.0f}")
    print(f"  FINAL ACCOUNT EQUITY:    ${final_equity:,.0f}")
    print(f"  return on cash contributed: {(final_equity/eq['cash_added'].iloc[-1]-1)*100:+.1f}%")
    print(f"  max drawdown (equity, mark-to-market): ${eq['dd'].min():,.0f}")
    print(f"  LEVERAGE at the end: notional / equity = {final_notional/final_equity:.1f}x  "
          f"(notional / cash contributed = {final_notional/eq['cash_added'].iloc[-1]:.1f}x)")
    print("\n  equity by year-end:")
    eq["year"] = eq["ts"].dt.year
    for y, g in eq.groupby("year"):
        last = g.iloc[-1]
        print(f"    {y}  equity=${last['equity']:9,.0f}  notional=${last['notional']:10,.0f}  "
              f"cash_in=${last['cash_added']:7,.0f}  lots={last['lots']:.2f}")

    # --- contrast: cash/month actually buys gold (unleveraged DCA) ---
    oz = 0.0
    cash_in2 = 0.0
    for _, r in months.iterrows():
        price = r["open"]
        oz += cash_per_month / price
        cash_in2 += cash_per_month
    final_value2 = oz * last_price
    print(f"\n  --- for contrast: if the ${cash_per_month:g}/month bought gold directly (unleveraged DCA) ---")
    print(f"  cash contributed: ${cash_in2:,.0f}   oz bought: {oz:.2f}   "
          f"final value: ${final_value2:,.0f}   return: {(final_value2/cash_in2-1)*100:+.1f}%")


if __name__ == "__main__":
    main()
