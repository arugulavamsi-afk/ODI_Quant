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
# Try multiple locations so it works locally AND on Render/cloud
def _find_frontend_dir() -> str:
    candidates = [
        # Relative to this file: backend/../frontend
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend"),
        # Relative to CWD (set to backend/ by start_server.py): ../frontend
        os.path.join(os.getcwd(), "..", "frontend"),
        # Absolute from repo root env var (optional override)
        os.path.join(os.environ.get("PROJECT_ROOT", ""), "frontend"),
    ]
    for path in candidates:
        norm = os.path.normpath(path)
        if os.path.isdir(norm):
            logger.info(f"Frontend found at: {norm}")
            return norm
    logger.warning("Frontend directory not found in any candidate path")
    return os.path.normpath(candidates[0])  # fallback

FRONTEND_DIR = _find_frontend_dir()

if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/app", include_in_schema=False)
async def serve_dashboard():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail=f"Frontend not found at {FRONTEND_DIR}")


@app.get("/", include_in_schema=False)
async def root_redirect():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail=f"Frontend not found at {FRONTEND_DIR}")


_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}

@app.get("/styles.css", include_in_schema=False)
async def serve_css():
    return FileResponse(os.path.join(FRONTEND_DIR, "styles.css"), media_type="text/css", headers=_NO_CACHE)


@app.get("/app.js", include_in_schema=False)
async def serve_js():
    return FileResponse(os.path.join(FRONTEND_DIR, "app.js"), media_type="application/javascript", headers=_NO_CACHE)


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


@app.get("/api/nifty/analysis")
async def get_nifty_analysis():
    """
    Full NIFTY50 options analysis.
    Fetches live NIFTY data + global sentiment, runs the directional engine
    and options strategy engine, returns a structured trade plan.
    """
    try:
        from data.fetcher import fetch_nifty_data, fetch_global_data
        from sentiment.global_sentiment import calculate_global_score
        from nifty.nifty_analyzer import analyze_nifty
        from nifty.options_engine import generate_options_analysis

        logger.info("NIFTY analysis: fetching data...")
        nifty_df     = fetch_nifty_data(period="1y")
        global_data  = fetch_global_data()
        global_sent  = calculate_global_score(global_data)

        if nifty_df is None or nifty_df.empty:
            raise HTTPException(status_code=503, detail="Could not fetch NIFTY50 market data")

        nifty_analysis = analyze_nifty(nifty_df, global_sent)
        if nifty_analysis.get("status") == "error":
            raise HTTPException(status_code=503, detail=nifty_analysis.get("error"))

        options_analysis = generate_options_analysis(nifty_analysis, global_sent)

        logger.info("NIFTY analysis complete — expected move: %s", nifty_analysis.get("expected_move"))
        return {
            "status":           "success",
            "run_date":         datetime.now().strftime("%Y-%m-%d"),
            "run_time":         datetime.now().strftime("%H:%M:%S"),
            "nifty_overview":   nifty_analysis,
            "options_analysis": options_analysis,
            "global_sentiment": {
                "score":          global_sent.get("score"),
                "classification": global_sent.get("classification"),
                "components":     global_sent.get("components", {}),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("NIFTY analysis error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"NIFTY analysis failed: {str(e)}")


@app.get("/api/strategy/intra-contra")
async def get_intra_contra():
    """
    IntraContra — 3M Momentum Swing System.
    Scans full NIFTY 100 for Flag & Pole, EMA Pullback, 52W High Breakout,
    and Sector Rotation setups with multi-timeframe trend confirmation.
    """
    try:
        from strategy.intra_contra import run_intra_contra
        logger.info("IntraContra scan: starting…")
        result = run_intra_contra(STOCK_UNIVERSE)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error", "Scan failed"))
        logger.info(
            "IntraContra complete — %d stocks, %d with setups",
            result["summary"]["total"],
            result["summary"]["with_setups"],
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("IntraContra error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"IntraContra failed: {str(e)}")


@app.get("/api/strategy/trend-pullback")
async def get_trend_pullback_strategy():
    """
    "Ride the Trend, Snipe the Pullback" strategy engine.
    Phases: Market Context → Sector Rotation → Quality Gate → Pattern Detection.
    Typical runtime: 60–120 s (fetches live data for all qualifying stocks).
    """
    try:
        from strategy.trend_pullback import run_trend_pullback_strategy
        logger.info("Trend-Pullback strategy: starting…")
        result = run_trend_pullback_strategy(STOCK_UNIVERSE)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error", "Strategy failed"))
        logger.info(
            "Trend-Pullback complete — %d qualified, %d with patterns",
            result["summary"]["total_qualified"],
            result["summary"]["with_patterns"],
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Trend-Pullback error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Strategy failed: {str(e)}")


@app.get("/api/strategy/bigbag")
async def get_bigbag():
    """
    BigBag — Asymmetric Compounding Quality Screen.
    Screens ~50 curated quality NSE stocks using EMPIRE framework metrics
    (ROE, EPS growth, margins, D/E, PEG) from yfinance fundamentals.
    """
    try:
        from strategy.bigbag import run_bigbag
        logger.info("BigBag screen: starting…")
        result = run_bigbag()
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error", "Screen failed"))
        logger.info(
            "BigBag complete — %d stocks, %d Tier-1, %d Tier-2",
            result["summary"]["total"],
            result["summary"]["tier1"],
            result["summary"]["tier2"],
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("BigBag error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"BigBag screen failed: {str(e)}")


@app.get("/api/strategy/bigbag/debug")
async def bigbag_debug():
    """One-ticker diagnostic — returns raw yfinance result or full error traceback."""
    import traceback
    import yfinance as yf
    try:
        t = yf.Ticker("TCS.NS")
        info = t.info or {}
        return {
            "ok": True,
            "keys_returned": len(info),
            "currentPrice": info.get("currentPrice"),
            "returnOnEquity": info.get("returnOnEquity"),
            "trailingPE": info.get("trailingPE"),
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


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
            "entry_trigger": tl.get("entry_trigger"),
            "stop_loss": tl.get("stop_loss"),
            "target1": tl.get("target1"),
            "target2": tl.get("target2"),
            "target3": tl.get("target3"),
            "risk_pct": tl.get("risk_pct"),
            "rr_t1": tl.get("rr_t1"),
            "rr_t2": tl.get("rr_t2"),
            "rr_t3": tl.get("rr_t3"),
            "position_size_1L": tl.get("position_size_1L"),
            "setup_note": tl.get("setup_note"),
            "prev_day_high": tl.get("prev_day_high"),
            "prev_day_low": tl.get("prev_day_low"),
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
            "entry_trigger": s.get("entry_trigger") or (tl.get("entry_trigger") if isinstance(tl, dict) else None),
            "stop_loss": s.get("stop_loss"),
            "target1": s.get("target1"),
            "target2": s.get("target2"),
            "target3": s.get("target3") or (tl.get("target3") if isinstance(tl, dict) else None),
            "risk_pct": s.get("risk_pct"),
            "rr_t1": tl.get("rr_t1") if isinstance(tl, dict) else None,
            "rr_t2": tl.get("rr_t2") if isinstance(tl, dict) else None,
            "rr_t3": tl.get("rr_t3") if isinstance(tl, dict) else None,
            "position_size_1L": tl.get("position_size_1L") if isinstance(tl, dict) else None,
            "setup_note": tl.get("setup_note") if isinstance(tl, dict) else None,
            "prev_day_high": tl.get("prev_day_high") if isinstance(tl, dict) else None,
            "prev_day_low": tl.get("prev_day_low") if isinstance(tl, dict) else None,
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
