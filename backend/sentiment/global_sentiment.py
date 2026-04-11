"""
Global market sentiment analysis.
Aggregates global index/commodity signals into a single -10 to +10 score.

Crude oil note:
  The base score treats rising crude as a NEGATIVE for the Indian market
  (cost pressure, current account deficit). This is correct on average but
  wrong for sectors that profit from rising crude prices.

  Use get_sector_adjustment(sentiment_result, sector) per stock instead of
  the blanket long_adjustment / short_adjustment.  That function reverses the
  crude component for oil-beneficiary sectors so ONGC/GAIL/BPCL/OIL get the
  right sign on the crude move.
"""

# Sectors where rising crude oil is a revenue/margin TAILWIND, not a cost.
# E&P companies gain directly on the upstream price.
# Gas distributors gain on product value.
# Petroleum refiners gain on inventory mark-ups (though spread matters too).
CRUDE_BENEFICIARY_SECTORS = {
    "Energy",              # E&P — ONGC, Oil India
    "Oil & Gas",           # Broad label used in some universe configs
    "Gas Distribution",    # GAIL, IGL, MGL
    "Gas",                 # Short-form variant
    "Petroleum Products",  # BPCL, HPCL (inventory gains on rising crude)
    "Refinery",            # Alternate label
}

# Sectors where a STRONG US dollar is actually a revenue tailwind
# (USD-billed exports = more INR revenue when dollar strengthens).
# Note: the base DXY logic is "strong dollar = FII outflow = bad",
# which is correct at the market level but wrong for IT exporters.
# This is NOT fixed here yet — flagged for a future sector-aware DXY pass.
# DXY_BENEFICIARY_SECTORS = {"IT Services", "Pharma", "Chemicals"}


def _classify_and_adjust(score: float) -> tuple:
    """Maps a sentiment score (-10 to +10) to (classification, long_adj, short_adj)."""
    if score >= 6:
        return "STRONG_BULLISH", 5, -5
    elif score >= 3:
        return "MILD_BULLISH", 5, -5
    elif score >= -2:
        return "NEUTRAL", 0, 0
    elif score >= -5:
        return "MILD_BEARISH", -5, 5
    else:
        return "STRONG_BEARISH", -5, 5


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
    crude_contribution = 0.0   # stored separately for per-sector reversal

    scoring_rules = {
        "^GSPC":     {"name": "S&P 500"},
        "^IXIC":     {"name": "NASDAQ"},
        "^N225":     {"name": "Nikkei 225"},
        "^HSI":      {"name": "Hang Seng"},
        "CL=F":      {"name": "Crude Oil"},
        "GC=F":      {"name": "Gold"},
        "DX-Y.NYB":  {"name": "US Dollar Index"},
    }

    for symbol, rules in scoring_rules.items():
        if symbol not in global_data:
            components[symbol] = {"name": rules["name"], "change_pct": 0, "contribution": 0}
            continue

        data = global_data[symbol]
        change = data.get("change_1d", 0)
        contribution = 0.0

        if symbol in ("^GSPC", "^IXIC"):
            if change > 1.0:       contribution =  2.0
            elif change > 0.5:     contribution =  1.0
            elif change < -1.0:    contribution = -2.0
            elif change < -0.5:    contribution = -1.0

        elif symbol in ("^N225", "^HSI"):
            if change > 1.0:       contribution =  1.0
            elif change > 0.5:     contribution =  0.5
            elif change < -1.0:    contribution = -1.0
            elif change < -0.5:    contribution = -0.5

        elif symbol == "CL=F":
            # Base crude signal: cost-pressure view (correct for most of India).
            # Oil-beneficiary sectors get this component REVERSED via
            # get_sector_adjustment(). Do NOT change the sign here.
            if change > 2.0:       contribution = -1.0
            elif change > 1.0:     contribution = -0.5
            elif change < -2.0:    contribution =  1.0
            elif change < -1.0:    contribution =  0.5
            crude_contribution = contribution   # capture before adding to score

        elif symbol == "GC=F":
            # Rising gold = fear / risk-off
            if change > 1.0:       contribution = -0.5
            elif change < -1.0:    contribution =  0.5

        elif symbol == "DX-Y.NYB":
            # Strong dollar = FII outflow from India (correct at market level;
            # IT/Pharma exporters benefit — see DXY_BENEFICIARY_SECTORS note above)
            if change > 0.5:       contribution = -1.0
            elif change > 0.25:    contribution = -0.5
            elif change < -0.5:    contribution =  1.0
            elif change < -0.25:   contribution =  0.5

        score += contribution
        components[symbol] = {
            "name": rules["name"],
            "change_pct": round(change, 3),
            "contribution": round(contribution, 2),
            "last_close": data.get("last_close"),
            "trend": data.get("trend", "NEUTRAL"),
        }

    score = max(-10.0, min(10.0, round(score, 2)))
    classification, long_adjustment, short_adjustment = _classify_and_adjust(score)

    # Display-only: include Nifty50 in components without scoring it
    if "^NSEI" in global_data:
        nsei = global_data["^NSEI"]
        components["^NSEI"] = {
            "name": "Nifty 50",
            "change_pct": round(nsei.get("change_1d", 0), 3),
            "contribution": 0,
            "last_close": nsei.get("last_close"),
            "trend": nsei.get("trend", "NEUTRAL"),
        }

    return {
        "score":             score,
        "classification":    classification,
        "long_adjustment":   long_adjustment,   # market-wide default
        "short_adjustment":  short_adjustment,  # market-wide default
        "crude_contribution": round(crude_contribution, 2),  # for per-sector reversal
        "components":        components,
    }


def get_sector_adjustment(global_sentiment: dict, sector: str) -> tuple:
    """
    Returns (long_adj, short_adj) tailored for the given sector.

    For most sectors this is identical to the market-wide adjustment.
    For CRUDE_BENEFICIARY_SECTORS the crude oil component is reversed:
      - Crude up → base score gets -1 (cost pressure for consumers)
      - But E&P / gas / refining companies PROFIT from rising crude
      - We reverse that component: re-score the market excluding crude,
        then add the opposite crude signal for the beneficiary sector.

    The reversal is: sector_score = base_score - crude_contribution + (-crude_contribution)
                                  = base_score - 2 × crude_contribution
    This cancels the consumer penalty and adds an equal producer benefit.
    """
    base_long  = global_sentiment.get("long_adjustment", 0)
    base_short = global_sentiment.get("short_adjustment", 0)

    if sector not in CRUDE_BENEFICIARY_SECTORS:
        return base_long, base_short

    crude_contribution = global_sentiment.get("crude_contribution", 0)
    if crude_contribution == 0:
        return base_long, base_short

    # Reverse the crude component for this sector and reclassify
    base_score    = global_sentiment.get("score", 0)
    sector_score  = max(-10.0, min(10.0, base_score - 2 * crude_contribution))
    _, long_adj, short_adj = _classify_and_adjust(sector_score)
    return long_adj, short_adj


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
