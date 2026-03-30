"""
Stock ranking and classification module.
Classifies stocks and generates human-readable trade explanations.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import HIGH_PROB_THRESHOLD, WATCHLIST_THRESHOLD


def classify_stock(long_score: int, short_score: int) -> dict:
    """
    Returns category and direction:
    - long_score >= 70:  'HIGH_PROB_LONG'
    - short_score >= 70: 'HIGH_PROB_SHORT'
    - long_score >= 50 or short_score >= 50: 'WATCHLIST'
    - else: 'NO_TRADE'

    If both long and short >= 70, pick the higher one.
    """
    if long_score >= HIGH_PROB_THRESHOLD and short_score >= HIGH_PROB_THRESHOLD:
        # Both high - pick the stronger one
        if long_score >= short_score:
            return {
                "category": "HIGH_PROB_LONG",
                "label": "HIGH_PROB_LONG",
                "direction": "LONG",
                "priority": 1,
            }
        else:
            return {
                "category": "HIGH_PROB_SHORT",
                "label": "HIGH_PROB_SHORT",
                "direction": "SHORT",
                "priority": 1,
            }
    elif long_score >= HIGH_PROB_THRESHOLD:
        return {
            "category": "HIGH_PROB_LONG",
            "label": "HIGH_PROB_LONG",
            "direction": "LONG",
            "priority": 1,
        }
    elif short_score >= HIGH_PROB_THRESHOLD:
        return {
            "category": "HIGH_PROB_SHORT",
            "label": "HIGH_PROB_SHORT",
            "direction": "SHORT",
            "priority": 1,
        }
    elif long_score >= WATCHLIST_THRESHOLD or short_score >= WATCHLIST_THRESHOLD:
        direction = "LONG" if long_score >= short_score else "SHORT"
        return {
            "category": "WATCHLIST",
            "label": "WATCHLIST",
            "direction": direction,
            "priority": 2,
        }
    else:
        direction = "LONG" if long_score >= short_score else "SHORT"
        return {
            "category": "NO_TRADE",
            "label": "NO_TRADE",
            "direction": direction,
            "priority": 3,
        }


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
        trigger  = trade_levels.get("entry_trigger") or trade_levels.get("entry", close)
        sl       = trade_levels.get("stop_loss", 0)
        t1       = trade_levels.get("target1", 0)
        t2       = trade_levels.get("target2", 0)
        t3       = trade_levels.get("target3", 0)
        risk_pct = trade_levels.get("risk_pct", 0)
        rr_t1    = trade_levels.get("rr_t1", 0)
        rr_t2    = trade_levels.get("rr_t2", 0)
        pos_size = trade_levels.get("position_size_1L", 0)
        note     = trade_levels.get("setup_note", "")

        lines.append("")
        lines.append(f"Day Trade Setup ({direction}):")
        if note:
            lines.append(f"  ~ {note}")
        lines.append(f"  Entry Trigger: Rs.{trigger:.2f}")
        lines.append(f"  Stop Loss:     Rs.{sl:.2f} ({risk_pct:.1f}% risk)")
        lines.append(f"  Target 1 (1×ATR): Rs.{t1:.2f}  [{rr_t1:.1f}:1 RR] — Book 50%, move SL to breakeven")
        lines.append(f"  Target 2 (2×ATR): Rs.{t2:.2f}  [{rr_t2:.1f}:1 RR] — Book 30%")
        lines.append(f"  Target 3 (3×ATR): Rs.{t3:.2f}  — Trail remaining 20%")
        lines.append(f"  Position Size (₹1L risk): {pos_size} shares")

    return "\n".join(lines)
