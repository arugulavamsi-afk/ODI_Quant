"""
Risk management engine.
Realistic intraday day-trading levels based on Previous Day High/Low and ATR.

Strategy:
  LONG  — Enter on break above PDH. SL capped at 0.75% below entry.
  SHORT — Enter on break below PDL. SL capped at 0.75% above entry.

Targets are intraday-realistic (stocks typically move ~half their daily ATR in one direction):
  T1 = 0.5× ATR  → book 40%, move SL to breakeven  (~0.5–1% move)
  T2 = 1.0× ATR  → book 40%                         (~1–2% move)
  T3 = 1.5× ATR  → trail remainder, capped at 2.5%  (stretch target)

SL bounds:
  Min SL = 0.3% of entry (avoid noise stop-outs)
  Max SL = 0.75% of entry (keeps risk tight for intraday)
"""
import pandas as pd
import numpy as np

# Intraday SL caps (% of entry price)
_SL_MIN_PCT  = 0.003   # 0.3% — floor so SL isn't trivially tight
_SL_MAX_PCT  = 0.0075  # 0.75% — ceiling so stop isn't unrealistically wide
_T3_MAX_PCT  = 0.025   # 2.5% — hard cap on T3 (rarely exceeded intraday)


def calculate_trade_levels(df: pd.DataFrame, direction: str, atr_value: float = None, atr_multiplier: float = 1.5) -> dict:
    if df is None or len(df) < 5:
        return {}

    try:
        last = df.iloc[-1]
        close = float(last["Close"])
        pdh   = float(last["High"])   # Previous session high
        pdl   = float(last["Low"])    # Previous session low

        # Resolve ATR (14-day daily ATR)
        if "ATR" in df.columns and not pd.isna(df["ATR"].iloc[-1]):
            atr = float(df["ATR"].iloc[-1])
        elif atr_value and atr_value > 0:
            atr = float(atr_value)
        else:
            atr = close * 0.015  # 1.5% fallback

        direction = direction.upper()

        if direction == "LONG":
            # Entry trigger: just above PDH (0.1% buffer to avoid false break)
            entry_trigger = round(pdh * 1.001, 2)

            # SL: PDL-based, but clamped to [0.3%, 0.75%] of entry
            pdl_sl    = round(pdl * 0.999, 2)
            pdl_risk  = entry_trigger - pdl_sl
            sl_max    = entry_trigger * _SL_MAX_PCT
            sl_min    = entry_trigger * _SL_MIN_PCT
            if pdl_risk <= sl_max:
                raw_sl   = pdl_sl
                sl_basis = f"PDL ₹{pdl:.2f}"
            else:
                raw_sl   = entry_trigger - sl_max
                sl_basis = f"0.75% cap (PDL too far)"
            stop_loss = round(max(raw_sl, entry_trigger - sl_max), 2)
            stop_loss = round(min(stop_loss, entry_trigger - sl_min), 2)

            sl_distance = round(entry_trigger - stop_loss, 2)

            # Intraday targets: 0.5×/1×/1.5× ATR, T3 hard-capped at 2.5%
            t3_atr  = entry_trigger + 1.5 * atr
            t3_cap  = entry_trigger * (1 + _T3_MAX_PCT)
            target1 = round(entry_trigger + 0.5 * atr, 2)
            target2 = round(entry_trigger + 1.0 * atr, 2)
            target3 = round(min(t3_atr, t3_cap), 2)

            setup_note = (
                f"Enter on break above PDH ₹{pdh:.2f} → trigger ₹{entry_trigger:.2f}. "
                f"SL {sl_basis} (risk {round(sl_distance/entry_trigger*100,2)}%). "
                f"Book 40% at T1, move SL to breakeven. Book 40% at T2. Trail rest to T3."
            )

        else:  # SHORT
            # Entry trigger: just below PDL
            entry_trigger = round(pdl * 0.999, 2)

            # SL: PDH-based, but clamped to [0.3%, 0.75%] of entry
            pdh_sl   = round(pdh * 1.001, 2)
            pdh_risk = pdh_sl - entry_trigger
            sl_max   = entry_trigger * _SL_MAX_PCT
            sl_min   = entry_trigger * _SL_MIN_PCT
            if pdh_risk <= sl_max:
                raw_sl   = pdh_sl
                sl_basis = f"PDH ₹{pdh:.2f}"
            else:
                raw_sl   = entry_trigger + sl_max
                sl_basis = f"0.75% cap (PDH too far)"
            stop_loss = round(min(raw_sl, entry_trigger + sl_max), 2)
            stop_loss = round(max(stop_loss, entry_trigger + sl_min), 2)

            sl_distance = round(stop_loss - entry_trigger, 2)

            t3_atr  = entry_trigger - 1.5 * atr
            t3_cap  = entry_trigger * (1 - _T3_MAX_PCT)
            target1 = round(entry_trigger - 0.5 * atr, 2)
            target2 = round(entry_trigger - 1.0 * atr, 2)
            target3 = round(max(t3_atr, t3_cap), 2)

            setup_note = (
                f"Enter on break below PDL ₹{pdl:.2f} → trigger ₹{entry_trigger:.2f}. "
                f"SL {sl_basis} (risk {round(sl_distance/entry_trigger*100,2)}%). "
                f"Book 40% at T1, move SL to breakeven. Book 40% at T2. Trail rest to T3."
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
