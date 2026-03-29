"""
Backtesting framework for ODI Quant.
Tests signal quality over historical data (1-2 years).
"""
import pandas as pd
import numpy as np
import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators.trend import calculate_moving_averages, get_trend_bias, get_trend_score, get_market_structure
from indicators.volatility import calculate_atr, get_atr_expansion, get_volatility_score
from indicators.volume import get_volume_spike, get_price_volume_alignment, get_volume_score
from indicators.breakout import get_breakout_status, get_closing_strength, get_breakout_score, get_consolidation_breakout
from signals.signal_engine import generate_long_signal, generate_short_signal
from scoring.scorer import calculate_long_score, calculate_short_score
from config import HIGH_PROB_THRESHOLD, BREAKOUT_PERIOD

logger = logging.getLogger(__name__)


def _compute_indicators_at_row(df_slice: pd.DataFrame) -> dict:
    """Compute all indicators for a given slice of data."""
    if len(df_slice) < 50:
        return None
    try:
        df = calculate_moving_averages(df_slice.copy())
        df = calculate_atr(df)

        last = df.iloc[-1]
        ma20 = float(df["MA20"].iloc[-1]) if not pd.isna(df["MA20"].iloc[-1]) else None
        ma50 = float(df["MA50"].iloc[-1]) if not pd.isna(df["MA50"].iloc[-1]) else None
        ma200 = float(df["MA200"].iloc[-1]) if not pd.isna(df["MA200"].iloc[-1]) else None
        atr_val = float(df["ATR"].iloc[-1]) if not pd.isna(df["ATR"].iloc[-1]) else 0.0

        trend_bias = get_trend_bias(df)
        market_structure = get_market_structure(df)
        breakout_info = get_breakout_status(df)
        closing_strength = get_closing_strength(df)
        volume_spike = get_volume_spike(df)
        pv_alignment = get_price_volume_alignment(df)
        atr_expansion = get_atr_expansion(df)
        range_ratio = float.__round__(float(get_atr_expansion(df)), 2)
        consol_breakout, _ = get_consolidation_breakout(df)

        return {
            "close": float(last["Close"]),
            "atr": atr_val,
            "ma20": ma20, "ma50": ma50, "ma200": ma200,
            "trend_bias": trend_bias,
            "market_structure": market_structure,
            "breakout_status": breakout_info["status"],
            "breakout_level": breakout_info.get("breakout_level"),
            "breakdown_level": breakout_info.get("breakdown_level"),
            "resistance": breakout_info.get("resistance"),
            "support": breakout_info.get("support"),
            "closing_strength": closing_strength,
            "volume_spike": volume_spike,
            "price_volume_alignment": pv_alignment,
            "atr_expansion": atr_expansion,
            "range_ratio": range_ratio,
            "consolidation_breakout": consol_breakout,
            "trend_score": get_trend_score(df),
            "breakout_score": get_breakout_score(df),
            "volume_score": get_volume_score(df),
            "volatility_score": get_volatility_score(df),
        }
    except Exception as e:
        logger.debug(f"Indicator compute error: {e}")
        return None


def run_backtest(symbol: str, df: pd.DataFrame, period_days: int = 252) -> dict:
    """
    Signal-based backtest over historical data.

    For each day in the lookback window:
    - Generate signal using all prior data (no look-ahead)
    - If HIGH_PROB signal: simulate next-day trade
      - Entry: next day open
      - Exit: check if target (2:1) or SL hit first within the day
    - Track outcomes

    Returns metrics dict.
    """
    if df is None or len(df) < 250:
        return {"error": "Insufficient data for backtest"}

    df = df.copy().sort_index()

    # Use last `period_days` + lookback buffer
    total_needed = period_days + 210  # 210 days for indicators warmup
    if len(df) > total_needed:
        df = df.iloc[-total_needed:]

    trades = []
    equity_curve = [1.0]
    equity = 1.0

    # Iterate over each tradeable day
    for i in range(210, len(df) - 1):
        df_slice = df.iloc[:i+1]
        indicators = _compute_indicators_at_row(df_slice)
        if indicators is None:
            continue

        long_signal = generate_long_signal(df_slice, indicators)
        short_signal = generate_short_signal(df_slice, indicators)

        long_score = calculate_long_score(indicators, long_signal, 0)
        short_score = calculate_short_score(indicators, short_signal, 0)

        # Only trade high-probability setups
        direction = None
        score = 0
        signal = None
        if long_score >= HIGH_PROB_THRESHOLD and long_score >= short_score:
            direction = "LONG"
            score = long_score
            signal = long_signal
        elif short_score >= HIGH_PROB_THRESHOLD:
            direction = "SHORT"
            score = short_score
            signal = short_signal

        if direction is None:
            continue

        # Next day trade simulation
        next_day = df.iloc[i + 1]
        entry = float(next_day["Open"])
        day_high = float(next_day["High"])
        day_low = float(next_day["Low"])
        day_close = float(next_day["Close"])

        atr = indicators["atr"]
        if atr == 0:
            atr = entry * 0.02

        if direction == "LONG":
            sl = entry - (atr * 1.5)
            target = entry + (atr * 1.5 * 2)  # 2:1 RR

            # Determine outcome: did price hit target or SL first?
            # Simple rule: if day_low < sl → SL hit (loss), if day_high > target → target hit (win)
            if day_low <= sl:
                outcome = "LOSS"
                pnl_r = -1.0  # -1R
            elif day_high >= target:
                outcome = "WIN"
                pnl_r = 2.0  # +2R
            else:
                # Closed without hitting either: use close
                close_pnl = day_close - entry
                sl_dist = entry - sl
                pnl_r = close_pnl / sl_dist if sl_dist > 0 else 0
                outcome = "WIN" if pnl_r > 0 else "LOSS"
        else:  # SHORT
            sl = entry + (atr * 1.5)
            target = entry - (atr * 1.5 * 2)

            if day_high >= sl:
                outcome = "LOSS"
                pnl_r = -1.0
            elif day_low <= target:
                outcome = "WIN"
                pnl_r = 2.0
            else:
                close_pnl = entry - day_close
                sl_dist = sl - entry
                pnl_r = close_pnl / sl_dist if sl_dist > 0 else 0
                outcome = "WIN" if pnl_r > 0 else "LOSS"

        trades.append({
            "date": str(df.index[i].date()),
            "direction": direction,
            "score": score,
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "target": round(target, 2),
            "outcome": outcome,
            "pnl_r": round(pnl_r, 2),
            "signal_quality": signal.get("signal", "N/A"),
        })

        # Update equity (fixed fractional: 1R = 2% of equity)
        equity *= (1 + pnl_r * 0.02)
        equity_curve.append(round(equity, 4))

    if not trades:
        return {"error": "No trades generated", "symbol": symbol}

    # Metrics
    total_trades = len(trades)
    wins = [t for t in trades if t["outcome"] == "WIN"]
    losses = [t for t in trades if t["outcome"] == "LOSS"]

    win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
    avg_win_r = np.mean([t["pnl_r"] for t in wins]) if wins else 0
    avg_loss_r = np.mean([t["pnl_r"] for t in losses]) if losses else 0
    avg_rr = np.mean([t["pnl_r"] for t in trades]) if trades else 0

    # Expectancy = (Win% * Avg Win) + (Loss% * Avg Loss)
    loss_rate = 1 - (win_rate / 100)
    expectancy = (win_rate / 100 * avg_win_r) + (loss_rate * avg_loss_r)

    # Max drawdown
    peak = 1.0
    max_dd = 0.0
    for e in equity_curve:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd:
            max_dd = dd

    final_equity = equity_curve[-1] if equity_curve else 1.0
    total_return = (final_equity - 1.0) * 100

    return {
        "symbol": symbol,
        "period_days": period_days,
        "total_trades": total_trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "avg_win_r": round(avg_win_r, 2),
        "avg_loss_r": round(avg_loss_r, 2),
        "avg_rr": round(avg_rr, 2),
        "expectancy": round(expectancy, 3),
        "max_drawdown_pct": round(max_dd, 2),
        "total_return_pct": round(total_return, 2),
        "trades": trades[-20:],  # Last 20 trades for display
    }


def run_portfolio_backtest(stock_data: dict, period_days: int = 252) -> dict:
    """Run backtest across all stocks and aggregate results."""
    all_results = []
    total_trades_agg = []

    for symbol, df in stock_data.items():
        try:
            result = run_backtest(symbol, df, period_days)
            if "error" not in result:
                all_results.append(result)
                total_trades_agg.extend(result.get("trades", []))
                logger.info(f"Backtest {symbol}: {result['total_trades']} trades, {result['win_rate']}% WR")
        except Exception as e:
            logger.warning(f"Backtest failed for {symbol}: {e}")

    if not all_results:
        return {"error": "No backtest results available"}

    # Aggregate metrics
    all_win_rates = [r["win_rate"] for r in all_results]
    all_expectancy = [r["expectancy"] for r in all_results]
    all_dd = [r["max_drawdown_pct"] for r in all_results]
    all_trades = [r["total_trades"] for r in all_results]

    return {
        "period_days": period_days,
        "stocks_tested": len(all_results),
        "total_trades": sum(all_trades),
        "avg_win_rate": round(np.mean(all_win_rates), 1),
        "avg_expectancy": round(np.mean(all_expectancy), 3),
        "avg_max_drawdown_pct": round(np.mean(all_dd), 2),
        "best_stock": max(all_results, key=lambda x: x["win_rate"])["symbol"],
        "worst_stock": min(all_results, key=lambda x: x["win_rate"])["symbol"],
        "individual_results": sorted(all_results, key=lambda x: x["win_rate"], reverse=True)[:10],
    }
