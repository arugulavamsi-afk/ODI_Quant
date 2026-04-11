"""
IntraContra — VWAP Momentum + Institutional Order Flow
=======================================================
Curated 20-stock watchlist of high-liquidity NSE/F&O names.
Pre-market prep analysis using EOD daily data:
  • Key levels  — PDH / PDL / PDC / Weekly Pivot / R1 / S1
  • VWAP proxy  — 20-day rolling typical-price × volume VWAP
  • Indicators  — ATR(14), RSI(14), 9 EMA, 21 EMA
  • Setups      — ORB Long/Short, VWAP Reversion, Gap Play
  • Sizing      — 2-tier risk system (1% / 2% / 0.5%)
"""

import logging
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# ─── Curated Watchlist ────────────────────────────────────────────────────────
# 20 high-liquidity Nifty 50 / F&O active stocks
IC_WATCHLIST = {
    "RELIANCE.NS":   {"name": "Reliance Industries",      "sector": "Energy"},
    "HDFCBANK.NS":   {"name": "HDFC Bank",                "sector": "Banking"},
    "ICICIBANK.NS":  {"name": "ICICI Bank",               "sector": "Banking"},
    "INFY.NS":       {"name": "Infosys",                  "sector": "IT"},
    "TATAMOTORS.NS": {"name": "Tata Motors",              "sector": "Auto"},
    "BAJFINANCE.NS": {"name": "Bajaj Finance",            "sector": "Finance"},
    "AXISBANK.NS":   {"name": "Axis Bank",                "sector": "Banking"},
    "SBIN.NS":       {"name": "State Bank of India",      "sector": "Banking"},
    "LT.NS":         {"name": "Larsen & Toubro",          "sector": "Infra"},
    "KOTAKBANK.NS":  {"name": "Kotak Mahindra Bank",      "sector": "Banking"},
    "TCS.NS":        {"name": "Tata Consultancy Services","sector": "IT"},
    "WIPRO.NS":      {"name": "Wipro",                    "sector": "IT"},
    "MARUTI.NS":     {"name": "Maruti Suzuki",            "sector": "Auto"},
    "BHARTIARTL.NS": {"name": "Bharti Airtel",            "sector": "Telecom"},
    "SUNPHARMA.NS":  {"name": "Sun Pharmaceutical",       "sector": "Pharma"},
    "NTPC.NS":       {"name": "NTPC",                     "sector": "Energy"},
    "ADANIPORTS.NS": {"name": "Adani Ports & SEZ",        "sector": "Infra"},
    "M&M.NS":        {"name": "Mahindra & Mahindra",      "sector": "Auto"},
    "HINDUNILVR.NS": {"name": "Hindustan Unilever",       "sector": "FMCG"},
    "TATASTEEL.NS":  {"name": "Tata Steel",               "sector": "Metals"},
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sf(val, d=2):
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, d)
    except Exception:
        return None


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _rsi(s: pd.Series, period: int = 14) -> pd.Series:
    d     = s.diff()
    gain  = d.clip(lower=0)
    loss  = (-d).clip(lower=0)
    ag    = gain.ewm(alpha=1/period, adjust=False).mean()
    al    = loss.ewm(alpha=1/period, adjust=False).mean()
    rs    = ag / al.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


# ─── Per-Stock Analysis ───────────────────────────────────────────────────────

def _process_stock(sym: str, info: dict) -> dict | None:
    try:
        t  = yf.Ticker(sym)
        df = t.history(period="6mo", auto_adjust=True)
        if df is None or len(df) < 30:
            return None

        df.columns = [c.strip() for c in df.columns]
        df = df.dropna(subset=["Close", "Volume"]).sort_index()

        close  = df["Close"]
        high   = df["High"]
        low    = df["Low"]
        opens  = df["Open"]
        volume = df["Volume"]

        # ── Key daily levels ─────────────────────────────────────────────────
        # "Previous day" = last complete session (iloc[-1] is yesterday's EOD)
        pdh  = _sf(high.iloc[-1])
        pdl  = _sf(low.iloc[-1])
        pdc  = _sf(close.iloc[-1])
        pdo  = _sf(opens.iloc[-1])

        # Day before yesterday for comparison
        cmp  = _sf(close.iloc[-1])   # last known close
        prev = _sf(close.iloc[-2]) if len(close) >= 2 else cmp
        chg_pct = _sf((cmp - prev) / prev * 100) if prev else None

        # Gap from two-days-ago close to yesterday's open
        gap_pct = _sf((pdo - prev) / prev * 100) if (prev and pdo) else None

        # ── Indicators ───────────────────────────────────────────────────────
        atr14    = _atr(high, low, close, 14)
        last_atr = _sf(atr14.iloc[-1])
        atr_pct  = _sf(last_atr / cmp * 100) if (last_atr and cmp) else None

        avg20v   = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean())
        avg20v_l = round(avg20v / 100_000, 1)      # in lakhs

        # 20-day VWAP proxy
        tp      = (high + low + close) / 3
        vwap_20 = _sf((tp * volume).rolling(20).sum().iloc[-1] /
                      volume.rolling(20).sum().iloc[-1])

        rsi_val = _sf(_rsi(close).iloc[-1])
        e9      = _sf(_ema(close, 9).iloc[-1])
        e21     = _sf(_ema(close, 21).iloc[-1])

        # ── Weekly Pivot Levels ───────────────────────────────────────────────
        wk = df.resample("W").agg({"High": "max", "Low": "min", "Close": "last"})
        wk_pivot = wk_r1 = wk_s1 = wk_r2 = wk_s2 = None
        if len(wk) >= 2:
            wh = float(wk["High"].iloc[-2])
            wl = float(wk["Low"].iloc[-2])
            wc = float(wk["Close"].iloc[-2])
            p  = (wh + wl + wc) / 3
            wk_pivot = _sf(p)
            wk_r1    = _sf(2 * p - wl)
            wk_s1    = _sf(2 * p - wh)
            wk_r2    = _sf(p + (wh - wl))
            wk_s2    = _sf(p - (wh - wl))

        # ── Qualification ─────────────────────────────────────────────────────
        qual_atr    = atr_pct is not None and atr_pct >= 1.5
        qual_vol    = avg20v >= 5_000_000          # 50 lakh shares
        qualified   = qual_atr and qual_vol

        # VWAP deviation
        vwap_dev_pct = _sf((cmp - vwap_20) / vwap_20 * 100) if vwap_20 else None

        # ── Setup Detection ───────────────────────────────────────────────────
        setups = []

        if pdh and pdl and cmp and vwap_20:

            # ORB Long: CMP within 2% above PDH  →  potential upside breakout
            if 0 <= (cmp - pdh) / pdh * 100 <= 2.0 and cmp > vwap_20 and e9 and cmp >= e9:
                entry = _sf(pdh * 1.002)
                sl    = _sf(min(vwap_20, pdh * 0.995))
                risk  = max((entry - sl), 0.01) if (entry and sl) else 1
                setups.append({
                    "setup": "ORB_LONG", "setup_label": "ORB Long",
                    "icon": "🟢", "window": "9:30–10:15 AM",
                    "entry": entry, "stop_loss": sl,
                    "target1": _sf(entry + risk * 2),
                    "target2": _sf(entry + risk * 3),
                    "note": f"Break above PDH ₹{pdh} · VWAP ₹{vwap_20} support · 9 EMA aligned",
                    "rr": "1:2 / 1:3",
                })

            # ORB Short: CMP within 2% below PDL  →  potential breakdown
            if 0 <= (pdl - cmp) / pdl * 100 <= 2.0 and cmp < vwap_20 and e9 and cmp <= e9:
                entry = _sf(pdl * 0.998)
                sl    = _sf(max(vwap_20, pdl * 1.005))
                risk  = max((sl - entry), 0.01) if (entry and sl) else 1
                setups.append({
                    "setup": "ORB_SHORT", "setup_label": "ORB Short",
                    "icon": "🔴", "window": "9:30–10:15 AM",
                    "entry": entry, "stop_loss": sl,
                    "target1": _sf(entry - risk * 2),
                    "target2": _sf(entry - risk * 3),
                    "note": f"Break below PDL ₹{pdl} · VWAP ₹{vwap_20} resistance · 9 EMA below",
                    "rr": "1:2 / 1:3",
                })

            # VWAP Reversion Long: price > 1.5% below VWAP + RSI oversold
            if vwap_dev_pct is not None and vwap_dev_pct <= -1.5 and rsi_val and rsi_val < 38:
                swing_low = _sf(low.iloc[-5:].min())
                sl   = _sf(swing_low * 0.99) if swing_low else _sf(cmp * 0.985)
                risk = max(cmp - sl, 0.01) if sl else 1
                setups.append({
                    "setup": "VWAP_REVERSION_LONG", "setup_label": "VWAP Reversion ↑",
                    "icon": "↩️", "window": "Any (not 11:30–12:30)",
                    "entry": cmp, "stop_loss": sl,
                    "target1": vwap_20,
                    "target2": _sf(vwap_20 + abs(vwap_dev_pct / 100 * vwap_20) * 0.5),
                    "note": f"{abs(vwap_dev_pct):.1f}% below VWAP · RSI {rsi_val:.0f} oversold · Scalp to VWAP",
                    "rr": "VWAP target",
                })

            # VWAP Reversion Short: price > 1.5% above VWAP + RSI overbought
            if vwap_dev_pct is not None and vwap_dev_pct >= 1.5 and rsi_val and rsi_val > 62:
                swing_hi = _sf(high.iloc[-5:].max())
                sl   = _sf(swing_hi * 1.01) if swing_hi else _sf(cmp * 1.015)
                risk = max(sl - cmp, 0.01) if sl else 1
                setups.append({
                    "setup": "VWAP_REVERSION_SHORT", "setup_label": "VWAP Reversion ↓",
                    "icon": "↪️", "window": "Any (not 11:30–12:30)",
                    "entry": cmp, "stop_loss": sl,
                    "target1": vwap_20,
                    "target2": _sf(vwap_20 - abs(vwap_dev_pct / 100 * vwap_20) * 0.5),
                    "note": f"{vwap_dev_pct:.1f}% above VWAP · RSI {rsi_val:.0f} overbought · Scalp to VWAP",
                    "rr": "VWAP target",
                })

        # Gap plays (based on yesterday's open vs close-before)
        if gap_pct is not None and pdh and pdl and pdc:
            if gap_pct >= 0.8:
                sl  = _sf(prev)  # gap fill = bearish reversal level
                risk = max(pdo - sl, 0.01) if (pdo and sl) else 1
                setups.append({
                    "setup": "GAP_UP", "setup_label": f"Gap Up +{gap_pct:.1f}%",
                    "icon": "⬆️", "window": "9:15–9:30 (observe), enter 9:30+",
                    "entry": _sf(pdo * 1.001), "stop_loss": sl,
                    "target1": _sf(pdo + risk * 2),
                    "target2": _sf(pdo + risk * 3),
                    "note": f"Opened ₹{pdo} vs prev close ₹{prev} · Watch ORB on gap · SL = gap fill",
                    "rr": "1:2 if ORB holds",
                })
            elif gap_pct <= -0.8:
                sl  = _sf(prev)
                risk = max(sl - pdo, 0.01) if (pdo and sl) else 1
                setups.append({
                    "setup": "GAP_DOWN", "setup_label": f"Gap Down {gap_pct:.1f}%",
                    "icon": "⬇️", "window": "9:15–9:30 (observe), enter 9:30+",
                    "entry": _sf(pdo * 0.999), "stop_loss": sl,
                    "target1": _sf(pdo - risk * 2),
                    "target2": _sf(pdo - risk * 3),
                    "note": f"Opened ₹{pdo} vs prev close ₹{prev} · Short if gap doesn't fill · SL = gap fill",
                    "rr": "1:2 if breakdown holds",
                })

        # Sort: directional ORB first
        order = ["ORB_LONG", "ORB_SHORT", "GAP_UP", "GAP_DOWN",
                 "VWAP_REVERSION_LONG", "VWAP_REVERSION_SHORT"]
        setups.sort(key=lambda x: order.index(x["setup"]) if x["setup"] in order else 99)

        # Trend label
        above_vwap = cmp > vwap_20 if (cmp and vwap_20) else None
        ema_bullish = (e9 and e21 and e9 > e21 and cmp >= e9)

        return {
            "symbol":        sym.replace(".NS", ""),
            "raw_symbol":    sym,
            "name":          info.get("name", sym),
            "sector":        info.get("sector", "—"),
            "cmp":           cmp,
            "chg_pct":       chg_pct,
            "gap_pct":       gap_pct,
            # Key levels
            "pdh":           pdh,
            "pdl":           pdl,
            "pdc":           pdc,
            "vwap_20":       vwap_20,
            "vwap_dev_pct":  vwap_dev_pct,
            "wk_pivot":      wk_pivot,
            "wk_r1":         wk_r1,
            "wk_s1":         wk_s1,
            "wk_r2":         wk_r2,
            "wk_s2":         wk_s2,
            # Indicators
            "atr_14":        last_atr,
            "atr_pct":       atr_pct,
            "avg_vol_l":     avg20v_l,
            "rsi_14":        rsi_val,
            "ema9":          e9,
            "ema21":         e21,
            # Status
            "above_vwap":    above_vwap,
            "ema_bullish":   ema_bullish,
            "qualified":     qualified,
            "qual_atr":      qual_atr,
            "qual_vol":      qual_vol,
            # Setups
            "setups":        setups,
            "setup_count":   len(setups),
            "has_setup":     len(setups) > 0,
        }
    except Exception as e:
        logger.warning(f"IntraContra({sym}): {e}")
        return None


# ─── Market Context ───────────────────────────────────────────────────────────

def _market_context() -> dict:
    ctx = {
        "nifty_price": None, "nifty_chg_pct": None,
        "nifty_pdh": None, "nifty_pdl": None,
        "nifty_vwap": None, "nifty_rsi": None,
        "vix_value": None, "vix_status": "UNKNOWN",
        "trade_bias": "NEUTRAL", "trade_bias_color": "yellow",
    }
    try:
        df = yf.Ticker("^NSEI").history(period="3mo", auto_adjust=True).dropna(subset=["Close"]).sort_index()
        if len(df) >= 10:
            close = df["Close"]; high = df["High"]; low = df["Low"]
            lc   = float(close.iloc[-1])
            prev = float(close.iloc[-2])
            tp   = (high + low + close) / 3
            vol  = df.get("Volume", pd.Series(1, index=df.index))
            vwap = _sf((tp * vol).rolling(20).sum().iloc[-1] / vol.rolling(20).sum().iloc[-1])
            ctx.update({
                "nifty_price":   _sf(lc),
                "nifty_chg_pct": _sf((lc - prev) / prev * 100),
                "nifty_pdh":     _sf(float(high.iloc[-1])),
                "nifty_pdl":     _sf(float(low.iloc[-1])),
                "nifty_vwap":    vwap,
                "nifty_rsi":     _sf(_rsi(close).iloc[-1]),
            })
            if vwap:
                bias = "LONG" if lc > vwap else "CAUTION"
                col  = "green" if lc > vwap else "red"
                ctx.update({"trade_bias": bias, "trade_bias_color": col})
    except Exception as e:
        logger.warning(f"Market context error: {e}")
    try:
        vdf = yf.Ticker("^INDIAVIX").history(period="1mo", auto_adjust=True)
        if vdf is not None and not vdf.empty:
            vv = _sf(vdf["Close"].dropna().iloc[-1])
            ctx["vix_value"]  = vv
            ctx["vix_status"] = ("LOW" if vv and vv < 13 else
                                  "MODERATE" if vv and vv <= 18 else
                                  "ELEVATED" if vv and vv <= 22 else "HIGH")
    except Exception as e:
        logger.warning(f"VIX error: {e}")
    return ctx


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def run_intra_contra(_universe: dict = None) -> dict:
    """Run pre-market analysis on the 20-stock curated watchlist."""
    try:
        logger.info("[IntraContra] Market context…")
        market_ctx = _market_context()

        logger.info("[IntraContra] Processing %d watchlist stocks…", len(IC_WATCHLIST))
        results = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(_process_stock, sym, info): sym
                    for sym, info in IC_WATCHLIST.items()}
            for fut in as_completed(futs):
                r = fut.result()
                if r is not None:
                    results.append(r)

        results.sort(key=lambda x: (-x["setup_count"], -int(x["qualified"]),
                                    x["symbol"]))

        total      = len(results)
        qualified  = sum(1 for s in results if s["qualified"])
        w_setups   = sum(1 for s in results if s["has_setup"])
        orb_long   = sum(1 for s in results for st in s["setups"] if st["setup"] == "ORB_LONG")
        orb_short  = sum(1 for s in results for st in s["setups"] if st["setup"] == "ORB_SHORT")
        vwap_rev   = sum(1 for s in results for st in s["setups"]
                         if st["setup"] in ("VWAP_REVERSION_LONG", "VWAP_REVERSION_SHORT"))
        gap_plays  = sum(1 for s in results for st in s["setups"]
                         if st["setup"] in ("GAP_UP", "GAP_DOWN"))
        above_vwap = sum(1 for s in results if s.get("above_vwap"))

        return {
            "status":         "success",
            "run_date":       datetime.now().strftime("%Y-%m-%d"),
            "run_time":       datetime.now().strftime("%H:%M:%S"),
            "market_context": market_ctx,
            "stocks":         results,
            "summary": {
                "total":       total,
                "qualified":   qualified,
                "with_setups": w_setups,
                "orb_long":    orb_long,
                "orb_short":   orb_short,
                "vwap_rev":    vwap_rev,
                "gap_plays":   gap_plays,
                "above_vwap":  above_vwap,
            },
        }
    except Exception as e:
        logger.error(f"[IntraContra] Error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
