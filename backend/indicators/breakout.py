"""
Breakout/Breakdown detection indicators
"""
import pandas as pd
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BREAKOUT_PERIOD, ATR_PERIOD


def get_breakout_status(df: pd.DataFrame, period: int = BREAKOUT_PERIOD) -> dict:
    """
    Returns: dict with status and key levels
    Status: 'BREAKOUT', 'BREAKDOWN', 'INSIDE', 'NEAR_BREAKOUT', 'NEAR_BREAKDOWN'
    BREAKOUT: close > highest high of last period days (excluding today)
    BREAKDOWN: close < lowest low of last period days
    NEAR_BREAKOUT: within 1% of the high
    NEAR_BREAKDOWN: within 1% of the low
    """
    if df is None or len(df) < period + 1:
        return {"status": "INSIDE", "resistance": None, "support": None, "breakout_level": None}

    today = df.iloc[-1]
    historical = df.iloc[-(period + 1):-1]

    close = float(today["Close"])
    period_high = float(historical["High"].max())
    period_low = float(historical["Low"].min())

    # Determine status
    if close > period_high:
        status = "BREAKOUT"
    elif close < period_low:
        status = "BREAKDOWN"
    elif close >= period_high * 0.99:  # Within 1% of high
        status = "NEAR_BREAKOUT"
    elif close <= period_low * 1.01:   # Within 1% of low
        status = "NEAR_BREAKDOWN"
    else:
        status = "INSIDE"

    return {
        "status": status,
        "resistance": round(period_high, 2),
        "support": round(period_low, 2),
        "breakout_level": round(period_high, 2),
        "breakdown_level": round(period_low, 2),
    }


def get_consolidation_breakout(df: pd.DataFrame, period: int = 10, atr_multiplier: float = 0.5) -> tuple:
    """
    Detect if stock broke out of consolidation.
    Consolidation: range < ATR * multiplier for N days.
    Returns: (is_breakout, consolidation_range)
    """
    if df is None or "ATR" not in df.columns or len(df) < period + ATR_PERIOD:
        return False, 0.0

    recent = df.iloc[-(period + 1):-1]
    atr = float(df["ATR"].iloc[-1]) if not pd.isna(df["ATR"].iloc[-1]) else 0

    if atr == 0:
        return False, 0.0

    # Check if the recent window was consolidating
    daily_ranges = recent["High"] - recent["Low"]
    avg_daily_range = float(daily_ranges.mean())
    consolidation_threshold = atr * atr_multiplier

    is_consolidating = avg_daily_range < consolidation_threshold

    # Check if today broke out
    today = df.iloc[-1]
    period_high = float(recent["High"].max())
    period_low = float(recent["Low"].min())
    close = float(today["Close"])

    broke_out = close > period_high or close < period_low

    consolidation_range = round(period_high - period_low, 2)

    return (is_consolidating and broke_out), consolidation_range


def get_closing_strength(df: pd.DataFrame) -> float:
    """
    Closing strength = (Close - Low) / (High - Low) * 100
    > 70% = strong close (bullish)
    < 30% = weak close (bearish)
    Returns: percentage (0-100)
    """
    if df is None or len(df) < 1:
        return 50.0

    today = df.iloc[-1]
    high = float(today["High"])
    low = float(today["Low"])
    close = float(today["Close"])

    if high == low:
        return 50.0

    strength = ((close - low) / (high - low)) * 100
    return round(strength, 2)


def get_breakout_score(df: pd.DataFrame) -> int:
    """Returns 0-25 score based on breakout status and closing strength"""
    if df is None or len(df) < BREAKOUT_PERIOD:
        return 0

    breakout_info = get_breakout_status(df)
    status = breakout_info["status"]
    closing_str = get_closing_strength(df)

    score = 0

    # Breakout status scoring (max 15 pts)
    if status == "BREAKOUT":
        score += 15
    elif status == "BREAKDOWN":
        score += 15  # Good for short
    elif status == "NEAR_BREAKOUT":
        score += 10
    elif status == "NEAR_BREAKDOWN":
        score += 10
    elif status == "INSIDE":
        score += 0

    # Closing strength scoring (max 10 pts)
    if closing_str >= 80:
        score += 10
    elif closing_str >= 70:
        score += 8
    elif closing_str >= 60:
        score += 6
    elif closing_str >= 50:
        score += 4
    elif closing_str >= 40:
        score += 2
    elif closing_str >= 30:
        score += 1
    # < 30 = weak close = 0 pts

    return min(score, 25)
