"""
Volume indicators: Volume Spike, Price-Volume Alignment
"""
import pandas as pd
import numpy as np
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import VOLUME_LOOKBACK, MIN_VOLUME


def get_volume_spike(df: pd.DataFrame, lookback: int = VOLUME_LOOKBACK) -> float:
    """
    Returns: ratio of today's volume to 20-day avg volume
    > 2.0 = strong spike, > 1.5 = moderate, < 0.8 = low
    """
    if df is None or "Volume" not in df.columns or len(df) < lookback + 1:
        return 1.0

    today_vol = float(df["Volume"].iloc[-1])
    avg_vol = df["Volume"].iloc[-(lookback + 1):-1].mean()

    if pd.isna(avg_vol) or avg_vol == 0:
        return 1.0

    return round(today_vol / float(avg_vol), 3)


def get_price_volume_alignment(df: pd.DataFrame) -> str:
    """
    Returns: 'BULLISH', 'BEARISH', 'NEUTRAL'
    BULLISH: price up + volume up (strong accumulation)
    BEARISH: price down + volume up (strong distribution)
    NEUTRAL: price move + volume down (weak move)
    """
    if df is None or len(df) < 2:
        return "NEUTRAL"

    today = df.iloc[-1]
    yesterday = df.iloc[-2]

    price_change = today["Close"] - yesterday["Close"]
    vol_change = today["Volume"] - yesterday["Volume"]

    price_up = price_change > 0
    vol_up = vol_change > 0

    if price_up and vol_up:
        return "BULLISH"
    elif not price_up and vol_up:
        return "BEARISH"
    else:
        return "NEUTRAL"


def is_genuine_volume_spike(stock_spike: float, sector_etf_spike: float | None) -> bool:
    """
    Returns True when the stock's volume spike is genuinely stock-specific rather
    than sector/market-wide noise.

    Logic:
      - No ETF data (sector_etf_spike is None) → treat as genuine (can't filter, don't penalise)
      - Sector ETF spike < 1.3  → sector volume is normal; any stock spike is real
      - Stock spike > sector_etf_spike × 1.2  → stock is meaningfully above sector noise
        (requires 20% more volume than the sector uplift to be considered genuine)

    Typical noise cases this catches:
      F&O expiry day:  sector_etf_spike = 2.0, stock_spike = 1.8 → not genuine (1.8 < 2.0×1.2=2.4)
      Post-holiday:    sector_etf_spike = 1.6, stock_spike = 1.7 → not genuine (1.7 < 1.6×1.2=1.92)
      Index rebal:     sector_etf_spike = 1.5, stock_spike = 2.4 → genuine (2.4 > 1.5×1.2=1.8)
    """
    if sector_etf_spike is None:
        return True  # no ETF data — can't filter, assume genuine
    if sector_etf_spike < 1.3:
        return True  # sector volume is normal, any stock spike is real
    return stock_spike > sector_etf_spike * 1.2


def get_volume_score(df: pd.DataFrame) -> int:
    """Returns 0-20 score based on volume spike and alignment"""
    if df is None or len(df) < 2:
        return 0

    spike = get_volume_spike(df)
    alignment = get_price_volume_alignment(df)

    score = 0

    # Volume spike component (max 12 pts)
    if spike >= 3.0:
        score += 12
    elif spike >= 2.0:
        score += 10
    elif spike >= 1.5:
        score += 7
    elif spike >= 1.2:
        score += 5
    elif spike >= 0.8:
        score += 3
    else:
        score += 0  # Very low volume = no score

    # Price-volume alignment (max 8 pts)
    if alignment == "BULLISH":
        score += 8
    elif alignment == "BEARISH":
        score += 8  # Also strong signal (for short)
    elif alignment == "NEUTRAL":
        score += 2

    return min(score, 20)
