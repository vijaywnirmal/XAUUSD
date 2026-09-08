# XAUUSD Backtest Verification Web App

Local-only Next.js + FastAPI app that lets you interactively re-run the
project's existing research (`research/`, `backtest/`, `data_pipeline/`)
from a browser: pick a strategy, tune its parameters, view price/indicator/
equity charts, inspect the trade log, compare multiple runs, and export
CSV/JSON/PDF. Nothing under `research/`, `backtest/`, `data_pipeline/` is
modified — the backend only imports and calls those modules.

## Run it

Two servers, both from the **repo root** (`C:\Users\Vijay\Downloads\XAUUSD`).

### 1. Backend (FastAPI / uvicorn), port 8000

```bash
pip install -r webapp/backend/requirements.txt
python -m uvicorn webapp.backend.main:app --reload --port 8000
```

Must be launched from the repo root (not `webapp/backend/`) so that
`research`, `backtest`, `data_pipeline` import as top-level packages.

Reads bars from the Postgres `xauusd` database — the single source of truth
(see `data_pipeline/dataset.py`). Connection settings come from the `PG*` env
vars (defaults in `db/config.py`); override them in `webapp/backend/.env`.

Optional `webapp/backend/.env` (copy from `.env.example`) for the Strategy
Builder's AI parsing and Postgres connection overrides — see that file.

### 2. Frontend (Next.js), default port 3000

```bash
cd webapp/frontend
pnpm install
pnpm dev
```

Open http://localhost:3000 — Next.js rewrites `/api/*` to
`http://127.0.0.1:8000/*` (see `webapp/frontend/next.config.mjs`), and CORS
on the backend is opened to `http://localhost:3000`.

## What's wired up

- **Registry: clean slate.** Every previously-registered hypothesis
  (H1–H18, NFP straddle, the H5/H6/H7/H8/H14 daily-portfolio sleeves) and
  the ML meta-labeling layer (`webapp/backend/ml/`) were removed on operator
  request, along with the underlying `research/*.py` / `research/H*_RESULT.md`
  files and `PROJECT_SUMMARY.md`. `webapp/backend/registry.py` now holds an
  empty `STRATEGY_REGISTRY` — the `StrategySpec`/`ParamSpec` scaffolding and
  the intraday (`signal_fn` + `bt_defaults`) / daily-portfolio (`daily_fn`)
  shapes are documented in that file's docstring for whatever gets built
  next. `backtest/`, `data_pipeline/`, and the rest of this app are
  untouched.
- **Strategy Builder**: compose long/short entry rules from the indicator
  library (`webapp/backend/indicators.py`: SMA, EMA, RSI, ATR, ADX,
  Stochastic, CCI, Bollinger, MACD, Donchian) with a fixed-$ stop/target/
  session-flat bracket, run through the same `Backtester`.
  - **"Parse with AI"**: describe the strategy in plain English and it fills
    in the rule rows for you to review before running (`webapp/backend/nl_parser.py`).
    Three backends, auto-selected: `ANTHROPIC_API_KEY` set → Claude (best
    accuracy); else a reachable Ollama → local model (no key/cost, lower
    accuracy); else a bounded offline regex/keyword parser (no network at
    all). Force one with `NL_PARSER_BACKEND=anthropic|ollama|local` in
    `webapp/backend/.env`. Whichever backend runs, only the rule rows get
    populated — nothing executes until you click "Run custom strategy", and
    every field is re-validated server-side against the indicator registry
    regardless of what the model returned.
  - **"Preview on chart"**: evaluates the current rules (or the just-parsed
    ones, automatically) against real data — same evaluation path the actual
    run uses (`builder.compute_signals`) — and plots price, the referenced
    indicators, and every bar where long/short would fire, so you can
    sanity-check the strategy before spending a full run on it.
  - Running the builder routes its result into the shared **Results** tab,
    same as every registry strategy.
  - **Save / load**: a composed strategy (rules, bracket, trailing stop) can
    be saved by name (`webapp/backend/saved_strategies.py`, a flat JSON file
    under `webapp/backend/data/`) and reloaded later, from another run, or
    after a server restart — `GET/POST /saved-strategies`,
    `GET/DELETE /saved-strategies/{id}`.
- **Compare**: run several strategies at once, overlay equity curves,
  side-by-side metrics table.
- **Export**: CSV (metrics + success bar + trades), JSON (full result), PDF
  (one-page summary with an equity-curve image) per run, from `/export/{run_id}.{fmt}`.

## Known limitations / deviations from the plan

- Chart data is downsampled server-side above ~5,000 bars/points for display
  only; the backtest itself always runs on the full requested timeframe.
- Runs are cached **in-memory only** (`webapp/backend/runner.py:RUN_CACHE`)
  — restarting the backend invalidates existing `run_id`s and their export
  links.
- The registry is currently empty (see "Registry: clean slate" above) — the
  notes below about matching `research/H*_RESULT.md` numbers describe
  verification done against hypotheses that existed before the reset; they're
  kept here as a record of the methodology for whatever gets re-registered
  next, not because those files still exist.

## Verification performed (historical, before the registry reset)

Compared the API's computed numbers against the matching `research/H*_RESULT.md`
for the same split/params (same engine + metrics code, so they should — and
did — match closely):

- **H9d** (in-sample 2009-2022): n=3,803, exp=-$0.094, PF=0.96 — matches
  `H9d_5EMA_TRAIL_RESULT.md` exactly.
- **NFP straddle** (in-sample): n=168, win=56.5%, exp=+$1.79, PF=1.47 —
  matches `NFP_STRADDLE_RESULT.md`.
- **H5** (idealised run): total_return +0.6554, CAGR +0.0303, Sharpe 0.3225,
  Sortino 0.3613, max_dd 0.2855, dd_days 1319 — matches `H5_RESULT.md`
  exactly to 4 decimals.
- **H14**: cash contributed $21,300 matches `H14_DCA_ACCUMULATE_RESULT.md`;
  final equity/notional are within ~1% (small drift from the exact "as of"
  data cutoff at report-generation time vs. now).

## API endpoints

- `GET /strategies` — registry listing + param schemas
- `GET /indicators` — indicator list + param schemas (for the builder)
- `GET /bars?timeframe=&split=&start=&end=` — OHLC (+ optional indicators)
- `POST /backtest` — `{strategy_id, params, run_config}` → result
- `POST /backtest/compare` — `{runs: [...]}` → `{runs: [result, ...]}`
- `POST /strategy-builder/parse` — `{text}` → parsed rule set (see backends above)
- `POST /strategy-builder/preview` — `{timeframe, split, spec}` → OHLC + indicator series + long/short signal timestamps (no Backtester run)
- `POST /strategy-builder/backtest` — `{timeframe, split, spec}` → result
- `GET /export/{run_id}.{csv|json|pdf}`
