"""
Daily execution pipeline — orchestrates the full ODI Quant analysis flow.

Steps:
1. Fetch global data → calculate global sentiment
2. Fetch all stock EOD data
3. For each stock: compute indicators → signals → scores → risk levels
4. Classify and rank
5. Save to DB
6. Return structured results
"""
import logging
import sys
import os
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.fetcher import fetch_all_stocks, fetch_global_data, fetch_sector_etf_spikes
from data.universe import STOCK_UNIVERSE
from signals.signal_engine import generate_signals
from scoring.scorer import calculate_long_score, calculate_short_score
from sentiment.global_sentiment import calculate_global_score
from risk.risk_engine import calculate_trade_levels
from ranking.ranker import classify_stock, rank_stocks, generate_explanation
from storage.db import initialize_db, save_results
from config import (MIN_VOLUME, MIN_PRICE, MAX_PRICE,
                    MAX_DAILY_LOSS_PCT, MAX_CONCURRENT_POSITIONS,
                    MAX_SECTOR_EXPOSURE_PCT, COMMISSION_PCT)

logger = logging.getLogger(__name__)


def _safe_float(val, default=0.0):
    """Convert numpy/pandas values to Python float safely."""
    try:
        if val is None:
            return default
        import numpy as np
        if isinstance(val, (np.integer, np.floating)):
            return float(val)
        return float(val)
    except Exception:
        return default


def _safe_int(val, default=0):
    try:
        if val is None:
            return default
        import numpy as np
        if isinstance(val, (np.integer,)):
            return int(val)
        return int(val)
    except Exception:
        return default


def _sanitize_dict(d: dict) -> dict:
    """Recursively convert numpy types in a dict to Python native types."""
    import numpy as np
    if not isinstance(d, dict):
        return d
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _sanitize_dict(v)
        elif isinstance(v, list):
            result[k] = [_sanitize_dict(i) if isinstance(i, dict) else
                         (float(i) if isinstance(i, (np.floating,)) else
                          (int(i) if isinstance(i, (np.integer,)) else i))
                         for i in v]
        elif isinstance(v, (np.integer,)):
            result[k] = int(v)
        elif isinstance(v, (np.floating,)):
            result[k] = float(v)
        elif isinstance(v, (np.bool_,)):
            result[k] = bool(v)
        else:
            result[k] = v
    return result


def apply_liquidity_filter(df, symbol: str) -> bool:
    """Check if stock passes minimum liquidity requirements."""
    if df is None or len(df) < 20:
        return False
    try:
        last = df.iloc[-1]
        close = float(last["Close"])
        avg_vol = float(df["Volume"].tail(20).mean())

        if close < MIN_PRICE or close > MAX_PRICE:
            logger.debug(f"{symbol}: price {close:.0f} outside range")
            return False
        if avg_vol < MIN_VOLUME:
            logger.debug(f"{symbol}: avg volume {avg_vol:.0f} < {MIN_VOLUME}")
            return False
        return True
    except Exception:
        return False


def run_daily_pipeline(universe: dict = None) -> dict:
    """
    Full daily analysis pipeline.
    Returns structured results with all stock setups.
    """
    if universe is None:
        universe = STOCK_UNIVERSE

    run_dt   = datetime.now()
    run_date = run_dt.strftime("%Y-%m-%d")
    run_timestamp = run_dt.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"Starting ODI Quant pipeline for {run_date}")

    # Initialize DB
    initialize_db()

    # Step 1: Fetch global data and compute sentiment
    logger.info("Fetching global market data...")
    global_data = fetch_global_data()
    global_sentiment = calculate_global_score(global_data)
    logger.info(f"Global sentiment: {global_sentiment['classification']} (score: {global_sentiment['score']:+.1f}, crude: {global_sentiment.get('crude_contribution', 0):+.1f})")

    # Step 2: Fetch all stock data
    logger.info(f"Fetching EOD data for {len(universe)} stocks...")
    stock_data = fetch_all_stocks(universe)
    logger.info(f"Fetched {len(stock_data)} stocks successfully")

    # Step 2b: Fetch sector ETF volume spikes (one yfinance call per unique ETF).
    # Used to filter F&O expiry / index rebalancing / post-holiday volume noise —
    # a stock's volume rule only fires when its spike meaningfully exceeds the
    # sector ETF spike on the same day.
    unique_sectors = {info.get("sector", "Unknown") for info in universe.values()}
    sector_etf_spikes = fetch_sector_etf_spikes(unique_sectors)
    logger.info(f"Sector ETF spikes fetched for {len(sector_etf_spikes)}/{len(unique_sectors)} sectors")

    # Step 3-4: Process each stock
    results = []
    for symbol, df in stock_data.items():
        info = universe.get(symbol, {})
        name = info.get("name", symbol)
        sector = info.get("sector", "Unknown")

        try:
            # Liquidity filter
            if not apply_liquidity_filter(df, symbol):
                continue

            # Generate signals and indicators
            sector_etf_spike = sector_etf_spikes.get(sector)
            signal_result = generate_signals(df, sector_etf_spike=sector_etf_spike)
            if signal_result is None:
                logger.debug(f"{symbol}: signal generation returned None")
                continue

            indicators = signal_result["indicators"]
            long_signal = signal_result["long_signal"]
            short_signal = signal_result["short_signal"]

            # Scores are sentiment-independent — global sentiment gates the
            # HIGH_PROB threshold in classify_stock(), it no longer boosts scores.
            long_score  = calculate_long_score(indicators, long_signal)
            short_score = calculate_short_score(indicators, short_signal)

            # Preliminary direction (scores only, no SL check yet) to know which
            # side to compute trade levels for before final classification.
            _pre_direction = "LONG" if long_score >= short_score else "SHORT"

            # Risk levels — computed before classify so sl_too_wide feeds into tier
            trade_levels = calculate_trade_levels(df, _pre_direction, atr_value=indicators.get("atr"))
            sl_too_wide  = trade_levels.get("sl_too_wide", False)

            # Classify — asymmetric HIGH_PROB threshold based on global sentiment;
            # demotes one tier when the natural SL is > 2%.
            sentiment_class = global_sentiment.get("classification", "NEUTRAL") if global_sentiment else "NEUTRAL"
            classification = classify_stock(long_score, short_score,
                                            sl_too_wide=sl_too_wide,
                                            sentiment_class=sentiment_class)
            direction = classification["direction"]

            # Explanation
            explanation = generate_explanation(
                symbol=symbol,
                name=name,
                indicators=indicators,
                long_signal=long_signal,
                short_signal=short_signal,
                long_score=long_score,
                short_score=short_score,
                global_sentiment=global_sentiment,
                trade_levels=trade_levels,
                direction=direction,
            )

            # Build result record
            stock_result = {
                "symbol": symbol,
                "name": name,
                "sector": sector,
                "long_score": _safe_int(long_score),
                "short_score": _safe_int(short_score),
                "classification": classification,
                "direction": direction,
                "indicators": _sanitize_dict(indicators),
                "long_signal": _sanitize_dict(long_signal),
                "short_signal": _sanitize_dict(short_signal),
                "trade_levels": _sanitize_dict(trade_levels),
                "explanation": explanation,
            }

            results.append(stock_result)
            logger.debug(f"{symbol}: L={long_score} S={short_score} [{classification['category']}]")

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}", exc_info=True)
            continue

    # Step 5: Rank all results
    ranked_results = rank_stocks(results)

    # Step 6: Save to DB
    try:
        save_results(run_date, ranked_results, _sanitize_dict(global_sentiment))
        logger.info(f"Results saved for {run_date}")
    except Exception as e:
        logger.error(f"Failed to save results: {e}")

    # Step 7: Build summary
    categories = [r["classification"]["category"] for r in ranked_results]
    summary = {
        "total": len(ranked_results),
        "high_prob_long": sum(1 for c in categories if c == "HIGH_PROB_LONG"),
        "high_prob_short": sum(1 for c in categories if c == "HIGH_PROB_SHORT"),
        "watchlist": sum(1 for c in categories if c == "WATCHLIST"),
        "no_trade": sum(1 for c in categories if c == "NO_TRADE"),
        "stocks_fetched": len(stock_data),
        "stocks_analyzed": len(results),
    }

    logger.info(
        f"Pipeline complete: {summary['high_prob_long']} long, "
        f"{summary['high_prob_short']} short, {summary['watchlist']} watchlist"
    )

    # ── Portfolio risk constraints (for UI display) ───────────────────────────
    portfolio_rules = {
        "max_daily_loss_pct":       MAX_DAILY_LOSS_PCT,
        "max_concurrent_positions": MAX_CONCURRENT_POSITIONS,
        "max_sector_exposure_pct":  MAX_SECTOR_EXPOSURE_PCT,
        "commission_pct_per_leg":   COMMISSION_PCT * 100,
        "rules_summary": (
            f"Stop trading today if down {MAX_DAILY_LOSS_PCT}% | "
            f"Max {MAX_CONCURRENT_POSITIONS} open positions | "
            f"Max {MAX_SECTOR_EXPOSURE_PCT}% capital per sector | "
            f"Commission {COMMISSION_PCT*100:.3f}% per leg ({COMMISSION_PCT*200:.2f}% round-trip)"
        ),
    }

    return {
        "run_date":        run_date,
        "run_timestamp":   run_timestamp,   # full datetime — UI can show staleness warning
        "global_sentiment": _sanitize_dict(global_sentiment),
        "stocks":          ranked_results,
        "summary":         summary,
        "portfolio_rules": portfolio_rules,
        "status":          "success",
    }
