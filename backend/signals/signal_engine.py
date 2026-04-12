"""
Signal Engine - combines all indicators and generates trade signals
"""
import pandas as pd
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators.trend import (calculate_moving_averages, calculate_rsi,
                              get_trend_bias, get_market_structure, get_trend_score,
                              get_rsi_score, RSI_OVERBOUGHT, RSI_OVERSOLD)
from indicators.volatility import calculate_atr, get_atr_expansion, get_range_vs_historical, get_volatility_score
from indicators.volume import get_volume_spike, get_price_volume_alignment, get_volume_score
from indicators.breakout import get_breakout_status, get_closing_strength, get_breakout_score, get_consolidation_breakout
from signals.long_signals import check_long_rules
from signals.short_signals import check_short_rules
from config import BREAKOUT_PERIOD


def generate_long_signal(df: pd.DataFrame, indicators: dict) -> dict:
    """
    LONG signal rules (ALL must be true for HIGH_CONFIDENCE, 3/5 for MODERATE):
    1. Trend = BULLISH
    2. Breakout = BREAKOUT or NEAR_BREAKOUT
    3. Volume spike > 1.5x
    4. Closing strength > 65%
    5. ATR expanding

    Returns: signal dict with confidence level
    """
    rules = check_long_rules(indicators)
    rule_count = rules["rule_count"]

    if rule_count == 5:
        signal = "HIGH_CONFIDENCE"
    elif rule_count >= 4:
        signal = "HIGH_CONFIDENCE"
    elif rule_count >= 3:
        signal = "MODERATE"
    elif rule_count >= 2:
        signal = "WEAK"
    else:
        signal = "NO_SIGNAL"

    return {
        "signal": signal,
        "triggered_rules": rules["triggered_rules"],
        "rule_details": rules["rule_details"],
        "rule_count": rule_count,
        "direction": "LONG",
    }


def generate_short_signal(df: pd.DataFrame, indicators: dict) -> dict:
    """
    SHORT signal rules (mirror of long):
    1. Trend = BEARISH
    2. Breakdown = BREAKDOWN or NEAR_BREAKDOWN
    3. Volume spike > 1.5x
    4. Closing strength < 35%
    5. ATR expanding

    Returns: signal dict with confidence level
    """
    rules = check_short_rules(indicators)
    rule_count = rules["rule_count"]

    if rule_count == 5:
        signal = "HIGH_CONFIDENCE"
    elif rule_count >= 4:
        signal = "HIGH_CONFIDENCE"
    elif rule_count >= 3:
        signal = "MODERATE"
    elif rule_count >= 2:
        signal = "WEAK"
    else:
        signal = "NO_SIGNAL"

    return {
        "signal": signal,
        "triggered_rules": rules["triggered_rules"],
        "rule_details": rules["rule_details"],
        "rule_count": rule_count,
        "direction": "SHORT",
    }


def generate_signals(df: pd.DataFrame, sector_etf_spike: float = None) -> dict:
    """
    Master function - computes all indicators and returns both long and short signals.
    Returns comprehensive dict with all indicator values and signals.
    """
    if df is None or len(df) < 50:
        return None

    try:
        # Compute indicators
        df = calculate_moving_averages(df)
        df = calculate_atr(df)
        df = calculate_rsi(df)

        last = df.iloc[-1]
        close = float(last["Close"])
        open_price = float(last["Open"])
        high = float(last["High"])
        low = float(last["Low"])
        volume = float(last["Volume"])

        # Get all indicator values
        trend_bias = get_trend_bias(df)
        market_structure = get_market_structure(df)
        breakout_info = get_breakout_status(df)
        breakout_status = breakout_info["status"]
        closing_strength = get_closing_strength(df)
        volume_spike = get_volume_spike(df)
        pv_alignment = get_price_volume_alignment(df)
        atr_expansion = get_atr_expansion(df)
        range_ratio = get_range_vs_historical(df)
        consol_breakout, consol_range = get_consolidation_breakout(df)

        # ATR value
        atr_val = float(df["ATR"].iloc[-1]) if not pd.isna(df["ATR"].iloc[-1]) else 0.0

        # Gap risk assessment
        # A stock with ATR ≥ 2% regularly sees overnight gaps > 1%, meaning the
        # next-day open will frequently blow straight through PDH+0.1% before the
        # market even opens — making the entry trigger stale from the bell.
        # ATR ≥ 1.5% is borderline (MEDIUM); below that the gap risk is LOW.
        atr_pct = (atr_val / close) if close > 0 else 0.0
        if atr_pct >= 0.02:
            gap_risk = "HIGH"    # 2%+ ATR — gap invalidation is routine
        elif atr_pct >= 0.015:
            gap_risk = "MEDIUM"  # 1.5-2% ATR — borderline, stay alert
        else:
            gap_risk = "LOW"     # < 1.5% ATR — gap unlikely to exceed 1%

        # MA values
        ma20 = float(df["MA20"].iloc[-1]) if not pd.isna(df["MA20"].iloc[-1]) else None
        ma50 = float(df["MA50"].iloc[-1]) if not pd.isna(df["MA50"].iloc[-1]) else None
        ma200 = float(df["MA200"].iloc[-1]) if not pd.isna(df["MA200"].iloc[-1]) else None

        # RSI
        rsi_raw = df["RSI"].iloc[-1] if "RSI" in df.columns else None
        rsi_val_display = round(float(rsi_raw), 1) if rsi_raw is not None and not pd.isna(rsi_raw) else None

        # Calculate scores
        trend_score = get_trend_score(df)
        breakout_score = get_breakout_score(df)
        volume_score = get_volume_score(df)
        volatility_score = get_volatility_score(df)
        rsi_score = get_rsi_score(df)

        # Assemble indicators dict
        indicators = {
            # Price data
            "close": round(close, 2),
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "volume": int(volume),
            # MAs
            "ma20": round(ma20, 2) if ma20 else None,
            "ma50": round(ma50, 2) if ma50 else None,
            "ma200": round(ma200, 2) if ma200 else None,
            # Trend
            "trend_bias": trend_bias,
            "market_structure": market_structure,
            # Breakout
            "breakout_status": breakout_status,
            "breakout_period": BREAKOUT_PERIOD,
            "resistance": breakout_info.get("resistance"),
            "support": breakout_info.get("support"),
            "breakout_level": breakout_info.get("breakout_level"),
            "breakdown_level": breakout_info.get("breakdown_level"),
            "consolidation_breakout": consol_breakout,
            # Volume
            "volume_spike": round(volume_spike, 2),
            "price_volume_alignment": pv_alignment,
            # Volatility
            "atr": round(atr_val, 2),
            "atr_expansion": round(atr_expansion, 2),
            "range_ratio": round(range_ratio, 2),
            # Closing strength
            "closing_strength": round(closing_strength, 1),
            # Gap risk
            "gap_risk": gap_risk,           # HIGH/MEDIUM/LOW — based on ATR%
            "atr_pct": round(atr_pct * 100, 2),  # ATR as % of close (for display)
            # RSI
            "rsi": rsi_val_display,
            # Sector ETF volume spike — used by signal rules to filter market-wide noise
            "sector_etf_spike": sector_etf_spike,
            # Component scores
            "trend_score": trend_score,
            "breakout_score": breakout_score,
            "volume_score": volume_score,
            "volatility_score": volatility_score,
            "rsi_score": rsi_score,
        }

        # Generate signals
        long_signal  = generate_long_signal(df, indicators)
        short_signal = generate_short_signal(df, indicators)

        # Gap-risk downgrade: HIGH ATR stocks routinely gap past PDH/PDL at open,
        # making the entry trigger stale before the market opens. Cap confidence at
        # MODERATE so these never appear as HIGH_CONFIDENCE setups in the scanner.
        if gap_risk == "HIGH":
            if long_signal["signal"] == "HIGH_CONFIDENCE":
                long_signal["signal"] = "MODERATE"
                long_signal["rule_details"].append(
                    f"[GAP RISK] ATR is {round(atr_pct*100,2)}% of price — PDH trigger "
                    f"likely blown through at open. Signal capped at MODERATE."
                )
            if short_signal["signal"] == "HIGH_CONFIDENCE":
                short_signal["signal"] = "MODERATE"
                short_signal["rule_details"].append(
                    f"[GAP RISK] ATR is {round(atr_pct*100,2)}% of price — PDL trigger "
                    f"likely blown through at open. Signal capped at MODERATE."
                )

        # RSI gate: suppress signals on exhausted moves.
        # A LONG into RSI ≥ 70 is chasing an overbought extension — institutions are
        # taking profit into the strength that triggered every other rule. A SHORT into
        # RSI ≤ 30 is pressing an already-oversold stock. Both are low-expectancy entries.
        # Any confidence level is suppressed to NO_SIGNAL so the setup never reaches
        # the scanner's HIGH_PROB or WATCHLIST buckets.
        if rsi_val_display is not None:
            if rsi_val_display >= RSI_OVERBOUGHT and long_signal["signal"] != "NO_SIGNAL":
                long_signal["signal"] = "NO_SIGNAL"
                long_signal["rule_details"].append(
                    f"[RSI GATE] RSI {rsi_val_display} ≥ {RSI_OVERBOUGHT} — move is overbought, "
                    f"institutional profit-taking likely. Long signal suppressed."
                )
            if rsi_val_display <= RSI_OVERSOLD and short_signal["signal"] != "NO_SIGNAL":
                short_signal["signal"] = "NO_SIGNAL"
                short_signal["rule_details"].append(
                    f"[RSI GATE] RSI {rsi_val_display} ≤ {RSI_OVERSOLD} — move is oversold, "
                    f"short-covering risk elevated. Short signal suppressed."
                )

        return {
            "indicators": indicators,
            "long_signal": long_signal,
            "short_signal": short_signal,
        }

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Signal generation error: {e}")
        return None
