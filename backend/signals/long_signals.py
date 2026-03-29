"""
Long signal generation rules
"""


def check_long_rules(indicators: dict) -> dict:
    """
    LONG signal rules:
    1. Trend = BULLISH
    2. Breakout = BREAKOUT or NEAR_BREAKOUT
    3. Volume spike > 1.5x
    4. Closing strength > 65%
    5. ATR expanding (ratio > 1.2)

    Returns: triggered rules and count
    """
    triggered = []
    rule_details = []

    # Rule 1: Trend
    if indicators.get("trend_bias") == "BULLISH":
        triggered.append("TREND_BULLISH")
        rule_details.append("Trend is BULLISH (price above key MAs)")

    # Rule 2: Breakout
    breakout_status = indicators.get("breakout_status", "INSIDE")
    if breakout_status in ("BREAKOUT", "NEAR_BREAKOUT"):
        triggered.append("BREAKOUT")
        rule_details.append(f"Price {breakout_status} above {indicators.get('breakout_period', 20)}-day high")

    # Rule 3: Volume spike
    volume_spike = indicators.get("volume_spike", 0)
    if volume_spike >= 1.5:
        triggered.append("VOLUME_SPIKE")
        rule_details.append(f"Volume spike {volume_spike:.1f}x above 20-day average")

    # Rule 4: Closing strength
    closing_strength = indicators.get("closing_strength", 50)
    if closing_strength >= 65:
        triggered.append("STRONG_CLOSE")
        rule_details.append(f"Strong close at {closing_strength:.0f}% of day's range")

    # Rule 5: ATR expansion
    atr_expansion = indicators.get("atr_expansion", 1.0)
    if atr_expansion >= 1.2:
        triggered.append("ATR_EXPANDING")
        rule_details.append(f"ATR expanding ({atr_expansion:.1f}x avg) - momentum building")

    return {
        "triggered_rules": triggered,
        "rule_details": rule_details,
        "rule_count": len(triggered),
    }
