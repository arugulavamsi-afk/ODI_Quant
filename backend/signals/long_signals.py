"""
Long signal generation rules
"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from indicators.volume import is_genuine_volume_spike


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

    # Rule 3: Volume spike — must be stock-specific, not sector/market noise.
    # F&O expiry, index rebalancing, and post-holiday sessions lift sector volume
    # uniformly; a stock whose spike merely tracks the sector ETF spike is not
    # showing institutional accumulation.
    volume_spike     = indicators.get("volume_spike", 0)
    sector_etf_spike = indicators.get("sector_etf_spike")
    if volume_spike >= 1.5 and is_genuine_volume_spike(volume_spike, sector_etf_spike):
        triggered.append("VOLUME_SPIKE")
        if sector_etf_spike and sector_etf_spike >= 1.3:
            rule_details.append(
                f"Volume spike {volume_spike:.1f}x (sector ETF {sector_etf_spike:.1f}x) "
                f"— stock-specific accumulation confirmed"
            )
        else:
            rule_details.append(f"Volume spike {volume_spike:.1f}x above 20-day average")
    elif volume_spike >= 1.5 and sector_etf_spike and sector_etf_spike >= 1.3:
        # Spike exists but is not stock-specific — log why it was filtered
        rule_details.append(
            f"[VOL FILTERED] Volume {volume_spike:.1f}x but sector ETF also {sector_etf_spike:.1f}x "
            f"— F&O expiry / rebalancing noise, not accumulation"
        )

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
