"""
Scoring Model (0-95) for Long and Short setups.

LONG SCORE weights:
- Trend Score:      0-25 pts  (MA alignment + market structure)
- Breakout Score:   0-25 pts  (breakout strength + closing strength)
- Volume Score:     0-20 pts  (volume spike + price-volume alignment)
- Volatility Score: 0-15 pts  (ATR expansion signals momentum)
- RSI Score:        0-10 pts  (momentum zone — measures remaining room, not already captured)

SHORT SCORE: mirror logic

Global sentiment does NOT boost scores. It gates the HIGH_PROB threshold in
ranker.classify_stock() — STRONG_BULLISH raises the bar to 75 (harder to enter
when euphoric), MILD_BEARISH lowers it to 65 (setups are higher quality when
fear-driven). Boosting scores on strong-sentiment days generated more signals
exactly when risk/reward was worst (extended moves, institutions distributing).

Signal quality (HIGH_CONFIDENCE / MODERATE / WEAK) is NOT included as a score
component — it is derived from the same four component conditions already scored
above, so adding it would double-count evidence.
"""


def calculate_long_score(indicators: dict, signal: dict = None, global_adjustment: int = 0) -> int:
    """
    Returns 0-95 long probability score.
    Higher score = stronger long setup.
    `signal` is accepted but not used — signal quality is derived from the same
    conditions already captured in the component scores; including it again would
    double-count evidence.
    `global_adjustment` is accepted but not applied to the score. Sentiment is
    handled as an asymmetric threshold gate in ranker.classify_stock(), not as a
    score boost. Keeping the parameter avoids breaking existing call sites.
    """
    # Component scores from indicators
    trend_score = indicators.get("trend_score", 0)
    volume_score = indicators.get("volume_score", 0)
    volatility_score = indicators.get("volatility_score", 0)
    rsi_score = indicators.get("rsi_score", 0)

    # Breakout score for LONG - only positive if bullish direction
    raw_breakout_score = indicators.get("breakout_score", 0)
    breakout_status = indicators.get("breakout_status", "INSIDE")
    pv_alignment = indicators.get("price_volume_alignment", "NEUTRAL")
    trend_bias = indicators.get("trend_bias", "NEUTRAL")

    # Directional adjustment for breakout score
    # A BREAKDOWN/NEAR_BREAKDOWN stock contributes 0 pts to the long score — the
    # raw score (which is direction-agnostic) must not leak through as a positive.
    if breakout_status in ("BREAKDOWN", "NEAR_BREAKDOWN"):
        breakout_score = 0
    else:
        breakout_score = raw_breakout_score

    # Directional adjustment for volume score
    # BEARISH PV alignment = price falling on high volume = distribution (institutional
    # selling). This must contribute 0 pts to a long score regardless of spike magnitude.
    if pv_alignment == "BEARISH":
        volume_score_adj = 0
    else:
        volume_score_adj = volume_score

    # Trend bias adjustment
    if trend_bias == "BEARISH":
        trend_score = max(0, trend_score - 15)  # Heavy penalty for bearish trend in long
    elif trend_bias == "NEUTRAL":
        trend_score = max(0, trend_score - 5)

    # Base score
    base_score = (
        trend_score +
        breakout_score +
        volume_score_adj +
        volatility_score +
        rsi_score
    )

    # Clamp to 0-100
    return max(0, min(100, int(base_score)))


def calculate_short_score(indicators: dict, signal: dict = None, global_adjustment: int = 0) -> int:
    """
    Returns 0-95 short probability score.
    Higher score = stronger short setup. Mirror logic of long score.
    `signal` and `global_adjustment` are accepted but not used — see calculate_long_score.
    """
    trend_score = indicators.get("trend_score", 0)
    volume_score = indicators.get("volume_score", 0)
    volatility_score = indicators.get("volatility_score", 0)
    rsi_score = indicators.get("rsi_score", 0)
    raw_breakout_score = indicators.get("breakout_score", 0)
    breakout_status = indicators.get("breakout_status", "INSIDE")
    pv_alignment = indicators.get("price_volume_alignment", "NEUTRAL")
    trend_bias = indicators.get("trend_bias", "NEUTRAL")
    closing_strength = indicators.get("closing_strength", 50)

    # Directional adjustment for breakout score (short needs breakdown)
    # A BREAKOUT/NEAR_BREAKOUT stock contributes 0 pts to the short score — mirror
    # of the long-score fix: the direction-agnostic raw score must not leak through.
    if breakout_status in ("BREAKOUT", "NEAR_BREAKOUT"):
        breakout_score = 0
    else:
        breakout_score = raw_breakout_score

    # For short: weak close is good, strong close is bad
    if closing_strength > 65:
        breakout_score = max(0, breakout_score - 5)
    elif closing_strength < 35:
        breakout_score = min(25, breakout_score + 3)

    # Volume alignment: BEARISH pv alignment is good for short.
    # BULLISH alignment = price rising on high volume = accumulation. Must contribute
    # 0 pts to a short score — mirror of the long-score fix above.
    if pv_alignment == "BULLISH":
        volume_score_adj = 0
    else:
        volume_score_adj = volume_score

    # Trend bias adjustment
    if trend_bias == "BULLISH":
        trend_score = max(0, trend_score - 15)  # Heavy penalty for bullish trend in short
    elif trend_bias == "NEUTRAL":
        trend_score = max(0, trend_score - 5)

    # Base score
    base_score = (
        trend_score +
        breakout_score +
        volume_score_adj +
        volatility_score +
        rsi_score
    )

    return max(0, min(100, int(base_score)))
