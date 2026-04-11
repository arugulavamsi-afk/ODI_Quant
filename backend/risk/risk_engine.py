"""
Risk management engine.
Realistic intraday day-trading levels based on Previous Day High/Low and ATR.

Strategy:
  LONG  — Enter on break above PDH. SL is always the true PDL-based level.
  SHORT — Enter on break below PDL. SL is always the true PDH-based level.

SL is NEVER artificially tightened. Setups where the natural SL is too wide
(> _SL_FILTER_PCT) are flagged via `sl_too_wide=True` so the scanner can
skip them rather than fake a tighter stop and mis-size the position.

Targets are intraday-realistic (stocks typically move ~half their daily ATR in one direction):
  T1 = 0.5× ATR  → book 40%, move SL to breakeven  (~0.5–1% move)
  T2 = 1.0× ATR  → book 40%                         (~1–2% move)
  T3 = 1.5× ATR  → trail remainder, capped at 2.5%  (stretch target)

SL bounds:
  Min SL  = 0.3% of entry  — floor so SL isn't trivially tight (noise protection)
  Filter  = 2.0% of entry  — setups wider than this are flagged sl_too_wide=True

Slippage model:
  Entry slippage  = 0.20% of trigger — market/stop order through a live breakout
  Exit slippage   = 0.10% per target — limit order, partial-fill risk at target
  All RR ratios and position sizing use the slippage-adjusted fill price so that
  what the UI shows matches realistic P&L, not a clean-data idealisation.
  T1 is flagged `t1_too_close=True` when net gain after entry+exit slippage
  is < 0.5% of fill — not worth booking at that level.

Position sizing:
  Sized from ACCOUNT_CAPITAL (config.py) × RISK_PER_TRADE_PCT, not a fixed ₹1L.
  The function also accepts a `capital` override for per-call customisation.
  Three risk tiers (0.5%, 1%, 2% of capital) are returned so the trader can
  choose their own exposure. `capital_risk_pct` shows what % of the configured
  capital is actually risked by the recommended (1%) position.
"""
import pandas as pd
import numpy as np
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config import ACCOUNT_CAPITAL, RISK_PER_TRADE_PCT, RISK_WARNING_PCT
except ImportError:
    ACCOUNT_CAPITAL    = 500_000   # fallback if config unavailable
    RISK_PER_TRADE_PCT = 1.0
    RISK_WARNING_PCT   = 2.0

_SL_MIN_PCT         = 0.003   # 0.3%  — floor so SL isn't inside tick noise
_SL_FILTER_PCT      = 0.02    # 2.0%  — flag (not cap) for setups with wide natural SL
_T3_MAX_PCT         = 0.025   # 2.5%  — hard cap on T3 (rarely exceeded intraday)
_ENTRY_SLIPPAGE_PCT = 0.002   # 0.2%  — market order through a momentum breakout
_EXIT_SLIPPAGE_PCT  = 0.001   # 0.1%  — limit order per target (partial-fill risk)
_MIN_T1_NET_PCT     = 0.005   # 0.5%  — minimum net gain at T1 to be worth booking


def calculate_trade_levels(df: pd.DataFrame, direction: str, atr_value: float = None,
                           atr_multiplier: float = 1.5, capital: float = None) -> dict:
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

            # SL: always the true PDL-based level — never artificially tightened.
            # If the natural SL is below the noise floor, lift it to the floor.
            pdl_sl      = round(pdl * 0.999, 2)
            sl_floor    = round(entry_trigger - entry_trigger * _SL_MIN_PCT, 2)
            stop_loss   = min(pdl_sl, sl_floor)   # take the lower (wider) of the two
            stop_loss   = round(stop_loss, 2)

            sl_distance = round(entry_trigger - stop_loss, 2)
            sl_pct      = sl_distance / entry_trigger
            sl_too_wide = sl_pct > _SL_FILTER_PCT

            sl_basis = f"PDL ₹{pdl:.2f}"
            if sl_too_wide:
                sl_basis += f" [WIDE — {round(sl_pct*100,2)}% risk, consider skipping]"

            # Gap invalidation level: if next session opens above this, PDH trigger
            # is already blown through — the setup is stale and should be skipped.
            gap_invalidation_level = round(pdh * 1.01, 2)

            # Slippage-adjusted fill: what a market/stop order actually fills at
            # through a live breakout (0.2% above trigger is conservative but realistic).
            entry_fill  = round(entry_trigger * (1 + _ENTRY_SLIPPAGE_PCT), 2)
            slippage_cost = round(entry_fill - entry_trigger, 2)

            # Actual risk is from fill price to SL, not from trigger to SL.
            # This is always larger than the theoretical risk — position sizing
            # must use this number or the trade is over-sized.
            actual_risk = round(entry_fill - stop_loss, 2)

            # Intraday targets: absolute market price levels (0.5×/1×/1.5× ATR from trigger).
            # Targets are chart levels — they don't move based on your fill.
            # But net P&L at each target depends on fill price + exit slippage.
            t3_atr  = entry_trigger + 1.5 * atr
            t3_cap  = entry_trigger * (1 + _T3_MAX_PCT)
            target1 = round(entry_trigger + 0.5 * atr, 2)
            target2 = round(entry_trigger + 1.0 * atr, 2)
            target3 = round(min(t3_atr, t3_cap), 2)

            # Net gain at each target after exit slippage (limit order gives back 0.1%)
            t1_net_gain = round((target1 * (1 - _EXIT_SLIPPAGE_PCT)) - entry_fill, 2)
            t2_net_gain = round((target2 * (1 - _EXIT_SLIPPAGE_PCT)) - entry_fill, 2)
            t3_net_gain = round((target3 * (1 - _EXIT_SLIPPAGE_PCT)) - entry_fill, 2)

            # T1 viability: if net gain after both slippages is < 0.5% of fill,
            # booking T1 barely covers commissions and is not worth the order.
            t1_net_pct  = t1_net_gain / entry_fill if entry_fill > 0 else 0
            t1_too_close = t1_net_pct < _MIN_T1_NET_PCT

            setup_note = (
                f"Enter on break above PDH ₹{pdh:.2f} → trigger ₹{entry_trigger:.2f} "
                f"(expect fill ~₹{entry_fill:.2f} after slippage). "
                f"SKIP if next open > ₹{gap_invalidation_level:.2f} (gap-up invalidates PDH trigger). "
                f"SL at {sl_basis} (risk {round(sl_pct*100,2)}% from trigger, "
                f"{round(actual_risk/entry_fill*100,2)}% from fill). "
                f"Book 40% at T1, move SL to breakeven. Book 40% at T2. Trail rest to T3."
            )
            if t1_too_close:
                setup_note += (
                    f" WARNING: T1 net gain after slippage is only {round(t1_net_pct*100,2)}% "
                    f"(< 0.5%) — consider skipping T1 and scaling out at T2 only."
                )

        else:  # SHORT
            # Entry trigger: just below PDL
            entry_trigger = round(pdl * 0.999, 2)

            # SL: always the true PDH-based level — never artificially tightened.
            # If the natural SL is below the noise floor, drop it to the floor.
            pdh_sl      = round(pdh * 1.001, 2)
            sl_floor    = round(entry_trigger + entry_trigger * _SL_MIN_PCT, 2)
            stop_loss   = max(pdh_sl, sl_floor)   # take the higher (wider) of the two
            stop_loss   = round(stop_loss, 2)

            sl_distance = round(stop_loss - entry_trigger, 2)
            sl_pct      = sl_distance / entry_trigger
            sl_too_wide = sl_pct > _SL_FILTER_PCT

            sl_basis = f"PDH ₹{pdh:.2f}"
            if sl_too_wide:
                sl_basis += f" [WIDE — {round(sl_pct*100,2)}% risk, consider skipping]"

            # Gap invalidation level: if next session opens below this, PDL trigger
            # is already blown through — the setup is stale and should be skipped.
            gap_invalidation_level = round(pdl * 0.99, 2)

            # Slippage-adjusted fill: short orders fill below trigger (0.2% worse)
            entry_fill    = round(entry_trigger * (1 - _ENTRY_SLIPPAGE_PCT), 2)
            slippage_cost = round(entry_trigger - entry_fill, 2)

            # Actual risk from fill to SL — always larger than trigger-to-SL.
            actual_risk = round(stop_loss - entry_fill, 2)

            # Targets are absolute chart levels; net P&L depends on fill + exit slippage.
            t3_atr  = entry_trigger - 1.5 * atr
            t3_cap  = entry_trigger * (1 - _T3_MAX_PCT)
            target1 = round(entry_trigger - 0.5 * atr, 2)
            target2 = round(entry_trigger - 1.0 * atr, 2)
            target3 = round(max(t3_atr, t3_cap), 2)

            # Net gain at each target after exit slippage (buy-to-cover limit, 0.1%)
            t1_net_gain = round(entry_fill - (target1 * (1 + _EXIT_SLIPPAGE_PCT)), 2)
            t2_net_gain = round(entry_fill - (target2 * (1 + _EXIT_SLIPPAGE_PCT)), 2)
            t3_net_gain = round(entry_fill - (target3 * (1 + _EXIT_SLIPPAGE_PCT)), 2)

            t1_net_pct   = t1_net_gain / entry_fill if entry_fill > 0 else 0
            t1_too_close = t1_net_pct < _MIN_T1_NET_PCT

            setup_note = (
                f"Enter on break below PDL ₹{pdl:.2f} → trigger ₹{entry_trigger:.2f} "
                f"(expect fill ~₹{entry_fill:.2f} after slippage). "
                f"SKIP if next open < ₹{gap_invalidation_level:.2f} (gap-down invalidates PDL trigger). "
                f"SL at {sl_basis} (risk {round(sl_pct*100,2)}% from trigger, "
                f"{round(actual_risk/entry_fill*100,2)}% from fill). "
                f"Book 40% at T1, move SL to breakeven. Book 40% at T2. Trail rest to T3."
            )
            if t1_too_close:
                setup_note += (
                    f" WARNING: T1 net gain after slippage is only {round(t1_net_pct*100,2)}% "
                    f"(< 0.5%) — consider skipping T1 and scaling out at T2 only."
                )

        # Theoretical risk (trigger → SL) — kept for reference / display alongside adjusted
        risk_pct     = round((sl_distance / entry_trigger) * 100, 2)

        # Slippage-adjusted RR: reward = net gain at target (after exit slip),
        # risk = actual_risk (fill → SL). This is what the trade actually delivers.
        rr_t1 = round(t1_net_gain / actual_risk, 2) if actual_risk > 0 else 0
        rr_t2 = round(t2_net_gain / actual_risk, 2) if actual_risk > 0 else 0
        rr_t3 = round(t3_net_gain / actual_risk, 2) if actual_risk > 0 else 0

        # ── Capital-relative position sizing ─────────────────────────────────
        # Use caller-supplied capital, or fall back to config value.
        effective_capital = float(capital) if capital and capital > 0 else ACCOUNT_CAPITAL

        # Recommended position: risk exactly RISK_PER_TRADE_PCT of capital.
        #   shares = (capital × risk_pct) / (fill → SL distance per share)
        recommended_risk_amt = effective_capital * RISK_PER_TRADE_PCT / 100.0
        pos_size_recommended = int(recommended_risk_amt / actual_risk) if actual_risk > 0 else 0

        # Additional tiers so the trader can dial in their own risk tolerance.
        pos_size_half_pct = int((effective_capital * 0.005) / actual_risk) if actual_risk > 0 else 0
        pos_size_2_pct    = int((effective_capital * 0.020) / actual_risk) if actual_risk > 0 else 0

        # What % of configured capital is at risk with the recommended position?
        capital_risk_amt  = round(actual_risk * pos_size_recommended, 2)
        capital_risk_pct  = round(capital_risk_amt / effective_capital * 100, 4) if effective_capital > 0 else 0

        # Warn when the recommended position still results in > RISK_WARNING_PCT of capital.
        # This happens when the SL is very wide relative to capital — the setup
        # position-sizes itself to near-zero shares and the math rounds oddly.
        capital_risk_high = capital_risk_pct > RISK_WARNING_PCT

        actual_risk_pct = round((actual_risk / entry_fill) * 100, 2) if entry_fill > 0 else 0

        # Append capital risk context to setup note.
        setup_note += (
            f" Position (1% of ₹{effective_capital:,.0f}): {pos_size_recommended} shares "
            f"risking ₹{capital_risk_amt:,.0f} ({capital_risk_pct:.2f}% of capital)."
        )
        if capital_risk_high:
            setup_note += (
                f" ⚠ CAPITAL RISK HIGH: effective risk {capital_risk_pct:.2f}% > "
                f"{RISK_WARNING_PCT}% threshold. Reduce position or skip setup."
            )

        return {
            "entry":                  round(close, 2),           # reference (prev close)
            "entry_trigger":          entry_trigger,              # chart level that confirms entry
            "entry_fill":             entry_fill,                 # expected actual fill (post-slippage)
            "slippage_cost":          slippage_cost,              # ₹ lost on entry alone
            "gap_invalidation_level": gap_invalidation_level,    # skip if open breaches this
            "stop_loss":              stop_loss,                  # true PDL/PDH-based SL
            "target1":                target1,
            "target2":                target2,
            "target3":                target3,
            "t1_net_gain":            t1_net_gain,               # net ₹ gain at T1 after all slippage
            "t2_net_gain":            t2_net_gain,
            "t3_net_gain":            t3_net_gain,
            "t1_too_close":           t1_too_close,              # True when T1 net gain < 0.5% of fill
            "risk_pct":               risk_pct,                  # % risk trigger→SL (pre-slippage)
            "actual_risk_pct":        actual_risk_pct,           # % risk fill→SL (realistic)
            "sl_distance":            round(sl_distance, 2),     # trigger→SL distance
            "actual_risk":            round(actual_risk, 2),     # fill→SL ₹ distance (per share)
            "sl_too_wide":            sl_too_wide,               # True if SL > 2%
            "rr_t1":                  rr_t1,                     # slippage-adjusted RR at T1
            "rr_t2":                  rr_t2,
            "rr_t3":                  rr_t3,
            # Capital-relative sizing (ACCOUNT_CAPITAL from config.py)
            "configured_capital":     effective_capital,
            "position_size":          pos_size_recommended,      # shares at RISK_PER_TRADE_PCT
            "position_size_half_pct": pos_size_half_pct,         # shares at 0.5% risk
            "position_size_2pct":     pos_size_2_pct,            # shares at 2.0% risk
            "capital_risk_amt":       capital_risk_amt,           # ₹ at risk (recommended position)
            "capital_risk_pct":       capital_risk_pct,           # % of capital at risk
            "capital_risk_high":      capital_risk_high,          # True if > RISK_WARNING_PCT
            "atr_used":               round(atr, 2),
            "prev_day_high":          round(pdh, 2),
            "prev_day_low":           round(pdl, 2),
            "setup_note":             setup_note,
        }

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Risk calculation error: {e}")
        return {}
