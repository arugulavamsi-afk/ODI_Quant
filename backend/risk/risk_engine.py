"""
Risk management engine.
Professional day-trading levels based on Previous Day High/Low and ATR.

Strategy:
  LONG  — Enter on break above PDH. SL below PDL (or ATR-based if range too wide).
  SHORT — Enter on break below PDL. SL above PDH (or ATR-based if range too wide).

Targets use ATR multiples (intraday realistic moves):
  T1 = 1× ATR  → book 50%, move SL to breakeven
  T2 = 2× ATR  → book 30%
  T3 = 3× ATR  → trail remainder
"""
import pandas as pd
import numpy as np


def calculate_trade_levels(df: pd.DataFrame, direction: str, atr_value: float = None, atr_multiplier: float = 1.5) -> dict:
    if df is None or len(df) < 5:
        return {}

    try:
        last = df.iloc[-1]
        close = float(last["Close"])
        pdh   = float(last["High"])   # Previous session high
        pdl   = float(last["Low"])    # Previous session low

        # Resolve ATR
        if "ATR" in df.columns and not pd.isna(df["ATR"].iloc[-1]):
            atr = float(df["ATR"].iloc[-1])
        elif atr_value and atr_value > 0:
            atr = float(atr_value)
        else:
            atr = close * 0.02  # 2% fallback

        direction = direction.upper()

        if direction == "LONG":
            # Entry trigger: just above PDH (0.1% buffer to avoid false break)
            entry_trigger = round(pdh * 1.001, 2)

            # SL: just below PDL — if the range is too wide (>2×ATR), tighten to 0.75×ATR below entry
            pdl_sl = round(pdl * 0.999, 2)
            pdl_risk = entry_trigger - pdl_sl
            if pdl_risk <= 2.0 * atr:
                stop_loss = pdl_sl
                sl_basis  = f"PDL ₹{pdl:.2f}"
            else:
                stop_loss = round(entry_trigger - 0.75 * atr, 2)
                sl_basis  = f"ATR-based (PDL too wide)"

            sl_distance = entry_trigger - stop_loss
            target1 = round(entry_trigger + 1.0 * atr, 2)
            target2 = round(entry_trigger + 2.0 * atr, 2)
            target3 = round(entry_trigger + 3.0 * atr, 2)
            setup_note = (
                f"Enter on break above PDH ₹{pdh:.2f} → trigger ₹{entry_trigger:.2f}. "
                f"SL below {sl_basis}. "
                f"Book 50% at T1, move SL to breakeven. Book 30% at T2. Trail rest to T3."
            )

        else:  # SHORT
            # Entry trigger: just below PDL
            entry_trigger = round(pdl * 0.999, 2)

            # SL: just above PDH — tighten if range >2×ATR
            pdh_sl = round(pdh * 1.001, 2)
            pdh_risk = pdh_sl - entry_trigger
            if pdh_risk <= 2.0 * atr:
                stop_loss = pdh_sl
                sl_basis  = f"PDH ₹{pdh:.2f}"
            else:
                stop_loss = round(entry_trigger + 0.75 * atr, 2)
                sl_basis  = f"ATR-based (PDH too wide)"

            sl_distance = stop_loss - entry_trigger
            target1 = round(entry_trigger - 1.0 * atr, 2)
            target2 = round(entry_trigger - 2.0 * atr, 2)
            target3 = round(entry_trigger - 3.0 * atr, 2)
            setup_note = (
                f"Enter on break below PDL ₹{pdl:.2f} → trigger ₹{entry_trigger:.2f}. "
                f"SL above {sl_basis}. "
                f"Book 50% at T1, move SL to breakeven. Book 30% at T2. Trail rest to T3."
            )

        risk_pct    = round((sl_distance / entry_trigger) * 100, 2)
        rr_t1       = round(abs(target1 - entry_trigger) / sl_distance, 2) if sl_distance > 0 else 0
        rr_t2       = round(abs(target2 - entry_trigger) / sl_distance, 2) if sl_distance > 0 else 0
        rr_t3       = round(abs(target3 - entry_trigger) / sl_distance, 2) if sl_distance > 0 else 0
        pos_size_1l = int(100000 / sl_distance) if sl_distance > 0 else 0

        return {
            "entry":          round(close, 2),          # reference (prev close)
            "entry_trigger":  entry_trigger,             # actual entry level
            "stop_loss":      stop_loss,
            "target1":        target1,
            "target2":        target2,
            "target3":        target3,
            "risk_pct":       risk_pct,
            "sl_distance":    round(sl_distance, 2),
            "rr_t1":          rr_t1,
            "rr_t2":          rr_t2,
            "rr_t3":          rr_t3,
            "position_size_1L": pos_size_1l,
            "atr_used":       round(atr, 2),
            "prev_day_high":  round(pdh, 2),
            "prev_day_low":   round(pdl, 2),
            "setup_note":     setup_note,
        }

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Risk calculation error: {e}")
        return {}
