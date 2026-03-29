"""
Short signal generation rules
"""


def check_short_rules(indicators: dict) -> dict:
    """
    SHORT signal rules (mirror of long):
    1. Trend = BEARISH
    2. Breakdown = BREAKDOWN or NEAR_BREAKDOWN
    3. Volume spike > 1.5x
    4. Closing strength < 35%
    5. ATR expanding (ratio > 1.2)

    Returns: triggered rules and count
    """
    triggered = []
    rule_details = []

    # Rule 1: Trend
    if indicators.get("trend_bias") == "BEARISH":
        triggered.append("TREND_BEARISH")
        rule_details.append("Trend is BEARISH (price below key MAs)")

    # Rule 2: Breakdown
    breakout_status = indicators.get("breakout_status", "INSIDE")
    if breakout_status in ("BREAKDOWN", "NEAR_BREAKDOWN"):
        triggered.append("BREAKDOWN")
        rule_details.append(f"Price {breakout_status} below {indicators.get('breakout_period', 20)}-day low")

    # Rule 3: Volume spike
    volume_spike = indicators.get("volume_spike", 0)
    if volume_spike >= 1.5:
        triggered.append("VOLUME_SPIKE")
        rule_details.append(f"Volume spike {volume_spike:.1f}x above 20-day average")

    # Rule 4: Closing strength (weak close for short)
    closing_strength = indicators.get("closing_strength", 50)
    if closing_strength <= 35:
        triggered.append("WEAK_CLOSE")
        rule_details.append(f"Weak close at {closing_strength:.0f}% of day's range")

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
