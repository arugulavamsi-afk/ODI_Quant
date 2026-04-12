"""
Trend indicators: Moving Averages, Market Structure
"""
import pandas as pd
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MA_SHORT, MA_MEDIUM, MA_LONG

RSI_PERIOD = 14
RSI_OVERBOUGHT = 70   # LONG gate: RSI must be below this
RSI_OVERSOLD   = 30   # SHORT gate: RSI must be above this
RSI_HEALTHY_HI = 65   # Upper bound of the healthy momentum zone (longs)
RSI_HEALTHY_LO = 40   # Lower bound


def calculate_rsi(df: pd.DataFrame, period: int = RSI_PERIOD) -> pd.DataFrame:
    """Add RSI column to df using Wilder's EMA smoothing (same formula as intra_contra)."""
    df = df.copy()
    delta = df["Close"].diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI"] = 100 - 100 / (1 + rs)
    return df


def get_rsi_score(df: pd.DataFrame) -> int:
    """
    Returns 0-10 RSI momentum score — rewards healthy momentum, penalises extremes.

    This measures something the four component scores do NOT already capture:
    whether the move has room left to run.

    Scoring:
      RSI 40-65  → +10  (rising from mid-range — early-stage momentum, room to run)
      RSI 65-70  → +5   (extended but not yet overbought)
      RSI 30-40  → +3   (recovering from oversold — possible longs, lower conviction)
      RSI ≥ 70   → 0    (overbought — gate will suppress signal anyway)
      RSI ≤ 30   → 0    (oversold — gate will suppress short signal anyway)
      No RSI     → 0
    """
    if df is None or "RSI" not in df.columns:
        return 0
    rsi_raw = df["RSI"].iloc[-1]
    if pd.isna(rsi_raw):
        return 0
    rsi = float(rsi_raw)
    if RSI_HEALTHY_LO <= rsi <= RSI_HEALTHY_HI:
        return 10
    elif RSI_HEALTHY_HI < rsi < RSI_OVERBOUGHT:
        return 5
    elif RSI_OVERSOLD < rsi < RSI_HEALTHY_LO:
        return 3
    return 0  # overbought (≥70) or oversold (≤30)


def calculate_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Add MA20, MA50, MA200 columns to df"""
    df = df.copy()
    df["MA20"] = df["Close"].rolling(window=MA_SHORT).mean()
    df["MA50"] = df["Close"].rolling(window=MA_MEDIUM).mean()
    df["MA200"] = df["Close"].rolling(window=MA_LONG).mean()
    return df


def get_trend_bias(df: pd.DataFrame) -> str:
    """
    Returns: 'BULLISH', 'BEARISH', 'NEUTRAL'
    Logic:
    - BULLISH: Close > MA20 > MA50 AND MA50 > MA200 (strong) OR Close > MA20 > MA50 (moderate)
    - BEARISH: Close < MA20 < MA50 AND MA50 < MA200 (strong) OR Close < MA20 < MA50 (moderate)
    - NEUTRAL: otherwise
    """
    if df is None or len(df) < MA_LONG:
        return "NEUTRAL"

    last = df.iloc[-1]
    close = last.get("Close", None)
    ma20 = last.get("MA20", None)
    ma50 = last.get("MA50", None)
    ma200 = last.get("MA200", None)

    if any(pd.isna(v) for v in [close, ma20, ma50, ma200]):
        # Try without MA200
        if not pd.isna(close) and not pd.isna(ma20) and not pd.isna(ma50):
            if close > ma20 > ma50:
                return "BULLISH"
            elif close < ma20 < ma50:
                return "BEARISH"
        return "NEUTRAL"

    # Strong bullish: price > MA20 > MA50 > MA200
    if close > ma20 and ma20 > ma50 and ma50 > ma200:
        return "BULLISH"
    # Strong bearish
    elif close < ma20 and ma20 < ma50 and ma50 < ma200:
        return "BEARISH"
    # Moderate bullish: price > MA20 > MA50
    elif close > ma20 and ma20 > ma50:
        return "BULLISH"
    # Moderate bearish
    elif close < ma20 and ma20 < ma50:
        return "BEARISH"
    else:
        return "NEUTRAL"


def get_market_structure(df: pd.DataFrame, lookback: int = 10) -> str:
    """
    Returns: 'HH_HL' (bullish structure), 'LH_LL' (bearish), 'MIXED'
    Checks last 3 swing highs/lows using local extrema.
    """
    if df is None or len(df) < lookback * 2:
        return "MIXED"

    recent = df.tail(lookback * 3).copy()
    highs = recent["High"].values
    lows = recent["Low"].values

    # Find local highs (pivot highs)
    pivot_highs = []
    pivot_lows = []

    window = 3
    for i in range(window, len(highs) - window):
        if highs[i] == max(highs[i - window:i + window + 1]):
            pivot_highs.append(highs[i])
        if lows[i] == min(lows[i - window:i + window + 1]):
            pivot_lows.append(lows[i])

    if len(pivot_highs) >= 2 and len(pivot_lows) >= 2:
        # Check last 2 highs and lows
        last_highs = pivot_highs[-2:]
        last_lows = pivot_lows[-2:]

        hh = last_highs[-1] > last_highs[-2]  # Higher High
        hl = last_lows[-1] > last_lows[-2]    # Higher Low
        lh = last_highs[-1] < last_highs[-2]  # Lower High
        ll = last_lows[-1] < last_lows[-2]    # Lower Low

        if hh and hl:
            return "HH_HL"
        elif lh and ll:
            return "LH_LL"

    return "MIXED"


def get_trend_score(df: pd.DataFrame) -> int:
    """Returns 0-25 score based on trend strength"""
    score = 0

    if df is None or len(df) < MA_MEDIUM:
        return 0

    last = df.iloc[-1]
    close = last.get("Close", None)
    ma20 = last.get("MA20", None)
    ma50 = last.get("MA50", None)
    ma200 = last.get("MA200", None)

    if pd.isna(close):
        return 0

    # MA alignment scoring (max 15 pts)
    if not pd.isna(ma20) and not pd.isna(ma50) and not pd.isna(ma200):
        if close > ma20 and ma20 > ma50 and ma50 > ma200:
            score += 15  # Perfect bullish alignment
        elif close > ma20 and ma20 > ma50:
            score += 10  # Moderate bullish
        elif close > ma50:
            score += 5   # Above medium MA
        elif close < ma20 and ma20 < ma50 and ma50 < ma200:
            score += 15  # Perfect bearish alignment (for short scoring)
        elif close < ma20 and ma20 < ma50:
            score += 10
        elif close < ma50:
            score += 5
    elif not pd.isna(ma20) and not pd.isna(ma50):
        if close > ma20 and ma20 > ma50:
            score += 10
        elif close < ma20 and ma20 < ma50:
            score += 10

    # Market structure scoring (max 10 pts)
    structure = get_market_structure(df)
    if structure == "HH_HL":
        score += 10
    elif structure == "LH_LL":
        score += 10  # Good for short
    elif structure == "MIXED":
        score += 0  # No identifiable swing structure = no contribution

    return min(score, 25)
