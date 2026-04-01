"""
NIFTY50 Options Strategy Engine.

Selects the optimal strategy (BUY_CE / BUY_PE / spreads) based on
directional bias + IV environment, computes Black-Scholes Greeks &
approximate premiums, and builds a complete trade plan.

Note: premiums / Greeks use 30-day historical volatility as an IV proxy.
Always verify live premiums on the NSE option chain before trading.
"""
import math
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

NIFTY_LOT_SIZE   = 50        # NIFTY F&O lot size (as of 2024 NSE circular)
NIFTY_STRIKE_GAP = 50        # Strike price interval
RISK_FREE_RATE   = 0.065     # ~6.5 % Indian repo rate


# ── Expiry helpers ────────────────────────────────────────────────────────────

def _next_thursday() -> tuple[str, int]:
    """Return (expiry_date YYYY-MM-DD, days_to_expiry)."""
    today      = datetime.now()
    days_ahead = 3 - today.weekday()   # Thursday = weekday 3
    if days_ahead <= 0:
        days_ahead += 7
    expiry = today + timedelta(days=days_ahead)
    return expiry.strftime("%Y-%m-%d"), days_ahead


# ── Black-Scholes pricing + Greeks ───────────────────────────────────────────

def _ncdf(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _npdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs(S: float, K: float, T: float, r: float, sigma: float, opt: str) -> dict:
    """
    Black-Scholes option value and first-order Greeks.

    Args:
        S     : Spot price
        K     : Strike price
        T     : Time to expiry (years)
        r     : Risk-free rate (decimal)
        sigma : Volatility (decimal, e.g. 0.15 for 15 %)
        opt   : "CE" (call) or "PE" (put)

    Returns dict with keys: premium, delta, theta, gamma.
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {"premium": 0.0, "delta": 0.0, "theta": 0.0, "gamma": 0.0}
    try:
        sqrtT = math.sqrt(T)
        d1    = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrtT)
        d2    = d1 - sigma * sqrtT
        disc  = math.exp(-r * T)

        if opt == "CE":
            premium = S * _ncdf(d1) - K * disc * _ncdf(d2)
            delta   = _ncdf(d1)
            theta   = (-(S * _npdf(d1) * sigma) / (2 * sqrtT)
                       - r * K * disc * _ncdf(d2)) / 365.0
        else:  # PE
            premium = K * disc * _ncdf(-d2) - S * _ncdf(-d1)
            delta   = _ncdf(d1) - 1.0
            theta   = (-(S * _npdf(d1) * sigma) / (2 * sqrtT)
                       + r * K * disc * _ncdf(-d2)) / 365.0

        gamma = _npdf(d1) / (S * sigma * sqrtT)

        return {
            "premium": round(max(0.0, premium), 2),
            "delta":   round(delta,  3),
            "theta":   round(theta,  3),
            "gamma":   round(gamma,  6),
        }
    except Exception as exc:
        logger.warning("Black-Scholes error: %s", exc)
        return {"premium": 0.0, "delta": 0.0, "theta": 0.0, "gamma": 0.0}


# ── IV classification ─────────────────────────────────────────────────────────

def _iv_level(hv: float) -> str:
    if hv < 12.0:  return "VERY_LOW"
    if hv < 16.0:  return "LOW"
    if hv < 22.0:  return "MODERATE"
    if hv < 30.0:  return "HIGH"
    return "VERY_HIGH"


# ── Strategy selection ────────────────────────────────────────────────────────

def _pick_strategy(expected_move: str, iv_lv: str) -> dict:
    """Choose optimal options strategy based on direction + IV environment."""
    if expected_move in ("STRONG_BULLISH", "BULLISH"):
        if iv_lv in ("HIGH", "VERY_HIGH"):
            return {
                "name":        "Bull Call Spread",
                "code":        "BULL_CALL_SPREAD",
                "direction":   "LONG",
                "option_type": "CE",
                "rationale": (
                    f"{iv_lv.replace('_', ' ')} IV — outright call buying is expensive. "
                    "Bull Call Spread (buy lower strike CE, sell higher strike CE) "
                    "reduces net debit and theta drag while retaining bullish exposure."
                ),
                "legs": 2,
            }
        else:
            return {
                "name":        "Buy Call (CE)",
                "code":        "BUY_CE",
                "direction":   "LONG",
                "option_type": "CE",
                "rationale": (
                    f"Bullish bias confirmed. {iv_lv.replace('_', ' ')} IV makes option "
                    "buying favourable — low premium outlay, minimal theta drag. "
                    "Outright ATM call maximises directional upside."
                ),
                "legs": 1,
            }

    elif expected_move in ("STRONG_BEARISH", "BEARISH"):
        if iv_lv in ("HIGH", "VERY_HIGH"):
            return {
                "name":        "Bear Put Spread",
                "code":        "BEAR_PUT_SPREAD",
                "direction":   "SHORT",
                "option_type": "PE",
                "rationale": (
                    f"{iv_lv.replace('_', ' ')} IV — outright put buying is expensive. "
                    "Bear Put Spread (buy higher strike PE, sell lower strike PE) "
                    "reduces net debit and protects against IV crush."
                ),
                "legs": 2,
            }
        else:
            return {
                "name":        "Buy Put (PE)",
                "code":        "BUY_PE",
                "direction":   "SHORT",
                "option_type": "PE",
                "rationale": (
                    f"Bearish bias confirmed. {iv_lv.replace('_', ' ')} IV makes option "
                    "buying favourable — low premium, low theta drag. "
                    "Outright ATM put maximises downside capture."
                ),
                "legs": 1,
            }

    else:
        return {
            "name":        "No Trade — Wait",
            "code":        "NO_TRADE",
            "direction":   "NEUTRAL",
            "option_type": "NONE",
            "rationale": (
                "NIFTY is in a consolidation / neutral zone — no clear directional edge. "
                "Avoid directional option positions. Wait for a confirmed PDH or PDL "
                "breakout before entering. Watch global cues at market open."
            ),
            "legs": 0,
        }


# ── Strike selection ──────────────────────────────────────────────────────────

def _select_strikes(spot: float, opt_type: str) -> dict:
    """Return ATM and adjacent NIFTY strikes (50-pt grid)."""
    gap = NIFTY_STRIKE_GAP
    atm = round(spot / gap) * gap

    if opt_type == "CE":
        itm   = atm - gap
        otm   = atm + gap
        hedge = atm + 2 * gap   # short leg for bull call spread
    elif opt_type == "PE":
        itm   = atm + gap
        otm   = atm - gap
        hedge = atm - 2 * gap   # short leg for bear put spread
    else:
        return {"atm": atm, "buy_strike": atm, "hedge_strike": None, "strike_type": "ATM"}

    return {
        "atm":          atm,
        "itm_strike":   itm,
        "otm_strike":   otm,
        "buy_strike":   atm,    # intraday default: ATM
        "hedge_strike": hedge,
        "strike_type":  "ATM",
    }


# ── Trade plan ────────────────────────────────────────────────────────────────

def _build_trade_plan(
    direction: str, spot: float, atr: float,
    pdh: float, pdl: float, net_premium: float,
) -> dict:
    """Build option-level and index-level entry/SL/target plan."""
    empty = {k: 0 for k in [
        "entry_premium", "stop_loss_premium", "target1_premium",
        "target2_premium", "sl_points", "risk_reward",
        "index_entry_trigger", "index_stop_loss",
        "index_target1", "index_target2", "max_loss_per_lot",
    ]}
    if net_premium <= 0:
        return empty

    entry   = round(net_premium, 2)
    sl_pts  = round(entry * 0.35, 2)          # SL = 35 % of premium
    sl      = round(entry - sl_pts, 2)
    t1      = round(entry + sl_pts * 2, 2)    # 2:1 R:R target
    t2      = round(entry + sl_pts * 3, 2)    # 3:1 R:R target

    if direction == "LONG":
        idx_entry = round(pdh * 1.001, 2)     # enter above PDH
        idx_sl    = round(pdl, 2)
        idx_t1    = round(idx_entry + atr, 2)
        idx_t2    = round(idx_entry + atr * 2, 2)
    else:
        idx_entry = round(pdl * 0.999, 2)     # enter below PDL
        idx_sl    = round(pdh, 2)
        idx_t1    = round(idx_entry - atr, 2)
        idx_t2    = round(idx_entry - atr * 2, 2)

    return {
        "entry_premium":       entry,
        "stop_loss_premium":   sl,
        "target1_premium":     t1,
        "target2_premium":     t2,
        "sl_points":           sl_pts,
        "risk_reward":         2.0,
        "index_entry_trigger": idx_entry,
        "index_stop_loss":     idx_sl,
        "index_target1":       idx_t1,
        "index_target2":       idx_t2,
        "max_loss_per_lot":    round(sl_pts * NIFTY_LOT_SIZE, 2),
    }


# ── Explanation builder ───────────────────────────────────────────────────────

def _build_explanation(
    na: dict, gs: dict, iv_lv: str, dte: int,
) -> list:
    reasons = []
    em    = na.get("expected_move",    "NEUTRAL")
    tb    = na.get("trend_bias",       "NEUTRAL")
    ma    = na.get("ma_alignment",     "NEUTRAL")
    bo    = na.get("breakout_status",  "INSIDE_RANGE")
    vs    = na.get("volume_spike",     1.0)
    cs    = na.get("closing_strength", 50.0)
    ms    = na.get("market_structure", "MIXED")
    gs_cl = gs.get("classification",   "NEUTRAL")

    # Direction
    if em in ("STRONG_BULLISH", "BULLISH"):
        reasons.append(
            f"NIFTY shows {tb.replace('_', ' ')} bias — "
            f"MA alignment: {ma.replace('_', ' ')}"
        )
    elif em in ("STRONG_BEARISH", "BEARISH"):
        reasons.append(
            f"NIFTY shows {tb.replace('_', ' ')} bias — "
            f"MA alignment: {ma.replace('_', ' ')}"
        )
    else:
        reasons.append("NIFTY is range-bound / neutral — no clear directional edge")

    # Price action breakout
    bo_map = {
        "BREAKOUT_ABOVE_PDH":   "Closed above Previous Day High — bullish momentum confirmed",
        "BREAKDOWN_BELOW_PDL":  "Closed below Previous Day Low — bearish momentum confirmed",
        "NEAR_PDH":             "Trading near Previous Day High — watch for breakout at open",
        "NEAR_PDL":             "Trading near Previous Day Low — watch for breakdown at open",
        "20D_BREAKOUT":         "20-day range breakout in progress — strong momentum signal",
        "20D_BREAKDOWN":        "20-day range breakdown in progress — strong bearish signal",
        "INSIDE_RANGE":         "Price inside prior day range — wait for directional confirmation",
    }
    if bo in bo_map:
        reasons.append(bo_map[bo])

    # Market structure
    if ms == "HH_HL":
        reasons.append("Higher Highs + Higher Lows — bullish market structure intact")
    elif ms == "LH_LL":
        reasons.append("Lower Highs + Lower Lows — bearish market structure confirmed")

    # Volume
    if vs >= 2.0:
        reasons.append(f"Strong volume surge ({vs:.1f}× average) — confirms directional conviction")
    elif vs >= 1.5:
        reasons.append(f"Above-average volume ({vs:.1f}×) — supports the directional move")

    # Closing strength
    if cs >= 75:
        reasons.append(f"Strong closing at {cs:.0f} % of day range — bulls in control")
    elif cs <= 25:
        reasons.append(f"Weak closing at {cs:.0f} % of day range — bears in control")

    # Global sentiment
    gs_map = {
        "STRONG_BULLISH": "Global markets strongly bullish — positive tailwind for NIFTY",
        "MILD_BULLISH":   "Global markets mildly bullish — supportive backdrop for longs",
        "NEUTRAL":        "Global markets neutral — no strong external catalyst",
        "MILD_BEARISH":   "Global markets mildly bearish — moderate headwind for NIFTY",
        "STRONG_BEARISH": "Global markets strongly bearish — significant headwind for NIFTY",
    }
    if gs_cl in gs_map:
        reasons.append(gs_map[gs_cl])

    # IV context
    iv_map = {
        "VERY_LOW":  "IV very low — excellent environment for buying options (minimal time decay)",
        "LOW":       "IV low — favourable for option buying (low premium, low theta drag)",
        "MODERATE":  "IV moderate — standard option buying; monitor premium decay",
        "HIGH":      "IV elevated — prefer spreads to cap premium outlay and IV risk",
        "VERY_HIGH": "IV very high — avoid outright option buying; use defined-risk spreads only",
    }
    if iv_lv in iv_map:
        reasons.append(iv_map[iv_lv])

    # DTE
    if dte >= 3:
        reasons.append(
            f"Weekly expiry in {dte} days — adequate time for intraday or 1–2 day swing play"
        )
    else:
        reasons.append(
            f"Expiry in {dte} day{'s' if dte != 1 else ''} — "
            "very short DTE; intraday-only; avoid holding overnight"
        )

    return reasons


# ── Public API ────────────────────────────────────────────────────────────────

def generate_options_analysis(nifty_analysis: dict, global_sentiment: dict) -> dict:
    """
    Full NIFTY50 options analysis.

    Args:
        nifty_analysis  : Output from nifty_analyzer.analyze_nifty().
        global_sentiment: Output from calculate_global_score().

    Returns:
        Dict with strategy, IV environment, strike selection,
        Greeks, trade plan, and human-readable explanation.
    """
    spot = nifty_analysis.get("current_price", 22000.0)
    atr  = nifty_analysis.get("atr",  100.0)
    hv30 = nifty_analysis.get("hv_30", 15.0)
    em   = nifty_analysis.get("expected_move", "NEUTRAL")
    pdh  = nifty_analysis.get("pdh",  spot + atr)
    pdl  = nifty_analysis.get("pdl",  spot - atr)

    iv_lv = _iv_level(hv30)
    sigma = hv30 / 100.0          # decimal volatility

    strategy = _pick_strategy(em, iv_lv)
    opt_type = strategy["option_type"]

    expiry, dte = _next_thursday()
    T = max(dte, 1) / 365.0

    strikes = _select_strikes(spot, opt_type)
    buy_strike   = strikes.get("buy_strike",   round(spot / 50) * 50)
    hedge_strike = strikes.get("hedge_strike")

    # Buy leg Greeks
    if opt_type != "NONE":
        buy_g = _bs(spot, buy_strike, T, RISK_FREE_RATE, sigma, opt_type)
    else:
        buy_g = {"premium": 0.0, "delta": 0.0, "theta": 0.0, "gamma": 0.0}

    buy_premium = buy_g.get("premium", 0.0)

    # Hedge leg Greeks (for spreads)
    hedge_g       = {}
    hedge_premium = 0.0
    net_premium   = buy_premium

    if strategy["code"] in ("BULL_CALL_SPREAD", "BEAR_PUT_SPREAD") and hedge_strike:
        hedge_g       = _bs(spot, hedge_strike, T, RISK_FREE_RATE, sigma, opt_type)
        hedge_premium = hedge_g.get("premium", 0.0)
        net_premium   = round(buy_premium - hedge_premium, 2)

    net_premium = max(net_premium, 0.0)

    trade_plan = _build_trade_plan(
        strategy["direction"], spot, atr, pdh, pdl, net_premium
    )

    explanation = _build_explanation(nifty_analysis, global_sentiment, iv_lv, dte)

    net_delta = round(
        buy_g.get("delta", 0.0) - (hedge_g.get("delta", 0.0) if hedge_g else 0.0), 3
    )
    net_theta = round(
        buy_g.get("theta", 0.0) - (hedge_g.get("theta", 0.0) if hedge_g else 0.0), 3
    )

    return {
        "strategy": strategy,
        "iv_environment": {
            "hv_30":    hv30,
            "iv_level": iv_lv,
        },
        "strike_selection": {
            "spot":          spot,
            "expiry":        expiry,
            "dte":           dte,
            "atm_strike":    strikes.get("atm"),
            "buy_strike":    buy_strike,
            "hedge_strike":  hedge_strike,
            "strike_type":   strikes.get("strike_type", "ATM"),
            "option_type":   opt_type,
            "lot_size":      NIFTY_LOT_SIZE,
        },
        "greeks": {
            "buy_leg": {
                "strike":  buy_strike,
                "premium": buy_g.get("premium", 0.0),
                "delta":   buy_g.get("delta",   0.0),
                "theta":   buy_g.get("theta",   0.0),
                "gamma":   buy_g.get("gamma",   0.0),
            },
            "hedge_leg": {
                "strike":  hedge_strike,
                "premium": hedge_g.get("premium", 0.0),
                "delta":   hedge_g.get("delta",   0.0),
                "theta":   hedge_g.get("theta",   0.0),
            } if hedge_strike and hedge_g else None,
            "net_premium": round(net_premium, 2),
            "net_delta":   net_delta,
            "net_theta":   net_theta,
        },
        "trade_plan": trade_plan,
        "explanation": explanation,
        "disclaimer": (
            "Premiums and Greeks are estimated using Black-Scholes with 30-day "
            "historical volatility as an IV proxy. Verify live premiums on the "
            "NSE option chain before placing any trade."
        ),
    }
