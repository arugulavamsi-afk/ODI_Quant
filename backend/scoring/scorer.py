"""
Scoring Model (0-100) for Long and Short setups.

LONG SCORE weights:
- Trend Score:      0-25 pts  (MA alignment + market structure)
- Breakout Score:   0-25 pts  (breakout strength + closing strength)
- Volume Score:     0-20 pts  (volume spike + price-volume alignment)
- Volatility Score: 0-15 pts  (ATR expansion signals momentum)
- Signal Quality:   0-15 pts  (HIGH_CONFIDENCE=15, MODERATE=8, WEAK=3, NONE=0)

SHORT SCORE: mirror logic
Global sentiment adjustment: +/-5 pts
"""


SIGNAL_QUALITY_SCORES = {
    "HIGH_CONFIDENCE": 15,
    "MODERATE": 8,
    "WEAK": 3,
    "NO_SIGNAL": 0,
}


def calculate_long_score(indicators: dict, signal: dict, global_adjustment: int = 0) -> int:
    """
    Returns 0-100 long probability score.
    Higher score = stronger long setup.
    """
    # Component scores from indicators
    trend_score = indicators.get("trend_score", 0)
    volume_score = indicators.get("volume_score", 0)
    volatility_score = indicators.get("volatility_score", 0)

    # Breakout score for LONG - only positive if bullish direction
    raw_breakout_score = indicators.get("breakout_score", 0)
    breakout_status = indicators.get("breakout_status", "INSIDE")
    pv_alignment = indicators.get("price_volume_alignment", "NEUTRAL")
    trend_bias = indicators.get("trend_bias", "NEUTRAL")

    # Directional adjustment for breakout score
    if breakout_status in ("BREAKDOWN", "NEAR_BREAKDOWN"):
        breakout_score = max(0, raw_breakout_score - 10)  # Penalty for bearish breakout
    else:
        breakout_score = raw_breakout_score

    # Directional adjustment for volume score
    if pv_alignment == "BEARISH":
        volume_score_adj = max(0, volume_score - 5)  # Penalty for bearish vol signal
    else:
        volume_score_adj = volume_score

    # Trend bias adjustment
    if trend_bias == "BEARISH":
        trend_score = max(0, trend_score - 15)  # Heavy penalty for bearish trend in long
    elif trend_bias == "NEUTRAL":
        trend_score = max(0, trend_score - 5)

    # Signal quality score
    signal_quality = signal.get("signal", "NO_SIGNAL") if signal else "NO_SIGNAL"
    signal_score = SIGNAL_QUALITY_SCORES.get(signal_quality, 0)

    # Base score
    base_score = (
        trend_score +
        breakout_score +
        volume_score_adj +
        volatility_score +
        signal_score
    )

    # Apply global sentiment adjustment
    adjusted_score = base_score + global_adjustment

    # Clamp to 0-100
    return max(0, min(100, int(adjusted_score)))


def calculate_short_score(indicators: dict, signal: dict, global_adjustment: int = 0) -> int:
    """
    Returns 0-100 short probability score.
    Higher score = stronger short setup.
    Mirror logic of long score.
    """
    trend_score = indicators.get("trend_score", 0)
    volume_score = indicators.get("volume_score", 0)
    volatility_score = indicators.get("volatility_score", 0)
    raw_breakout_score = indicators.get("breakout_score", 0)
    breakout_status = indicators.get("breakout_status", "INSIDE")
    pv_alignment = indicators.get("price_volume_alignment", "NEUTRAL")
    trend_bias = indicators.get("trend_bias", "NEUTRAL")
    closing_strength = indicators.get("closing_strength", 50)

    # Directional adjustment for breakout score (short needs breakdown)
    if breakout_status in ("BREAKOUT", "NEAR_BREAKOUT"):
        breakout_score = max(0, raw_breakout_score - 10)
    else:
        breakout_score = raw_breakout_score

    # For short: weak close is good, strong close is bad
    if closing_strength > 65:
        breakout_score = max(0, breakout_score - 5)
    elif closing_strength < 35:
        breakout_score = min(25, breakout_score + 3)

    # Volume alignment: BEARISH pv alignment is good for short
    if pv_alignment == "BULLISH":
        volume_score_adj = max(0, volume_score - 5)
    else:
        volume_score_adj = volume_score

    # Trend bias adjustment
    if trend_bias == "BULLISH":
        trend_score = max(0, trend_score - 15)  # Heavy penalty for bullish trend in short
    elif trend_bias == "NEUTRAL":
        trend_score = max(0, trend_score - 5)

    # Signal quality
    signal_quality = signal.get("signal", "NO_SIGNAL") if signal else "NO_SIGNAL"
    signal_score = SIGNAL_QUALITY_SCORES.get(signal_quality, 0)

    # Base score
    base_score = (
        trend_score +
        breakout_score +
        volume_score_adj +
        volatility_score +
        signal_score
    )

    # Apply global sentiment adjustment
    adjusted_score = base_score + global_adjustment

    return max(0, min(100, int(adjusted_score)))
