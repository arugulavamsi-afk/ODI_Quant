"""
Stock ranking and classification module.
Classifies stocks and generates human-readable trade explanations.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import HIGH_PROB_THRESHOLD, WATCHLIST_THRESHOLD, RISK_WARNING_PCT

# Alias used in explanation strings so the displayed threshold matches config.
RISK_WARNING_PCT_DISPLAY = RISK_WARNING_PCT


def classify_stock(long_score: int, short_score: int, sl_too_wide: bool = False) -> dict:
    """
    Returns category and direction:
    - long_score >= 70:  'HIGH_PROB_LONG'
    - short_score >= 70: 'HIGH_PROB_SHORT'
    - long_score >= 50 or short_score >= 50: 'WATCHLIST'
    - else: 'NO_TRADE'

    If both long and short >= 70, pick the higher one.

    sl_too_wide=True: natural PDL/PDH stop exceeds 2% of entry.
    These setups are demoted one tier — a HIGH_PROB becomes WATCHLIST
    and a WATCHLIST becomes NO_TRADE — because the real risk is too large
    to size correctly at ₹1L capital risk per trade.
    """
    if long_score >= HIGH_PROB_THRESHOLD and short_score >= HIGH_PROB_THRESHOLD:
        direction = "LONG" if long_score >= short_score else "SHORT"
        cat = f"HIGH_PROB_{direction}"
        if sl_too_wide:
            return {"category": "WATCHLIST", "label": f"WATCHLIST (SL>2%)", "direction": direction, "priority": 2}
        return {"category": cat, "label": cat, "direction": direction, "priority": 1}

    elif long_score >= HIGH_PROB_THRESHOLD:
        if sl_too_wide:
            return {"category": "WATCHLIST", "label": "WATCHLIST (SL>2%)", "direction": "LONG", "priority": 2}
        return {"category": "HIGH_PROB_LONG", "label": "HIGH_PROB_LONG", "direction": "LONG", "priority": 1}

    elif short_score >= HIGH_PROB_THRESHOLD:
        if sl_too_wide:
            return {"category": "WATCHLIST", "label": "WATCHLIST (SL>2%)", "direction": "SHORT", "priority": 2}
        return {"category": "HIGH_PROB_SHORT", "label": "HIGH_PROB_SHORT", "direction": "SHORT", "priority": 1}

    elif long_score >= WATCHLIST_THRESHOLD or short_score >= WATCHLIST_THRESHOLD:
        direction = "LONG" if long_score >= short_score else "SHORT"
        if sl_too_wide:
            return {"category": "NO_TRADE", "label": "NO_TRADE (SL>2%)", "direction": direction, "priority": 3}
        return {"category": "WATCHLIST", "label": "WATCHLIST", "direction": direction, "priority": 2}

    else:
        direction = "LONG" if long_score >= short_score else "SHORT"
        return {"category": "NO_TRADE", "label": "NO_TRADE", "direction": direction, "priority": 3}


def rank_stocks(results_list: list) -> list:
    """
    Sort by: HIGH_PROB first, then by max(long_score, short_score) descending.
    Returns ranked list with rank numbers.
    """
    def sort_key(stock):
        priority = stock.get("classification", {}).get("priority", 3)
        score = max(stock.get("long_score", 0), stock.get("short_score", 0))
        return (priority, -score)

    sorted_stocks = sorted(results_list, key=sort_key)

    for i, stock in enumerate(sorted_stocks):
        stock["rank"] = i + 1

    return sorted_stocks


def generate_explanation(
    symbol: str,
    name: str,
    indicators: dict,
    long_signal: dict,
    short_signal: dict,
    long_score: int,
    short_score: int,
    global_sentiment: dict,
    trade_levels: dict,
    direction: str,
) -> str:
    """
    Generates human-readable trade explanation with all key details.
    """
    close = indicators.get("close", 0)
    trend_bias = indicators.get("trend_bias", "NEUTRAL")
    breakout_status = indicators.get("breakout_status", "INSIDE")
    volume_spike = indicators.get("volume_spike", 1.0)
    closing_strength = indicators.get("closing_strength", 50)
    atr_expansion = indicators.get("atr_expansion", 1.0)
    ma20 = indicators.get("ma20")
    ma50 = indicators.get("ma50")
    ma200 = indicators.get("ma200")
    sentiment_class = global_sentiment.get("classification", "NEUTRAL") if global_sentiment else "NEUTRAL"
    sentiment_score = global_sentiment.get("score", 0) if global_sentiment else 0

    direction = direction.upper()
    is_long = direction == "LONG"
    score = long_score if is_long else short_score
    signal = long_signal if is_long else short_signal
    signal_quality = signal.get("signal", "NO_SIGNAL") if signal else "NO_SIGNAL"

    if score >= 70:
        category_label = f"HIGH PROBABILITY {'LONG' if is_long else 'SHORT'}"
    elif score >= 50:
        category_label = "WATCHLIST CANDIDATE"
    else:
        category_label = "LOW PROBABILITY SETUP"

    lines = [
        f"{symbol} is a {category_label} setup",
        f"Signal Quality: {signal_quality} | Score: {score}/100",
        "",
        "Setup Analysis:",
    ]

    # Trend analysis
    if trend_bias == "BULLISH":
        ma_desc = ""
        if ma20 and ma50 and ma200:
            ma_desc = f" - Price ({close:.0f}) > MA20 ({ma20:.0f}) > MA50 ({ma50:.0f}) > MA200 ({ma200:.0f})"
        elif ma20 and ma50:
            ma_desc = f" - Price ({close:.0f}) > MA20 ({ma20:.0f}) > MA50 ({ma50:.0f})"
        indicator = "+" if is_long else "-"
        lines.append(f"  {indicator} Trend is BULLISH{ma_desc}")
    elif trend_bias == "BEARISH":
        ma_desc = ""
        if ma20 and ma50 and ma200:
            ma_desc = f" - Price ({close:.0f}) < MA20 ({ma20:.0f}) < MA50 ({ma50:.0f}) < MA200 ({ma200:.0f})"
        elif ma20 and ma50:
            ma_desc = f" - Price ({close:.0f}) < MA20 ({ma20:.0f}) < MA50 ({ma50:.0f})"
        indicator = "-" if is_long else "+"
        lines.append(f"  {indicator} Trend is BEARISH{ma_desc}")
    else:
        lines.append(f"  ~ Trend is NEUTRAL - Mixed MA alignment")

    # Breakout analysis
    breakout_level = indicators.get("breakout_level")
    breakdown_level = indicators.get("breakdown_level")
    if breakout_status == "BREAKOUT" and breakout_level:
        indicator = "+" if is_long else "-"
        lines.append(f"  {indicator} BREAKOUT above 20-day high of Rs.{breakout_level:.2f} with {volume_spike:.1f}x volume")
    elif breakout_status == "BREAKDOWN" and breakdown_level:
        indicator = "-" if is_long else "+"
        lines.append(f"  {indicator} BREAKDOWN below 20-day low of Rs.{breakdown_level:.2f} with {volume_spike:.1f}x volume")
    elif breakout_status == "NEAR_BREAKOUT" and breakout_level:
        lines.append(f"  ~ Near breakout of 20-day high at Rs.{breakout_level:.2f}")
    elif breakout_status == "NEAR_BREAKDOWN" and breakdown_level:
        lines.append(f"  ~ Near breakdown of 20-day low at Rs.{breakdown_level:.2f}")
    else:
        lines.append(f"  ~ Inside range - no breakout/breakdown")

    # Volume analysis
    if volume_spike >= 2.0:
        pv = indicators.get("price_volume_alignment", "NEUTRAL")
        indicator = "+" if (is_long and pv == "BULLISH") or (not is_long and pv == "BEARISH") else "~"
        lines.append(f"  {indicator} Strong volume spike: {volume_spike:.1f}x average ({pv} price-volume)")
    elif volume_spike >= 1.5:
        lines.append(f"  + Volume up: {volume_spike:.1f}x average")
    else:
        lines.append(f"  ~ Low volume: {volume_spike:.1f}x average (weak signal)")

    # Closing strength
    if closing_strength >= 70:
        indicator = "+" if is_long else "-"
        lines.append(f"  {indicator} Strong close at {closing_strength:.0f}% of today's range (bullish candle)")
    elif closing_strength <= 30:
        indicator = "-" if is_long else "+"
        lines.append(f"  {indicator} Weak close at {closing_strength:.0f}% of today's range (bearish candle)")
    else:
        lines.append(f"  ~ Neutral close at {closing_strength:.0f}% of today's range")

    # ATR expansion
    if atr_expansion >= 1.5:
        indicator = "+"
        lines.append(f"  {indicator} ATR expanding ({atr_expansion:.1f}x avg) - strong momentum")
    elif atr_expansion >= 1.2:
        lines.append(f"  + ATR moderately expanding ({atr_expansion:.1f}x avg) - building momentum")
    else:
        lines.append(f"  ~ ATR flat/contracting ({atr_expansion:.1f}x avg)")

    # Global sentiment
    if sentiment_class in ("STRONG_BULLISH", "MILD_BULLISH"):
        indicator = "+" if is_long else "-"
        lines.append(f"  {indicator} Global sentiment {sentiment_class} (score: {sentiment_score:+.1f}) {'supports' if is_long else 'opposes'} long bias")
    elif sentiment_class in ("STRONG_BEARISH", "MILD_BEARISH"):
        indicator = "-" if is_long else "+"
        lines.append(f"  {indicator} Global sentiment {sentiment_class} (score: {sentiment_score:+.1f}) {'opposes' if is_long else 'supports'} short bias")
    else:
        lines.append(f"  ~ Global sentiment NEUTRAL (score: {sentiment_score:+.1f})")

    # Trade levels
    if trade_levels:
        trigger               = trade_levels.get("entry_trigger") or trade_levels.get("entry", close)
        entry_fill            = trade_levels.get("entry_fill", trigger)
        slippage_cost         = trade_levels.get("slippage_cost", 0)
        gap_invalid           = trade_levels.get("gap_invalidation_level")
        sl                    = trade_levels.get("stop_loss", 0)
        t1                    = trade_levels.get("target1", 0)
        t2                    = trade_levels.get("target2", 0)
        t3                    = trade_levels.get("target3", 0)
        t1_net_gain           = trade_levels.get("t1_net_gain", 0)
        t2_net_gain           = trade_levels.get("t2_net_gain", 0)
        t1_too_close          = trade_levels.get("t1_too_close", False)
        risk_pct              = trade_levels.get("risk_pct", 0)
        actual_risk_pct       = trade_levels.get("actual_risk_pct", risk_pct)
        rr_t1                 = trade_levels.get("rr_t1", 0)
        rr_t2                 = trade_levels.get("rr_t2", 0)
        rr_t3                 = trade_levels.get("rr_t3", 0)
        pos_size              = trade_levels.get("position_size", 0)
        pos_size_half         = trade_levels.get("position_size_half_pct", 0)
        pos_size_2pct         = trade_levels.get("position_size_2pct", 0)
        configured_capital    = trade_levels.get("configured_capital", 500_000)
        capital_risk_amt      = trade_levels.get("capital_risk_amt", 0)
        capital_risk_pct      = trade_levels.get("capital_risk_pct", 0)
        capital_risk_high     = trade_levels.get("capital_risk_high", False)
        actual_risk_per_share = trade_levels.get("actual_risk", 1)   # fill→SL ₹ per share
        note                  = trade_levels.get("setup_note", "")
        sl_too_wide           = trade_levels.get("sl_too_wide", False)
        gap_risk              = indicators.get("gap_risk", "LOW")

        lines.append("")
        lines.append(f"Day Trade Setup ({direction}):")
        if capital_risk_high:
            lines.append(f"  ⚠ CAPITAL RISK HIGH: This trade risks {capital_risk_pct:.2f}% of ₹{configured_capital:,.0f} "
                         f"(configured in config.py). Exceeds {RISK_WARNING_PCT_DISPLAY}% threshold. Reduce size or skip.")
        if sl_too_wide:
            lines.append(f"  ⚠ WIDE STOP: Natural PDL/PDH SL is {risk_pct:.1f}% away (> 2% threshold).")
            lines.append(f"    Setup demoted one tier. Trade only if you reduce position size accordingly.")
        if gap_risk == "HIGH":
            lines.append(f"  ⚠ GAP RISK HIGH: ATR > 2% of price. PDH/PDL trigger likely blown through at open.")
            if gap_invalid:
                gap_dir = "above" if direction == "LONG" else "below"
                lines.append(f"    If next open is {gap_dir} ₹{gap_invalid:.2f}, skip this setup — trigger is stale.")
        elif gap_risk == "MEDIUM" and gap_invalid:
            gap_dir = "above" if direction == "LONG" else "below"
            lines.append(f"  ~ GAP RISK MEDIUM: If next open is {gap_dir} ₹{gap_invalid:.2f}, skip — trigger stale.")
        if t1_too_close:
            lines.append(f"  ⚠ T1 TOO CLOSE: Net gain at T1 after slippage is ₹{t1_net_gain:.2f} — skip T1, scale out at T2.")
        if note:
            lines.append(f"  ~ {note}")
        lines.append(f"  Entry Trigger:    ₹{trigger:.2f}  (chart level)")
        lines.append(f"  Expected Fill:    ₹{entry_fill:.2f}  (after 0.2% entry slippage, ₹{slippage_cost:.2f} cost)")
        if gap_invalid:
            lines.append(f"  Gap Invalidation: ₹{gap_invalid:.2f}  ← skip if open breaches this")
        lines.append(f"  Stop Loss:        ₹{sl:.2f}  ({actual_risk_pct:.2f}% from fill  |  {risk_pct:.2f}% from trigger)")
        lines.append(f"  Target 1 (0.5×ATR): ₹{t1:.2f}  [{rr_t1:.2f}:1 RR after slip]  net ₹{t1_net_gain:.2f} — Book 40%, move SL→BE")
        lines.append(f"  Target 2 (1.0×ATR): ₹{t2:.2f}  [{rr_t2:.2f}:1 RR after slip]  net ₹{t2_net_gain:.2f} — Book 40%")
        lines.append(f"  Target 3 (1.5×ATR): ₹{t3:.2f}  [{rr_t3:.2f}:1 RR after slip]  — Trail remaining 20%")
        lines.append(f"  Position Sizing   (capital: ₹{configured_capital:,.0f} — set ACCOUNT_CAPITAL in config.py):")
        lines.append(f"    Conservative 0.5%: {pos_size_half} shares  risking ₹{round(actual_risk_per_share * pos_size_half, 0):.0f}")
        lines.append(f"    Standard     1.0%: {pos_size} shares  risking ₹{capital_risk_amt:,.0f}  ({capital_risk_pct:.2f}% of capital)")
        lines.append(f"    Aggressive   2.0%: {pos_size_2pct} shares  risking ₹{round(actual_risk_per_share * pos_size_2pct, 0):.0f}")

    return "\n".join(lines)
