"""
Volatility indicators: ATR, Range Expansion
"""
import pandas as pd
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import ATR_PERIOD, VOLUME_LOOKBACK


def calculate_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.DataFrame:
    """Add ATR column to df using proper True Range calculation"""
    df = df.copy()
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    df["TR"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = df["TR"].rolling(window=period).mean()

    return df


def get_atr_expansion(df: pd.DataFrame, period: int = ATR_PERIOD, lookback: int = VOLUME_LOOKBACK) -> float:
    """
    Returns: expansion_ratio (current ATR / avg ATR over lookback)
    > 1.5 = expanding, < 0.7 = contracting
    """
    if df is None or "ATR" not in df.columns or len(df) < lookback + period:
        return 1.0

    current_atr = df["ATR"].iloc[-1]
    avg_atr = df["ATR"].iloc[-(lookback + 1):-1].mean()

    if pd.isna(current_atr) or pd.isna(avg_atr) or avg_atr == 0:
        return 1.0

    return round(float(current_atr) / float(avg_atr), 3)


def get_range_vs_historical(df: pd.DataFrame, lookback: int = VOLUME_LOOKBACK) -> float:
    """
    Returns: ratio of today's range to average range over lookback
    """
    if df is None or len(df) < lookback + 1:
        return 1.0

    today_range = float(df["High"].iloc[-1]) - float(df["Low"].iloc[-1])
    hist_range = (df["High"] - df["Low"]).iloc[-(lookback + 1):-1].mean()

    if pd.isna(hist_range) or hist_range == 0:
        return 1.0

    return round(today_range / float(hist_range), 3)


def get_volatility_score(df: pd.DataFrame) -> int:
    """Returns 0-15 score. Higher when ATR expanding (means momentum)"""
    if df is None or "ATR" not in df.columns:
        return 0

    expansion_ratio = get_atr_expansion(df)
    range_ratio = get_range_vs_historical(df)

    score = 0

    # ATR expansion component (max 10 pts)
    if expansion_ratio >= 2.0:
        score += 10
    elif expansion_ratio >= 1.5:
        score += 8
    elif expansion_ratio >= 1.2:
        score += 6
    elif expansion_ratio >= 1.0:
        score += 4
    elif expansion_ratio >= 0.8:
        score += 2
    # < 0.7 = contracting = 0 pts

    # Range vs historical (max 5 pts)
    if range_ratio >= 1.5:
        score += 5
    elif range_ratio >= 1.2:
        score += 3
    elif range_ratio >= 0.9:
        score += 2
    else:
        score += 1

    return min(score, 15)
