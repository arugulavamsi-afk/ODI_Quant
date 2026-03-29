"""
ODI Quant — FastAPI backend
Endpoints:
  GET  /api/run                  — trigger daily pipeline
  GET  /api/results/latest       — latest results from DB
  GET  /api/results/{date}       — results for specific date
  GET  /api/stock/{symbol}       — details for one stock
  GET  /api/global-sentiment/latest — latest global sentiment
  GET  /api/backtest             — run portfolio backtest
  GET  /app                      — serve dashboard HTML
"""
import logging
import os
import sys
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# Add backend dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline.daily_pipeline import run_daily_pipeline
from storage.db import initialize_db, get_latest_results, get_results_by_date, get_available_dates
from data.fetcher import fetch_all_stocks, fetch_global_data
from data.universe import STOCK_UNIVERSE
from backtest.backtester import run_portfolio_backtest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize DB on startup
initialize_db()

app = FastAPI(
    title="ODI Quant",
    description="NSE Day Trading Scanner — Next-Day Setup Probability Engine",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pipeline state (simple in-memory lock)
_pipeline_running = False
_last_pipeline_result = None


# ─── Static frontend ──────────────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/app", include_in_schema=False)
async def serve_dashboard():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Frontend not found")


@app.get("/", include_in_schema=False)
async def root_redirect():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


# ─── API Endpoints ────────────────────────────────────────────────────────────

@app.get("/api/run")
async def run_pipeline():
    """Trigger the full daily pipeline. Fetches data, computes signals, ranks stocks."""
    global _pipeline_running, _last_pipeline_result

    if _pipeline_running:
        return JSONResponse(
            status_code=202,
            content={"status": "running", "message": "Pipeline already running, please wait..."}
        )

    _pipeline_running = True
    try:
        logger.info("API: Starting daily pipeline")
        result = run_daily_pipeline()
        _last_pipeline_result = result
        return {
            "status": "success",
            "run_date": result["run_date"],
            "summary": result["summary"],
            "global_sentiment": result["global_sentiment"],
            "stocks": _format_stocks_for_api(result["stocks"]),
        }
    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")
    finally:
        _pipeline_running = False


@app.get("/api/results/latest")
async def get_latest():
    """Get the most recent pipeline results from DB."""
    results = get_latest_results()
    if not results:
        return JSONResponse(
            status_code=404,
            content={"status": "no_data", "message": "No results found. Run /api/run first."}
        )
    return _format_db_results(results)


@app.get("/api/results/{date}")
async def get_results_for_date(date: str):
    """Get results for a specific date (YYYY-MM-DD)."""
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must be in YYYY-MM-DD format")

    results = get_results_by_date(date)
    if not results or not results.get("stocks"):
        raise HTTPException(status_code=404, detail=f"No results found for {date}")
    return _format_db_results(results)


@app.get("/api/stock/{symbol}")
async def get_stock_detail(symbol: str):
    """Get full details for a specific stock from latest results."""
    results = get_latest_results()
    if not results:
        raise HTTPException(status_code=404, detail="No results available")

    symbol_upper = symbol.upper()
    for stock in results.get("stocks", []):
        if stock.get("symbol", "").upper() == symbol_upper:
            return stock

    raise HTTPException(status_code=404, detail=f"Stock {symbol} not found in latest results")


@app.get("/api/global-sentiment/latest")
async def get_global_sentiment():
    """Get latest global sentiment data."""
    results = get_latest_results()
    if not results:
        # Fetch fresh global data
        try:
            from sentiment.global_sentiment import calculate_global_score
            global_data = fetch_global_data()
            sentiment = calculate_global_score(global_data)
            return sentiment
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    gs = results.get("global_sentiment")
    if not gs:
        raise HTTPException(status_code=404, detail="No global sentiment data")
    return gs


@app.get("/api/dates")
async def get_available():
    """Get list of dates with available results."""
    dates = get_available_dates()
    return {"dates": dates}


@app.get("/api/backtest")
async def run_backtest_endpoint(period_days: int = 252):
    """Run portfolio backtest. Warning: this may take a few minutes."""
    try:
        logger.info(f"Starting portfolio backtest ({period_days} days)...")
        stock_data = fetch_all_stocks(STOCK_UNIVERSE)
        result = run_portfolio_backtest(stock_data, period_days=period_days)
        return result
    except Exception as e:
        logger.error(f"Backtest error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "version": "1.0.0",
        "time": datetime.now().isoformat(),
        "pipeline_running": _pipeline_running,
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _format_stocks_for_api(stocks: list) -> list:
    """Format pipeline stock results for API response."""
    formatted = []
    for s in stocks:
        cls = s.get("classification", {})
        ind = s.get("indicators", {})
        tl = s.get("trade_levels", {})
        formatted.append({
            "rank": s.get("rank"),
            "symbol": s.get("symbol"),
            "name": s.get("name"),
            "sector": s.get("sector"),
            "cmp": ind.get("close"),
            "long_score": s.get("long_score"),
            "short_score": s.get("short_score"),
            "category": cls.get("category"),
            "direction": cls.get("direction"),
            "trend_bias": ind.get("trend_bias"),
            "volume_spike": ind.get("volume_spike"),
            "breakout_status": ind.get("breakout_status"),
            "closing_strength": ind.get("closing_strength"),
            "atr_expansion": ind.get("atr_expansion"),
            "long_signal_quality": s.get("long_signal", {}).get("signal"),
            "short_signal_quality": s.get("short_signal", {}).get("signal"),
            "entry": tl.get("entry"),
            "stop_loss": tl.get("stop_loss"),
            "target1": tl.get("target1"),
            "target2": tl.get("target2"),
            "risk_pct": tl.get("risk_pct"),
            "position_size_1L": tl.get("position_size_1L"),
            "explanation": s.get("explanation"),
            "indicators": ind,
        })
    return formatted


def _format_db_results(results: dict) -> dict:
    """Format DB results for API response."""
    stocks = []
    for s in results.get("stocks", []):
        ind = s.get("indicators_json", {})
        tl = s.get("trade_levels_json", {})
        ls = s.get("long_signal_json", {})
        ss = s.get("short_signal_json", {})
        stocks.append({
            "rank": s.get("rank"),
            "symbol": s.get("symbol"),
            "name": s.get("name"),
            "sector": s.get("sector"),
            "cmp": s.get("entry") or (ind.get("close") if isinstance(ind, dict) else None),
            "long_score": s.get("long_score"),
            "short_score": s.get("short_score"),
            "category": s.get("category"),
            "direction": s.get("direction"),
            "trend_bias": ind.get("trend_bias") if isinstance(ind, dict) else None,
            "volume_spike": ind.get("volume_spike") if isinstance(ind, dict) else None,
            "breakout_status": ind.get("breakout_status") if isinstance(ind, dict) else None,
            "closing_strength": ind.get("closing_strength") if isinstance(ind, dict) else None,
            "atr_expansion": ind.get("atr_expansion") if isinstance(ind, dict) else None,
            "long_signal_quality": ls.get("signal") if isinstance(ls, dict) else None,
            "short_signal_quality": ss.get("signal") if isinstance(ss, dict) else None,
            "entry": s.get("entry"),
            "stop_loss": s.get("stop_loss"),
            "target1": s.get("target1"),
            "target2": s.get("target2"),
            "risk_pct": s.get("risk_pct"),
            "position_size_1L": tl.get("position_size_1L") if isinstance(tl, dict) else None,
            "explanation": s.get("explanation"),
            "indicators": ind if isinstance(ind, dict) else {},
        })

    gs = results.get("global_sentiment", {})
    if isinstance(gs, dict):
        gs_data = {
            "score": gs.get("score"),
            "classification": gs.get("classification"),
            "long_adjustment": gs.get("long_adjustment"),
            "short_adjustment": gs.get("short_adjustment"),
            "components": gs.get("components_json", gs.get("components", {})),
        }
    else:
        gs_data = {}

    return {
        "run_date": results.get("run_date"),
        "global_sentiment": gs_data,
        "stocks": stocks,
        "summary": results.get("summary", {}),
        "status": "success",
    }
