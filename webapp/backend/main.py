"""
FastAPI app wrapping the existing data_pipeline / backtest / research code
for interactive re-verification from the webapp/frontend Next.js app.

Run:
    uvicorn webapp.backend.main:app --reload --port 8000
(from the repo root, so `research`, `backtest`, `data_pipeline` import cleanly)

Data backend: bars come from the Postgres `xauusd` db (see
data_pipeline/dataset.py) — the single source of truth. Connection settings
come from the PG* env vars in webapp/backend/.env (loaded below).
"""
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from webapp.backend import runner, export, builder, nl_parser, saved_strategies, livebot_monitor, monitor_view
from webapp.backend.registry import STRATEGY_REGISTRY
from webapp.backend.indicators import INDICATOR_REGISTRY
from webapp.backend.jsonsafe import safe
from data_pipeline.dataset import load_bars
from backtest.metrics import compute_metrics, success_bar, monte_carlo_trades

app = FastAPI(title="XAUUSD Backtest Verification API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BacktestRequest(BaseModel):
    strategy_id: str
    params: dict[str, Any] = {}
    run_config: dict[str, Any] = {}


class CompareRequest(BaseModel):
    runs: list[BacktestRequest]


class BuilderRequest(BaseModel):
    timeframe: str = "5min"
    split: Optional[str] = "in_sample"
    start: Optional[str] = None
    end: Optional[str] = None
    spec: dict[str, Any]


class NLParseRequest(BaseModel):
    text: str


class SaveStrategyRequest(BaseModel):
    name: str
    timeframe: str = "5min"
    split: Optional[str] = "in_sample"
    start: Optional[str] = None
    end: Optional[str] = None
    spec: dict[str, Any]
    id: Optional[str] = None   # present -> overwrite that saved strategy


class BuilderPreviewRequest(BaseModel):
    timeframe: str = "5min"
    split: Optional[str] = "in_sample"
    start: Optional[str] = None
    end: Optional[str] = None
    spec: dict[str, Any]


@app.get("/")
def root():
    return {"ok": True, "strategies": len(STRATEGY_REGISTRY)}


@app.get("/strategies")
def strategies():
    return runner.list_strategies()


@app.get("/indicators")
def indicators():
    return [{"id": k, **v} for k, v in INDICATOR_REGISTRY.items()]


@app.get("/bars")
def bars(timeframe: str = "5min", split: Optional[str] = "in_sample",
         start: Optional[str] = None, end: Optional[str] = None):
    try:
        return runner.get_bars(timeframe, split, start, end)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/backtest")
def backtest(req: BacktestRequest):
    try:
        return runner.run_backtest(req.strategy_id, req.params, req.run_config)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}")


@app.post("/backtest/compare")
def backtest_compare(req: CompareRequest):
    results = []
    for r in req.runs:
        try:
            results.append(runner.run_backtest(r.strategy_id, r.params, r.run_config))
        except Exception as e:
            results.append({"error": f"{type(e).__name__}: {e}", "strategy_id": r.strategy_id})
    return {"runs": results}


@app.post("/strategy-builder/parse")
def strategy_builder_parse(req: NLParseRequest):
    try:
        return nl_parser.parse_strategy_text(req.text)
    except nl_parser.NLParseError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"{type(e).__name__}: {e}")


@app.post("/strategy-builder/preview")
def strategy_builder_preview(req: BuilderPreviewRequest):
    try:
        return runner.get_builder_preview(req.spec, req.timeframe, req.split, req.start, req.end)
    except Exception as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}")


@app.post("/strategy-builder/backtest")
def strategy_builder_backtest(req: BuilderRequest):
    try:
        df = load_bars(req.timeframe, split=req.split, start=req.start, end=req.end,
                       columns=["ts", "open", "high", "low", "close", "spread_mean"])
        res = builder.compile_and_run(df, req.spec)
        metrics = compute_metrics(res, req.timeframe)
        sb = success_bar(metrics)
        mc = monte_carlo_trades(res)
        trades = res["trades"]
        eq = runner._downsample_series(res["equity"])
        import uuid
        run_id = str(uuid.uuid4())
        result = {
            "run_id": run_id,
            "category": "builder",
            "strategy": {"id": "custom_builder", "name": "Custom (Strategy Builder)"},
            "params": req.spec, "run_config": {"timeframe": req.timeframe, "split": req.split},
            "metrics": safe(metrics),
            "success_bar": safe(sb.to_dict(orient="records")),
            "success_bar_all_pass": bool(sb.attrs.get("all_pass", False)),
            "monte_carlo": safe(mc),
            "n_bars": len(df),
            "trades": safe(trades.to_dict(orient="records")) if len(trades) else [],
            "equity": [{"ts": safe(t), "equity": safe(v)} for t, v in zip(eq.index, eq.values)],
            "ohlc": [{"ts": safe(r.ts), "open": safe(r.open), "high": safe(r.high),
                      "low": safe(r.low), "close": safe(r.close)}
                     for r in runner._downsample_ohlc(df[["ts", "open", "high", "low", "close"]]).itertuples()],
        }
        runner.RUN_CACHE[run_id] = result
        return result
    except Exception as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}")


@app.get("/saved-strategies")
def list_saved_strategies():
    return saved_strategies.list_saved()


@app.get("/saved-strategies/{strategy_id}")
def get_saved_strategy(strategy_id: str):
    record = saved_strategies.get_saved(strategy_id)
    if record is None:
        raise HTTPException(404, "saved strategy not found")
    return record


@app.post("/saved-strategies")
def create_saved_strategy(req: SaveStrategyRequest):
    return saved_strategies.save_strategy(
        req.name, req.timeframe, req.split, req.start, req.end, req.spec, strategy_id=req.id,
    )


@app.delete("/saved-strategies/{strategy_id}")
def delete_saved_strategy(strategy_id: str):
    if not saved_strategies.delete_saved(strategy_id):
        raise HTTPException(404, "saved strategy not found")
    return {"ok": True}


@app.get("/livebot/status")
def livebot_status():
    return livebot_monitor.status()


@app.get("/livebot/decisions")
def livebot_decisions(limit: int = 50):
    return livebot_monitor.decisions(limit)


@app.get("/livebot/trades")
def livebot_trades():
    return livebot_monitor.trades()


@app.get("/monitor/snapshot")
def monitor_snapshot():
    return monitor_view.snapshot()


@app.get("/monitor/history")
def monitor_history(limit: int = 240):
    return monitor_view.history(limit)


@app.get("/run/{run_id}/detail")
def run_detail(run_id: str, days: int = 30):
    try:
        return runner.get_run_detail(run_id, days)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}")


@app.get("/export/{run_id}.{fmt}")
def export_run(run_id: str, fmt: str):
    result = runner.get_run(run_id)
    if result is None:
        raise HTTPException(404, "run not found (in-memory cache — was the server restarted?)")
    if fmt == "csv":
        data = export.to_csv_bytes(result)
        media = "text/csv"
    elif fmt == "json":
        data = export.to_json_bytes(result)
        media = "application/json"
    elif fmt == "pdf":
        data = export.to_pdf_bytes(result)
        media = "application/pdf"
    else:
        raise HTTPException(400, "fmt must be csv, json, or pdf")
    export.save_and_get_path(run_id, fmt, data)
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": f"attachment; filename={run_id}.{fmt}"})
