# livebot — H1 NY opening-range breakout, MT5 execution

Automated version of the **H1** strategy (13:30–14:00 UTC box → OCO stop-order
breakout → flat 20:00 UTC), running against a MetaTrader 5 terminal.

**It attaches to an already-open, already-logged-in MT5 desktop terminal via
`mt5.initialize()`. There is no account login or password anywhere in this
project.** Placing a real order also requires `LIVEBOT_CONFIRM_LIVE=yes` in the
environment — without it, every send is blocked and raises.

## Modes

| Mode | What it does | Needs MT5? |
|---|---|---|
| `paper` *(default)* | Attaches to MT5 read-only, simulates OCO fills / stops from the live bid/ask, logs everything. **Sends nothing.** | yes (read-only) |
| `replay` | Runs the state machine over Postgres M5 bars, prints a summary. Offline sanity check. | no |
| `live` | Sends real pending + market orders. Also needs `LIVEBOT_CONFIRM_LIVE=yes`. | yes |

```bash
python -m livebot                                          # paper
LIVEBOT_MODE=replay python -m livebot                      # offline state-machine test
LIVEBOT_MODE=live LIVEBOT_CONFIRM_LIVE=yes python -m livebot  # real orders (you set both)
```

## Strategy (matches the backtest)

1. Box = completed M5 bars with open time in **13:30–14:00 UTC** → `box_high` = max high, `box_low` = min low.
2. From 14:00 UTC: OCO stop orders — **BUY-STOP @ box_high**, **SELL-STOP @ box_low** (`0.01` lot). First to trade wins; the other is cancelled.
3. Stop-loss = the opposite box extreme (long → box_low, short → box_high). No fixed target.
4. **No new entry at/after 18:00 UTC.** Any open position is **force-flat at/after 20:00 UTC**.
5. One trade per day.

### Live-only guards (`config.py`)

- `MAX_BOX_WIDTH_USD` (12.0) — skip the day if the box is wider than this.
- `MAX_SPREAD_USD` (0.60) — block the first arm / pull orders on a spread spike. *Not* a per-tick flap gate.
- `MAX_TRADES_PER_DAY` (1), `MAX_DAILY_LOSS_USD` (25.0), `MAX_OPEN_POSITIONS` (1).
- Kill switch: create a file named `STOP` in `livebot/` to halt new entries (open positions still managed to flat). Delete it to resume.
- Don't-chase: if price already broke a box level before the bot ever armed that day, the day is skipped.

## Logs

- `logs/decisions.jsonl` — every decision / event (arming, fills, cancels, errors).
- `logs/trades.csv` — one row per closed trade, same columns as `forward/h1_forward_log.csv`, so `python -m forward.h1_forward report` reads paper/live trades too. Includes `entry_spread` and `slippage_vs_box` — those two numbers are what decide whether the edge survives live (backtest breakeven spread ≈ $0.30).

## Reality check

The backtest says H1 is **breakeven-at-best**: gross +$0.388/trade, net ≈ −$0.03
at a $0.34 spread, PF ~1.04 even at a $0.20 spread, and not statistically
significant out-of-sample. Run `paper` for **3–5 months** (≈60–100 trades) and
watch the realised `entry_spread` + `slippage_vs_box` before considering `live`.

## Tests

```bash
python -m pytest livebot/tests/ -q
```

Cover the decision logic only (box calc, arming, OCO levels, all guards, flat
time). No MT5 connection required.

## Files

| File | Role |
|---|---|
| `h1_strategy.py` | pure decision logic + state machine (no I/O) |
| `brokers.py` | `Mt5Feed` / `ReplayFeed` price feeds; `PaperBroker` (sim) / `Mt5Broker` (real, gated) |
| `runner.py` | the poll loop: build Context → `decide()` → execute Intent |
| `logbook.py` | JSONL decision stream + trades CSV |
| `config.py` | all knobs; `MODE` defaults to `paper` |
| `__main__.py` | entry point |
