"""
Risk management engine.
Calculates stop loss, targets, and position sizing.
"""
import pandas as pd
import numpy as np


def calculate_trade_levels(df: pd.DataFrame, direction: str, atr_multiplier: float = 1.5) -> dict:
    """
    Calculates trade entry, SL, and targets based on ATR.

    Entry: current close

    LONG:
    - Stop Loss: Close - (ATR * 1.5) OR below recent swing low (whichever is tighter but > 0.5 ATR away)
    - Target 1: Close + (SL_distance * 2)   # 2:1 RR
    - Target 2: Close + (SL_distance * 3)   # 3:1 RR

    SHORT:
    - Stop Loss: Close + (ATR * 1.5)
    - Target 1: Close - (SL_distance * 2)
    - Target 2: Close - (SL_distance * 3)

    Returns: trade levels dict
    """
    if df is None or "ATR" not in df.columns or len(df) < 5:
        return {}

    try:
        last = df.iloc[-1]
        close = float(last["Close"])
        atr = float(df["ATR"].iloc[-1])

        if pd.isna(atr) or atr == 0:
            # Fallback: use 2% of price as ATR estimate
            atr = close * 0.02

        direction = direction.upper()

        if direction == "LONG":
            # ATR-based SL
            atr_sl = close - (atr * atr_multiplier)

            # Swing low-based SL (look at last 5 bars)
            recent_lows = df["Low"].iloc[-6:-1]
            swing_low = float(recent_lows.min()) if len(recent_lows) > 0 else atr_sl

            # Use swing low if it's between atr_sl and (close - 0.5*atr)
            min_sl_distance = atr * 0.5
            if swing_low < close - min_sl_distance and swing_low > atr_sl:
                stop_loss = swing_low
            else:
                stop_loss = atr_sl

            # Ensure SL is at least 0.5 ATR below entry
            if close - stop_loss < atr * 0.5:
                stop_loss = close - (atr * 0.5)

            sl_distance = close - stop_loss
            target1 = close + (sl_distance * 2)
            target2 = close + (sl_distance * 3)

        else:  # SHORT
            # ATR-based SL
            atr_sl = close + (atr * atr_multiplier)

            # Swing high-based SL
            recent_highs = df["High"].iloc[-6:-1]
            swing_high = float(recent_highs.max()) if len(recent_highs) > 0 else atr_sl

            # Use swing high if it's between (close + 0.5*atr) and atr_sl
            min_sl_distance = atr * 0.5
            if swing_high > close + min_sl_distance and swing_high < atr_sl:
                stop_loss = swing_high
            else:
                stop_loss = atr_sl

            # Ensure SL is at least 0.5 ATR above entry
            if stop_loss - close < atr * 0.5:
                stop_loss = close + (atr * 0.5)

            sl_distance = stop_loss - close
            target1 = close - (sl_distance * 2)
            target2 = close - (sl_distance * 3)

        # Risk percentage
        risk_pct = (sl_distance / close) * 100

        # RR ratio
        rr_ratio = 2.0  # Fixed at 2:1

        # Position size for 1 lakh (100,000 INR) risk
        risk_per_share = sl_distance
        if risk_per_share > 0:
            position_size_1l = int(100000 / risk_per_share)
        else:
            position_size_1l = 0

        return {
            "entry": round(close, 2),
            "stop_loss": round(stop_loss, 2),
            "target1": round(target1, 2),
            "target2": round(target2, 2),
            "risk_pct": round(risk_pct, 2),
            "sl_distance": round(sl_distance, 2),
            "rr_ratio": rr_ratio,
            "position_size_1L": position_size_1l,
            "atr_used": round(atr, 2),
        }

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Risk calculation error: {e}")
        return {}
