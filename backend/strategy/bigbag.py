"""
BigBag — Asymmetric Compounding Quality Screen
===============================================
Screens a curated universe of quality NSE stocks using yfinance .info
to compute available EMPIRE-aligned fundamental metrics.

EMPIRE scoring (available from yfinance):
  E — Earnings Quality  : ROE > 20%, EPS growth
  M — Moat Proxy        : Operating margin stability
  P — Promoter Proxy    : Revenue growth consistency
  I — Industry (fixed)  : Curated universe = industry tailwind assumed
  R — Runway            : Market cap size (smaller = more runway)
  E — Entry Price       : PEG < 1.5, P/E relative
"""

import logging
import numpy as np
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

logger = logging.getLogger(__name__)

# ─── Curated Quality Universe ─────────────────────────────────────────────────
BB_UNIVERSE = {
    # Core Compounders
    "RELIANCE.NS":    {"name": "Reliance Industries",       "sector": "Conglomerate",    "theme": "Energy+Digital+Retail", "fin": False},
    "TCS.NS":         {"name": "Tata Consultancy Svcs",     "sector": "IT Services",     "theme": "Digital India",        "fin": False},
    "INFY.NS":        {"name": "Infosys",                   "sector": "IT Services",     "theme": "Digital India",        "fin": False},
    "LTTS.NS":        {"name": "L&T Technology Svcs",       "sector": "IT Services",     "theme": "Digital India",        "fin": False},
    "PERSISTENT.NS":  {"name": "Persistent Systems",        "sector": "IT Services",     "theme": "Digital India",        "fin": False},
    "COFORGE.NS":     {"name": "Coforge",                   "sector": "IT Services",     "theme": "Digital India",        "fin": False},
    # Private Banks
    "HDFCBANK.NS":    {"name": "HDFC Bank",                 "sector": "Private Banks",   "theme": "Financialization",     "fin": True},
    "ICICIBANK.NS":   {"name": "ICICI Bank",                "sector": "Private Banks",   "theme": "Financialization",     "fin": True},
    "KOTAKBANK.NS":   {"name": "Kotak Mahindra Bank",       "sector": "Private Banks",   "theme": "Financialization",     "fin": True},
    "AXISBANK.NS":    {"name": "Axis Bank",                 "sector": "Private Banks",   "theme": "Financialization",     "fin": True},
    # AMC / Wealth
    "HDFCAMC.NS":     {"name": "HDFC AMC",                  "sector": "AMC/Wealth",      "theme": "Financialization",     "fin": True},
    "NIPPONLIFE.NS":  {"name": "Nippon Life AMC",           "sector": "AMC/Wealth",      "theme": "Financialization",     "fin": True},
    "ANGELONE.NS":    {"name": "Angel One",                 "sector": "Broking",         "theme": "Financialization",     "fin": True},
    # Insurance
    "SBILIFE.NS":     {"name": "SBI Life Insurance",        "sector": "Insurance",       "theme": "Financialization",     "fin": True},
    "HDFCLIFE.NS":    {"name": "HDFC Life Insurance",       "sector": "Insurance",       "theme": "Financialization",     "fin": True},
    # NBFC
    "BAJFINANCE.NS":  {"name": "Bajaj Finance",             "sector": "NBFC",            "theme": "Financialization",     "fin": True},
    "CHOLAFIN.NS":    {"name": "Cholamandalam Invest",      "sector": "NBFC",            "theme": "Financialization",     "fin": True},
    # Consumer / FMCG
    "HINDUNILVR.NS":  {"name": "Hindustan Unilever",        "sector": "FMCG",            "theme": "Premiumization",       "fin": False},
    "NESTLEIND.NS":   {"name": "Nestle India",              "sector": "FMCG",            "theme": "Premiumization",       "fin": False},
    "TITAN.NS":       {"name": "Titan Company",             "sector": "Consumer Disc.",  "theme": "Premiumization",       "fin": False},
    "DMART.NS":       {"name": "Avenue Supermarts",         "sector": "Retail",          "theme": "Consumer",             "fin": False},
    "TRENT.NS":       {"name": "Trent (Zara/Westside)",     "sector": "Retail",          "theme": "Consumer Disc.",       "fin": False},
    # Healthcare / Hospitals
    "SUNPHARMA.NS":   {"name": "Sun Pharmaceutical",        "sector": "Pharma",          "theme": "Healthcare",           "fin": False},
    "DRREDDY.NS":     {"name": "Dr Reddy's Labs",           "sector": "Pharma",          "theme": "Healthcare",           "fin": False},
    "APOLLOHOSP.NS":  {"name": "Apollo Hospitals",          "sector": "Hospitals",       "theme": "Healthcare Infra",     "fin": False},
    "MAXHEALTH.NS":   {"name": "Max Healthcare",            "sector": "Hospitals",       "theme": "Healthcare Infra",     "fin": False},
    "METROPOLIS.NS":  {"name": "Metropolis Healthcare",     "sector": "Diagnostics",     "theme": "Healthcare Infra",     "fin": False},
    # Capital Goods / Infra
    "LT.NS":          {"name": "Larsen & Toubro",           "sector": "Capital Goods",   "theme": "Capex/Infra",          "fin": False},
    "SIEMENS.NS":     {"name": "Siemens India",             "sector": "Capital Goods",   "theme": "Capex/Infra",          "fin": False},
    "ABB.NS":         {"name": "ABB India",                 "sector": "Capital Goods",   "theme": "Capex/Infra",          "fin": False},
    "CUMMINSIND.NS":  {"name": "Cummins India",             "sector": "Capital Goods",   "theme": "Capex/Infra",          "fin": False},
    "KAYNES.NS":      {"name": "Kaynes Technology",         "sector": "Electronics",     "theme": "Capex/Infra",          "fin": False},
    # Defence
    "HAL.NS":         {"name": "HAL",                       "sector": "Defence/Aero",    "theme": "Defence",              "fin": False},
    "BEL.NS":         {"name": "Bharat Electronics",        "sector": "Defence",         "theme": "Defence",              "fin": False},
    "COCHINSHIP.NS":  {"name": "Cochin Shipyard",           "sector": "Defence/Ship",    "theme": "Defence",              "fin": False},
    "MAZDOCK.NS":     {"name": "Mazagon Dock",              "sector": "Defence/Ship",    "theme": "Defence",              "fin": False},
    # Auto Ancillaries
    "BALKRISIND.NS":  {"name": "Balkrishna Industries",     "sector": "Auto Ancil.",     "theme": "Auto Ancil.",          "fin": False},
    "SUNDRMFAST.NS":  {"name": "Sundram Fasteners",         "sector": "Auto Ancil.",     "theme": "Auto Ancil.",          "fin": False},
    # Specialty Chemicals
    "PIDILITIND.NS":  {"name": "Pidilite Industries",       "sector": "Specialty Chem",  "theme": "Specialty Chem",       "fin": False},
    "AARTIIND.NS":    {"name": "Aarti Industries",          "sector": "Specialty Chem",  "theme": "Specialty Chem",       "fin": False},
    "CLEANSCIENCE.NS":{"name": "Clean Science & Tech",      "sector": "Specialty Chem",  "theme": "Specialty Chem",       "fin": False},
    # QSR / Consumer Disc
    "DEVYANI.NS":     {"name": "Devyani International",     "sector": "QSR",             "theme": "Consumer Disc.",       "fin": False},
    "SAPPHIRE.NS":    {"name": "Sapphire Foods",            "sector": "QSR",             "theme": "Consumer Disc.",       "fin": False},
    # Renewable Energy
    "TATAPOWER.NS":   {"name": "Tata Power",                "sector": "Renewable Energy","theme": "Energy Transition",    "fin": False},
    "ADANIGREEN.NS":  {"name": "Adani Green Energy",        "sector": "Renewable Energy","theme": "Energy Transition",    "fin": False},
    # Logistics
    "DELHIVERY.NS":   {"name": "Delhivery",                 "sector": "Logistics",       "theme": "Logistics",            "fin": False},
    "CONCOR.NS":      {"name": "Container Corp India",      "sector": "Logistics",       "theme": "Logistics",            "fin": False},
}

FINANCIAL_SECTORS = {"Private Banks", "NBFC", "Insurance", "AMC/Wealth", "Broking"}


def _sf(val, d=2):
    try:
        f = float(val)
        return None if (f != f or abs(f) == float("inf")) else round(f, d)
    except Exception:
        return None


def _empire_score(info: dict, is_financial: bool) -> tuple:
    """
    Compute EMPIRE score (0–100) from available yfinance .info fields.
    Returns (total_score, max_possible, breakdown_dict).
    """
    breakdown = {}
    total = 0
    possible = 0

    # E — Earnings Quality: ROE (20 pts)
    roe_raw = info.get("returnOnEquity")
    if roe_raw is not None:
        roe = _sf(roe_raw * 100)
        possible += 20
        if roe and roe >= 25:     pts = 20
        elif roe and roe >= 20:   pts = 15
        elif roe and roe >= 15:   pts = 8
        else:                     pts = 0
        breakdown["roe"] = {"score": pts, "max": 20, "value": roe, "label": "ROE"}
        total += pts

    # E — Earnings growth: EPS growth (20 pts)
    eg_raw = info.get("earningsGrowth")
    if eg_raw is not None:
        eg = _sf(eg_raw * 100)
        possible += 20
        if eg and eg >= 25:      pts = 20
        elif eg and eg >= 20:    pts = 15
        elif eg and eg >= 15:    pts = 8
        elif eg and eg >= 0:     pts = 3
        else:                    pts = 0
        breakdown["eps_growth"] = {"score": pts, "max": 20, "value": eg, "label": "EPS Growth"}
        total += pts

    # M — Moat: Operating margin (15 pts)
    om_raw = info.get("operatingMargins")
    if om_raw is not None:
        om = _sf(om_raw * 100)
        possible += 15
        if om and om >= 20:    pts = 15
        elif om and om >= 15:  pts = 10
        elif om and om >= 10:  pts = 5
        else:                  pts = 0
        breakdown["op_margin"] = {"score": pts, "max": 15, "value": om, "label": "Op. Margin"}
        total += pts

    # P — Revenue Growth proxy (15 pts)
    rg_raw = info.get("revenueGrowth")
    if rg_raw is not None:
        rg = _sf(rg_raw * 100)
        possible += 15
        if rg and rg >= 20:    pts = 15
        elif rg and rg >= 15:  pts = 10
        elif rg and rg >= 10:  pts = 5
        elif rg and rg >= 0:   pts = 2
        else:                  pts = 0
        breakdown["rev_growth"] = {"score": pts, "max": 15, "value": rg, "label": "Rev Growth"}
        total += pts

    # R — Debt/Equity (15 pts, skip for financials)
    if not is_financial:
        de_raw = info.get("debtToEquity")
        if de_raw is not None:
            # yfinance sometimes returns ratio * 100; normalize
            de = de_raw / 100 if de_raw > 5 else de_raw
            possible += 15
            if de <= 0.1:    pts = 15
            elif de <= 0.3:  pts = 10
            elif de <= 0.5:  pts = 5
            else:            pts = 0
            breakdown["de_ratio"] = {"score": pts, "max": 15, "value": _sf(de), "label": "D/E Ratio"}
            total += pts

    # E — Entry Price: PEG (15 pts)
    pe  = _sf(info.get("trailingPE"))
    eg2 = _sf(eg_raw * 100) if eg_raw else None
    if pe and eg2 and eg2 > 0:
        peg = pe / eg2
        possible += 15
        if peg < 1.0:    pts = 15
        elif peg < 1.5:  pts = 10
        elif peg < 2.0:  pts = 5
        else:            pts = 0
        breakdown["peg"] = {"score": pts, "max": 15, "value": _sf(peg), "label": "PEG Ratio"}
        total += pts

    if possible == 0:
        return 0, 0, breakdown

    # Normalize to 0–100
    score = round(total / possible * 100, 1)
    return score, possible, breakdown


def _conviction_tier(score: float) -> tuple:
    if score >= 70:
        return "TIER_1", "Tier 1 · 8–12%",  "#eab308"
    elif score >= 50:
        return "TIER_2", "Tier 2 · 4–6%",   "#4a9eff"
    else:
        return "TIER_3", "Watchlist · 2–3%", "#888"


def _process_bb_stock(sym: str, meta: dict) -> dict | None:
    try:
        t    = yf.Ticker(sym)
        info = t.info or {}

        # Prices
        cmp   = _sf(info.get("currentPrice") or info.get("regularMarketPrice"))
        w52h  = _sf(info.get("fiftyTwoWeekHigh"))
        w52l  = _sf(info.get("fiftyTwoWeekLow"))
        dist_52wh = _sf((cmp - w52h) / w52h * 100) if (cmp and w52h) else None
        dist_52wl = _sf((cmp - w52l) / w52l * 100) if (cmp and w52l) else None

        # Market cap in Crores
        mc    = info.get("marketCap")
        mc_cr = round(mc / 1e7, 0) if mc else None

        # Fundamental ratios (as displayed %)
        roe_raw = info.get("returnOnEquity")
        eg_raw  = info.get("earningsGrowth")
        rg_raw  = info.get("revenueGrowth")
        om_raw  = info.get("operatingMargins")
        nm_raw  = info.get("profitMargins")
        de_raw  = info.get("debtToEquity")

        roe = _sf(roe_raw * 100) if roe_raw is not None else None
        eps_growth = _sf(eg_raw * 100) if eg_raw is not None else None
        rev_growth = _sf(rg_raw * 100) if rg_raw is not None else None
        op_margin  = _sf(om_raw * 100) if om_raw is not None else None
        net_margin = _sf(nm_raw * 100) if nm_raw is not None else None
        # Normalize D/E
        if de_raw is not None:
            de_ratio = _sf(de_raw / 100 if de_raw > 5 else de_raw)
        else:
            de_ratio = None

        pe = _sf(info.get("trailingPE"))
        pb = _sf(info.get("priceToBook"))
        peg = _sf(pe / eps_growth) if (pe and eps_growth and eps_growth > 0) else None

        is_fin = meta.get("fin", False) or meta.get("sector") in FINANCIAL_SECTORS

        empire_score, empire_possible, empire_bd = _empire_score(info, is_fin)
        conviction, conv_label, conv_color = _conviction_tier(empire_score)

        return {
            "symbol":         sym.replace(".NS", "").replace("^", ""),
            "raw_symbol":     sym,
            "name":           meta.get("name", info.get("longName", sym)),
            "sector":         meta.get("sector", info.get("sector", "—")),
            "theme":          meta.get("theme", "—"),
            "is_financial":   is_fin,
            # Price
            "cmp":            cmp,
            "w52h":           w52h,
            "w52l":           w52l,
            "dist_52wh":      dist_52wh,
            "dist_52wl":      dist_52wl,
            "market_cap_cr":  mc_cr,
            # Fundamentals
            "roe":            roe,
            "de_ratio":       de_ratio,
            "pe":             pe,
            "pb":             pb,
            "peg":            peg,
            "eps_growth":     eps_growth,
            "rev_growth":     rev_growth,
            "op_margin":      op_margin,
            "net_margin":     net_margin,
            # EMPIRE
            "empire_score":   empire_score,
            "empire_possible": empire_possible,
            "empire_breakdown": empire_bd,
            "conviction":     conviction,
            "conviction_label": conv_label,
            "conviction_color": conv_color,
        }
    except Exception as e:
        logger.warning("BigBag(%s): %s", sym, e)
        return None


def run_bigbag(_universe: dict = None) -> dict:
    """Screen quality compounders using EMPIRE framework metrics."""
    try:
        universe = _universe or BB_UNIVERSE
        logger.info("[BigBag] Screening %d quality candidates…", len(universe))
        results = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(_process_bb_stock, sym, meta): sym
                    for sym, meta in universe.items()}
            for fut in as_completed(futs):
                r = fut.result()
                if r is not None:
                    results.append(r)

        results.sort(key=lambda x: (-x["empire_score"], x["symbol"]))

        total    = len(results)
        tier1    = sum(1 for s in results if s["conviction"] == "TIER_1")
        tier2    = sum(1 for s in results if s["conviction"] == "TIER_2")
        high_roe = sum(1 for s in results if s["roe"] and s["roe"] >= 20)
        low_de   = sum(1 for s in results if not s["is_financial"] and
                       s["de_ratio"] is not None and s["de_ratio"] < 0.3)
        good_peg = sum(1 for s in results if s["peg"] and s["peg"] < 1.5)
        near_52wh= sum(1 for s in results if s["dist_52wh"] is not None and s["dist_52wh"] >= -10)

        return {
            "status":   "success",
            "run_date": datetime.now().strftime("%Y-%m-%d"),
            "run_time": datetime.now().strftime("%H:%M:%S"),
            "stocks":   results,
            "summary": {
                "total":     total,
                "tier1":     tier1,
                "tier2":     tier2,
                "high_roe":  high_roe,
                "low_de":    low_de,
                "good_peg":  good_peg,
                "near_52wh": near_52wh,
            },
        }
    except Exception as e:
        logger.error("[BigBag] Error: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
