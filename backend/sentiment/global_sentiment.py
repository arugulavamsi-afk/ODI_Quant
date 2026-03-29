"""
Global market sentiment analysis.
Aggregates global index/commodity signals into a single -10 to +10 score.
"""


def calculate_global_score(global_data: dict) -> dict:
    """
    Score each global input:
    - S&P500 1d change:  > +1% = +2, > +0.5% = +1, < -1% = -2, < -0.5% = -1
    - NASDAQ 1d change:  same weights
    - Nikkei 1d change:  > +1% = +1, < -1% = -1
    - Hang Seng:         > +1% = +1, < -1% = -1
    - Crude (CL):        > +2% = -1 (cost pressure), < -2% = +1
    - Gold (GC):         > +1% = -0.5 (fear), < -1% = +0.5
    - DXY:               > +0.5% = -1 (strong dollar = FII outflow), < -0.5% = +1

    Total: -10 to +10
    """
    score = 0.0
    components = {}

    scoring_rules = {
        "^GSPC": {"name": "S&P 500", "type": "equity", "weight": "high"},
        "^IXIC": {"name": "NASDAQ", "type": "equity", "weight": "high"},
        "^N225": {"name": "Nikkei 225", "type": "equity", "weight": "medium"},
        "^HSI": {"name": "Hang Seng", "type": "equity", "weight": "medium"},
        "CL=F": {"name": "Crude Oil", "type": "commodity", "weight": "medium"},
        "GC=F": {"name": "Gold", "type": "safe_haven", "weight": "low"},
        "DX-Y.NYB": {"name": "US Dollar Index", "type": "currency", "weight": "medium"},
    }

    for symbol, rules in scoring_rules.items():
        if symbol not in global_data:
            components[symbol] = {"name": rules["name"], "change_pct": 0, "contribution": 0}
            continue

        data = global_data[symbol]
        change = data.get("change_1d", 0)
        contribution = 0.0

        if symbol in ("^GSPC", "^IXIC"):
            # Major US equity indices - high weight
            if change > 1.0:
                contribution = 2.0
            elif change > 0.5:
                contribution = 1.0
            elif change < -1.0:
                contribution = -2.0
            elif change < -0.5:
                contribution = -1.0
            else:
                contribution = 0.0

        elif symbol in ("^N225", "^HSI"):
            # Asian equity indices - medium weight
            if change > 1.0:
                contribution = 1.0
            elif change > 0.5:
                contribution = 0.5
            elif change < -1.0:
                contribution = -1.0
            elif change < -0.5:
                contribution = -0.5
            else:
                contribution = 0.0

        elif symbol == "CL=F":
            # Crude oil - rising oil = cost pressure for Indian markets
            if change > 2.0:
                contribution = -1.0
            elif change > 1.0:
                contribution = -0.5
            elif change < -2.0:
                contribution = 1.0
            elif change < -1.0:
                contribution = 0.5
            else:
                contribution = 0.0

        elif symbol == "GC=F":
            # Gold - rising gold = fear/risk-off
            if change > 1.0:
                contribution = -0.5
            elif change < -1.0:
                contribution = 0.5
            else:
                contribution = 0.0

        elif symbol == "DX-Y.NYB":
            # DXY - strong dollar = FII outflow from India
            if change > 0.5:
                contribution = -1.0
            elif change > 0.25:
                contribution = -0.5
            elif change < -0.5:
                contribution = 1.0
            elif change < -0.25:
                contribution = 0.5
            else:
                contribution = 0.0

        score += contribution
        components[symbol] = {
            "name": rules["name"],
            "change_pct": round(change, 3),
            "contribution": round(contribution, 2),
            "last_close": data.get("last_close"),
            "trend": data.get("trend", "NEUTRAL"),
        }

    # Clamp score to -10 to +10
    score = max(-10.0, min(10.0, round(score, 2)))

    # Classification
    if score >= 6:
        classification = "STRONG_BULLISH"
        long_adjustment = 5
        short_adjustment = -5
    elif score >= 3:
        classification = "MILD_BULLISH"
        long_adjustment = 5
        short_adjustment = -5
    elif score >= -2:
        classification = "NEUTRAL"
        long_adjustment = 0
        short_adjustment = 0
    elif score >= -5:
        classification = "MILD_BEARISH"
        long_adjustment = -5
        short_adjustment = 5
    else:
        classification = "STRONG_BEARISH"
        long_adjustment = -5
        short_adjustment = 5

    # Also include Nifty50 in components for display
    if "^NSEI" in global_data:
        nsei = global_data["^NSEI"]
        components["^NSEI"] = {
            "name": "Nifty 50",
            "change_pct": round(nsei.get("change_1d", 0), 3),
            "contribution": 0,  # Not scored, just displayed
            "last_close": nsei.get("last_close"),
            "trend": nsei.get("trend", "NEUTRAL"),
        }

    return {
        "score": score,
        "classification": classification,
        "long_adjustment": long_adjustment,
        "short_adjustment": short_adjustment,
        "components": components,
    }


def get_global_sentiment_summary(global_data: dict) -> str:
    """Human readable summary of global market conditions"""
    result = calculate_global_score(global_data)
    score = result["score"]
    classification = result["classification"]

    lines = [
        f"Global Market Sentiment: {classification} (Score: {score:+.1f}/10)",
        "",
        "Key Drivers:",
    ]

    for symbol, comp in result["components"].items():
        name = comp["name"]
        change = comp["change_pct"]
        contrib = comp.get("contribution", 0)

        if contrib > 0:
            indicator = "+"
        elif contrib < 0:
            indicator = "-"
        else:
            indicator = "~"

        lines.append(f"  {indicator} {name}: {change:+.2f}% (impact: {contrib:+.1f})")

    lines.append("")
    lines.append(f"Long Score Adjustment: {result['long_adjustment']:+d}")
    lines.append(f"Short Score Adjustment: {result['short_adjustment']:+d}")

    return "\n".join(lines)
