"""
NIFTY50 Directional Analysis Engine.

Computes technical indicators (MAs, ATR, VWAP, volume, breakout status,
market structure) and combines them with global sentiment to produce a
directional bias and expected move for the next trading session.
"""
import math
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def analyze_nifty(nifty_df: pd.DataFrame, global_sentiment: dict) -> dict:
    """
    Full NIFTY50 directional analysis.

    Args:
        nifty_df  : OHLCV DataFrame for ^NSEI (1-year history preferred).
        global_sentiment: Output from calculate_global_score().

    Returns:
        Dict with price data, indicators, trend bias, expected move,
        support/resistance levels.  Returns {"status": "error"} on failure.
    """
    if nifty_df is None or len(nifty_df) < 50:
        return {"status": "error", "error": "Insufficient NIFTY data (need ≥ 50 trading days)"}

    df = nifty_df.copy().sort_index()

    # ── Current & previous day ────────────────────────────────────────────────
    cur_close  = float(df["Close"].iloc[-1])
    cur_open   = float(df["Open"].iloc[-1])
    cur_high   = float(df["High"].iloc[-1])
    cur_low    = float(df["Low"].iloc[-1])

    pdh = float(df["High"].iloc[-2])
    pdl = float(df["Low"].iloc[-2])
    pdc = float(df["Close"].iloc[-2])

    change_pct = round((cur_close - pdc) / pdc * 100, 2) if pdc else 0.0

    # ── Moving averages ───────────────────────────────────────────────────────
    close = df["Close"]
    ma20  = float(close.rolling(20).mean().iloc[-1])
    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(min(200, len(df))).mean().iloc[-1])

    # ── ATR (14) ──────────────────────────────────────────────────────────────
    prev_close    = df["Close"].shift(1)
    tr            = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"]  - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr           = float(tr.rolling(14).mean().iloc[-1])
    atr_20_prev   = float(tr.rolling(20).mean().iloc[-2]) if len(df) > 21 else atr
    atr_expansion = round(atr / atr_20_prev, 2) if atr_20_prev > 0 else 1.0

    # ── 5-day VWAP (approximate, EOD) ────────────────────────────────────────
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    if "Volume" in df.columns:
        vol5 = df["Volume"].tail(5)
        if vol5.sum() > 0:
            vwap_5d = float((typical * df["Volume"]).tail(5).sum() / vol5.sum())
        else:
            vwap_5d = float(typical.tail(5).mean())
    else:
        vwap_5d = float(typical.tail(5).mean())

    # ── Historical volatility — 30-day annualised % ───────────────────────────
    daily_ret = df["Close"].pct_change()
    hv_30     = float(daily_ret.tail(30).std() * math.sqrt(252) * 100)
    hv_30     = round(max(5.0, hv_30), 2)   # floor at 5 %

    # ── Volume spike ──────────────────────────────────────────────────────────
    if "Volume" in df.columns and len(df) > 21:
        vol_avg20 = float(df["Volume"].tail(21).iloc[:-1].mean())
        cur_vol   = float(df["Volume"].iloc[-1])
        vol_spike = round(cur_vol / vol_avg20, 2) if vol_avg20 > 0 else 1.0
    else:
        vol_spike = 1.0

    # ── 20-day high / low (excluding today) ───────────────────────────────────
    high20 = float(df["High"].tail(21).iloc[:-1].max())
    low20  = float(df["Low"].tail(21).iloc[:-1].min())

    # ── Breakout status ───────────────────────────────────────────────────────
    if cur_close > pdh:
        breakout_status = "BREAKOUT_ABOVE_PDH"
    elif cur_close < pdl:
        breakout_status = "BREAKDOWN_BELOW_PDL"
    elif cur_close > high20:
        breakout_status = "20D_BREAKOUT"
    elif cur_close < low20:
        breakout_status = "20D_BREAKDOWN"
    elif cur_close >= pdh * 0.998:
        breakout_status = "NEAR_PDH"
    elif cur_close <= pdl * 1.002:
        breakout_status = "NEAR_PDL"
    else:
        breakout_status = "INSIDE_RANGE"

    # ── Closing strength (0–100 %) ────────────────────────────────────────────
    day_range        = cur_high - cur_low
    closing_strength = round((cur_close - cur_low) / day_range * 100, 1) if day_range > 0 else 50.0

    # ── 3-day market structure ────────────────────────────────────────────────
    h = [float(df["High"].iloc[-i]) for i in range(1, 4)]
    lo = [float(df["Low"].iloc[-i])  for i in range(1, 4)]
    if h[0] > h[1] > h[2] and lo[0] > lo[1] > lo[2]:
        market_structure = "HH_HL"
    elif h[0] < h[1] < h[2] and lo[0] < lo[1] < lo[2]:
        market_structure = "LH_LL"
    else:
        market_structure = "MIXED"

    # ── Trend score & bias ────────────────────────────────────────────────────
    ts = 0  # trend score accumulator

    if cur_close > ma20 > ma50 > ma200:
        ts += 3;  ma_alignment = "STRONG_BULLISH"
    elif cur_close > ma20 > ma50:
        ts += 2;  ma_alignment = "BULLISH"
    elif cur_close > ma20:
        ts += 1;  ma_alignment = "MILDLY_BULLISH"
    elif cur_close < ma20 < ma50 < ma200:
        ts -= 3;  ma_alignment = "STRONG_BEARISH"
    elif cur_close < ma20 < ma50:
        ts -= 2;  ma_alignment = "BEARISH"
    elif cur_close < ma20:
        ts -= 1;  ma_alignment = "MILDLY_BEARISH"
    else:
        ma_alignment = "NEUTRAL"

    # PDH/PDL position
    if cur_close > pdh:
        ts += 2
    elif cur_close < pdl:
        ts -= 2

    # Volume alignment
    if vol_spike >= 1.5:
        ts += 1 if cur_close > pdc else -1

    # Market structure
    if market_structure == "HH_HL":
        ts += 1
    elif market_structure == "LH_LL":
        ts -= 1

    if ts >= 4:
        trend_bias = "STRONG_BULLISH"
    elif ts >= 2:
        trend_bias = "BULLISH"
    elif ts <= -4:
        trend_bias = "STRONG_BEARISH"
    elif ts <= -2:
        trend_bias = "BEARISH"
    else:
        trend_bias = "NEUTRAL"

    # ── Global sentiment integration ─────────────────────────────────────────
    gs_score = global_sentiment.get("score", 0)
    gs_class = global_sentiment.get("classification", "NEUTRAL")

    fs = ts  # final score
    if gs_class in ("STRONG_BULLISH", "MILD_BULLISH"):
        fs += 1
    elif gs_class in ("STRONG_BEARISH", "MILD_BEARISH"):
        fs -= 1

    if fs >= 4:
        expected_move = "STRONG_BULLISH"
    elif fs >= 2:
        expected_move = "BULLISH"
    elif fs <= -4:
        expected_move = "STRONG_BEARISH"
    elif fs <= -2:
        expected_move = "BEARISH"
    else:
        expected_move = "NEUTRAL"

    # ── Support / Resistance ──────────────────────────────────────────────────
    support1    = round(pdl, 2)
    support2    = round(pdl - atr * 0.5, 2)
    resistance1 = round(pdh, 2)
    resistance2 = round(pdh + atr * 0.5, 2)

    # Expected next-day range (ATR-based)
    expected_high = round(cur_close + atr * 0.8, 2)
    expected_low  = round(cur_close - atr * 0.8, 2)

    return {
        "status": "ok",
        # Price data
        "current_price":     round(cur_close, 2),
        "current_open":      round(cur_open, 2),
        "current_high":      round(cur_high, 2),
        "current_low":       round(cur_low, 2),
        "prev_close":        round(pdc, 2),
        "change_pct":        change_pct,
        # Key levels
        "pdh":               round(pdh, 2),
        "pdl":               round(pdl, 2),
        "vwap_5d":           round(vwap_5d, 2),
        "ma20":              round(ma20, 2),
        "ma50":              round(ma50, 2),
        "ma200":             round(ma200, 2),
        # Volatility
        "atr":               round(atr, 2),
        "atr_expansion":     atr_expansion,
        "hv_30":             hv_30,
        # Volume
        "volume_spike":      vol_spike,
        # Signals
        "breakout_status":   breakout_status,
        "closing_strength":  closing_strength,
        "ma_alignment":      ma_alignment,
        "market_structure":  market_structure,
        "trend_bias":        trend_bias,
        "trend_score":       ts,
        "expected_move":     expected_move,
        # Sentiment
        "global_sentiment_score": gs_score,
        "global_sentiment":       gs_class,
        # Levels
        "support1":     support1,
        "support2":     support2,
        "resistance1":  resistance1,
        "resistance2":  resistance2,
        "expected_high": expected_high,
        "expected_low":  expected_low,
    }
