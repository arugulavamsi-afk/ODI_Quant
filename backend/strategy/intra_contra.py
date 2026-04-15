"""
IntraContra — VWAP Momentum + Institutional Order Flow
=======================================================
Curated 20-stock watchlist of high-liquidity NSE/F&O names.
Pre-market prep analysis using EOD daily data:
  • Key levels    — PDH / PDL / PDC / Weekly Pivot / R1 / S1
  • Session TP    — (PDH + PDL + PDC) / 3 — prior session typical price.
                    This is the EOD approximation of the session VWAP (the
                    volume-weighted average price for that single day). It is
                    the correct intraday anchor for mean-reversion setups.
  • 20D VWAP      — 20-day rolling VWAP. Used ONLY as a swing trend reference
                    (above = bullish swing bias, below = bearish). NOT used as
                    an intraday entry/exit level — it resets too slowly.
  • Indicators    — ATR(14), RSI(14), 9 EMA, 21 EMA
  • Setups        — PDH Breakout / PDL Breakdown, Session TP Reversion, Gap Play
  • Sizing        — 2-tier risk system (1% / 2% / 0.5%)

DATA LIMITATION — NO TRUE ORB:
  A genuine Opening Range Breakout (ORB) requires intraday 1-min or 5-min data
  to define the high/low of the opening range (NSE regular session: 9:15 AM onward).
  yfinance free tier does not reliably supply sub-daily historical data.

  What this module computes instead:
    PDH_BREAKOUT  — price is within 2% above PDH; watch for continuation above PDH at open.
    PDL_BREAKDOWN — price is within 2% below PDL; watch for continuation below PDL at open.

  These are EOD-level pre-market alerts, NOT live intraday signals.
  The trader must verify the actual opening range and volume in the live session
  before executing. Do not treat entry prices as pre-market limit orders —
  they are reference levels requiring live confirmation at open.
"""

import logging
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone, timedelta, time as dtime
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# IST = UTC+5:30 (no external timezone library needed)
IST = timezone(timedelta(hours=5, minutes=30))

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


# ─── Live / Intraday Helpers ──────────────────────────────────────────────────

def _market_session_info() -> dict:
    """Returns current NSE market session state based on IST wall-clock time."""
    now = datetime.now(IST)
    is_weekday = now.weekday() < 5          # Mon=0 … Fri=4
    t = now.time()
    market_open  = dtime(9, 15)
    market_close = dtime(15, 30)
    orb_end      = dtime(9, 30)
    is_open      = is_weekday and market_open <= t <= market_close
    orb_complete = is_weekday and t >= orb_end
    elapsed_min  = None
    if is_open:
        open_dt = now.replace(hour=9, minute=15, second=0, microsecond=0)
        elapsed_min = int((now - open_dt).total_seconds() / 60)
    return {
        "is_open":            is_open,
        "orb_complete":       orb_complete,
        "ist_time":           now.strftime("%H:%M IST"),
        "ist_date":           now.strftime("%Y-%m-%d"),
        "session_elapsed_min": elapsed_min,
    }


def _fetch_intraday(sym: str) -> "pd.DataFrame | None":
    """Fetch today's 5-min OHLCV from yfinance. Returns None on failure."""
    try:
        df = yf.Ticker(sym).history(period="1d", interval="5m", auto_adjust=True)
        if df is None or df.empty:
            return None
        df.columns = [c.strip() for c in df.columns]
        df = df.dropna(subset=["Close", "Volume"])
        return df if not df.empty else None
    except Exception:
        return None


def _is_today_data(df: pd.DataFrame) -> bool:
    """True if the latest row in df is from today (IST calendar date)."""
    try:
        ts = df.index[-1]
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            d = ts.astimezone(IST).date()
        else:
            d = ts.date()
        return d == datetime.now(IST).date()
    except Exception:
        return False


def _to_ist_times(df: pd.DataFrame):
    """Return a list of time objects (IST) for each row in df."""
    idx = df.index
    if hasattr(idx[0], "tzinfo") and idx[0].tzinfo is not None:
        return [ts.astimezone(IST).time() for ts in idx]
    return [ts.time() for ts in idx]


def _compute_orb(df_5m: pd.DataFrame) -> "tuple[float|None, float|None]":
    """
    Opening Range = high/low of NSE 9:15–9:29 AM candles (first 15 min).
    Returns (orb_high, orb_low) or (None, None).
    """
    try:
        times = _to_ist_times(df_5m)
        mask  = [(dtime(9, 15) <= t < dtime(9, 30)) for t in times]
        orb   = df_5m[mask]
        if orb.empty:
            return None, None
        return _sf(float(orb["High"].max())), _sf(float(orb["Low"].min()))
    except Exception:
        return None, None


def _compute_intraday_vwap(df_5m: pd.DataFrame) -> "float | None":
    """Cumulative session VWAP anchored at today's open (9:15 AM)."""
    try:
        vol = df_5m["Volume"]
        if vol.sum() == 0:
            return None
        tp = (df_5m["High"] + df_5m["Low"] + df_5m["Close"]) / 3
        return _sf(float((tp * vol).cumsum().iloc[-1] / vol.cumsum().iloc[-1]))
    except Exception:
        return None


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

        # 20-day rolling VWAP — swing trend reference ONLY.
        # Tells you whether the stock is in a bullish or bearish multi-day regime.
        # DO NOT use as an intraday entry/exit anchor — it moves too slowly.
        tp       = (high + low + close) / 3
        vwap_20d = _sf((tp * volume).rolling(20).sum().iloc[-1] /
                       volume.rolling(20).sum().iloc[-1])

        # Prior Session Typical Price (Session TP) = (PDH + PDL + PDC) / 3
        # This is the EOD approximation of the session VWAP — the price level
        # where institutional volume centred during the prior trading session.
        # It resets every session, making it the correct intraday mean-reversion
        # anchor. Deviation from Session TP is what drives early-session reversions.
        session_tp     = _sf((pdh + pdl + pdc) / 3) if (pdh and pdl and pdc) else None
        session_tp_dev = _sf((cmp - session_tp) / session_tp * 100) if session_tp else None

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

        # ── Live Intraday Enrichment ───────────────────────────────────────────
        # Fetch today's 5-min bars. When the market is open (or recently closed
        # with today's data available), override CMP with the live last price so
        # that all downstream setup conditions use a real-time price level.
        # Also computes: true ORB high/low and cumulative intraday VWAP.
        is_live       = False
        live_price    = None
        orb_high      = None
        orb_low       = None
        intraday_vwap = None
        live_volume   = None
        orb_complete  = False

        df_5m = _fetch_intraday(sym)
        if df_5m is not None and _is_today_data(df_5m):
            is_live    = True
            lp         = _sf(float(df_5m["Close"].iloc[-1]))
            live_price = lp
            live_volume = int(df_5m["Volume"].sum())
            intraday_vwap = _compute_intraday_vwap(df_5m)
            orb_high, orb_low = _compute_orb(df_5m)

            # Override EOD CMP with live price for all setup detection below
            if lp:
                cmp = lp
                session_tp_dev = _sf((cmp - session_tp) / session_tp * 100) if session_tp else None

            # ORB is complete once any candle at or after 9:30 AM IST is present
            try:
                times = _to_ist_times(df_5m)
                orb_complete = any(t >= dtime(9, 30) for t in times)
            except Exception:
                orb_complete = False

        # ── Setup Detection ───────────────────────────────────────────────────
        setups = []

        if pdh and pdl and cmp:

            # PDH Breakout: CMP closed within 2% above PDH — bullish continuation setup.
            # This is a pre-market alert, NOT a live ORB. A true ORB requires intraday
            # 1-min/5-min data (NSE opens 9:15 AM) to define the opening range correctly.
            # Using PDH as a proxy is reasonable for EOD prep but the trader must confirm:
            #   (a) the opening range on the live session holds above PDH, and
            #   (b) opening volume is strong before entering.
            # Filter: swing bias bullish (CMP above 20D VWAP) + 9 EMA aligned.
            # SL: 0.5% below PDH — intraday noise buffer. 20D VWAP NOT used as SL.
            if 0 <= (cmp - pdh) / pdh * 100 <= 2.0 and vwap_20d and cmp > vwap_20d and e9 and cmp >= e9:
                entry = _sf(pdh * 1.002)
                sl    = _sf(pdh * 0.995)           # 0.5% below PDH — intraday noise buffer
                risk  = max((entry - sl), 0.01) if (entry and sl) else 1
                stp_note = f"Session TP ₹{session_tp}" if session_tp else ""
                setups.append({
                    "setup": "PDH_BREAKOUT", "setup_label": "PDH Breakout",
                    "icon": "🟢",
                    "window": "Live confirm at open · NSE 9:15 AM+",
                    "data_note": "EOD alert — verify opening range and volume in live session before entry",
                    "entry": entry, "stop_loss": sl,
                    "target1": _sf(entry + risk * 2),
                    "target2": _sf(entry + risk * 3),
                    "note": (f"Closed within 2% of PDH ₹{pdh} · SL just below PDH · "
                             f"20D VWAP ₹{vwap_20d} (swing bias: bullish) · "
                             f"{stp_note} · 9 EMA aligned · "
                             f"Confirm live: opening range holding above PDH + vol surge"),
                    "rr": "1:2 / 1:3",
                })

            # PDL Breakdown: CMP closed within 2% below PDL — bearish continuation setup.
            # Same data limitation as above — EOD proxy only.
            # Trader must confirm the live opening range is holding below PDL at open.
            # Filter: swing bias bearish (CMP below 20D VWAP) + 9 EMA below.
            # SL: 0.5% above PDL. 20D VWAP NOT used as SL.
            if 0 <= (pdl - cmp) / pdl * 100 <= 2.0 and vwap_20d and cmp < vwap_20d and e9 and cmp <= e9:
                entry = _sf(pdl * 0.998)
                sl    = _sf(pdl * 1.005)           # 0.5% above PDL — intraday noise buffer
                risk  = max((sl - entry), 0.01) if (entry and sl) else 1
                stp_note = f"Session TP ₹{session_tp}" if session_tp else ""
                setups.append({
                    "setup": "PDL_BREAKDOWN", "setup_label": "PDL Breakdown",
                    "icon": "🔴",
                    "window": "Live confirm at open · NSE 9:15 AM+",
                    "data_note": "EOD alert — verify opening range and volume in live session before entry",
                    "entry": entry, "stop_loss": sl,
                    "target1": _sf(entry - risk * 2),
                    "target2": _sf(entry - risk * 3),
                    "note": (f"Closed within 2% of PDL ₹{pdl} · SL just above PDL · "
                             f"20D VWAP ₹{vwap_20d} (swing bias: bearish) · "
                             f"{stp_note} · 9 EMA below · "
                             f"Confirm live: opening range holding below PDL + vol surge"),
                    "rr": "1:2 / 1:3",
                })

            # Session TP Reversion Long
            # Trigger: CMP is > 1.5% below the prior session's typical price (PDH+PDL+PDC)/3
            #          AND RSI < 38 confirms oversold reading at this session deviation.
            # This is coherent: the prior session TP is where institutional money averaged
            # in yesterday. When price drops 1.5%+ below that level early in the session,
            # it represents an opportunity to fade the move back toward that anchor.
            # Target: session_tp — the natural intraday mean-reversion target.
            # Window: morning session only (9:30–11:30 AM). Mean-reversion dynamics
            #         weaken after the first 90 minutes as new price discovery sets in.
            if session_tp and session_tp_dev is not None and session_tp_dev <= -1.5 and rsi_val and rsi_val < 38:
                swing_low = _sf(low.iloc[-3:].min())
                sl   = _sf(swing_low * 0.99) if swing_low else _sf(cmp * 0.985)
                risk = max(cmp - sl, 0.01) if sl else 1
                setups.append({
                    "setup": "SESSION_REVERSION_LONG", "setup_label": "Session TP Reversion ↑",
                    "icon": "↩️", "window": "9:30–11:30 AM only",
                    "entry": cmp, "stop_loss": sl,
                    "target1": session_tp,
                    "target2": _sf(session_tp + abs(session_tp_dev / 100 * session_tp) * 0.3),
                    "note": (f"{abs(session_tp_dev):.1f}% below Session TP ₹{session_tp} · "
                             f"RSI {rsi_val:.0f} oversold · Fade back to prior session anchor · "
                             f"Exit by 11:30 AM regardless"),
                    "rr": "Session TP target",
                })

            # Session TP Reversion Short
            # Mirror of above: CMP > 1.5% above session TP + RSI > 62 overbought.
            if session_tp and session_tp_dev is not None and session_tp_dev >= 1.5 and rsi_val and rsi_val > 62:
                swing_hi = _sf(high.iloc[-3:].max())
                sl   = _sf(swing_hi * 1.01) if swing_hi else _sf(cmp * 1.015)
                risk = max(sl - cmp, 0.01) if sl else 1
                setups.append({
                    "setup": "SESSION_REVERSION_SHORT", "setup_label": "Session TP Reversion ↓",
                    "icon": "↪️", "window": "9:30–11:30 AM only",
                    "entry": cmp, "stop_loss": sl,
                    "target1": session_tp,
                    "target2": _sf(session_tp - abs(session_tp_dev / 100 * session_tp) * 0.3),
                    "note": (f"{session_tp_dev:.1f}% above Session TP ₹{session_tp} · "
                             f"RSI {rsi_val:.0f} overbought · Fade back to prior session anchor · "
                             f"Exit by 11:30 AM regardless"),
                    "rr": "Session TP target",
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
                    "note": f"Opened ₹{pdo} vs prev close ₹{prev} · Watch first 15-min range for direction · SL = gap fill",
                    "rr": "1:2 if opening range holds",
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

        # ── ORB Setups — live only, generated after ORB window (≥ 9:30 AM) ──────
        # A true Opening Range Breakout requires live intraday data.
        # Condition: live CMP has confirmed above/below the 9:15-9:29 range,
        #            AND price is on the correct side of the intraday VWAP.
        if is_live and orb_complete and orb_high and orb_low:
            orb_range = orb_high - orb_low
            if orb_range > 0.01:

                # ORB Long: live CMP broke and is ABOVE ORB High
                if (cmp > orb_high and intraday_vwap and cmp > intraday_vwap):
                    entry = _sf(orb_high * 1.001)
                    sl    = orb_low
                    risk  = max(entry - sl, 0.01) if (entry and sl) else orb_range
                    setups.append({
                        "setup": "ORB_LONG", "setup_label": "ORB Breakout ↑",
                        "icon": "🚀",
                        "window": "9:30–11:00 AM · LIVE confirmed",
                        "data_note": "LIVE — price confirmed above Opening Range High",
                        "entry": entry, "stop_loss": sl,
                        "target1": _sf(entry + risk * 2),
                        "target2": _sf(entry + risk * 3),
                        "note": (f"ORB High ₹{orb_high} · ORB Low ₹{orb_low} · "
                                 f"Range ₹{_sf(orb_range)} · "
                                 f"Intraday VWAP ₹{intraday_vwap} (price above = bullish) · "
                                 f"SL at ORB Low · PDH ₹{pdh} next resistance"),
                        "rr": "1:2 / 1:3",
                    })

                # ORB Short: live CMP broke and is BELOW ORB Low
                elif (cmp < orb_low and intraday_vwap and cmp < intraday_vwap):
                    entry = _sf(orb_low * 0.999)
                    sl    = orb_high
                    risk  = max(sl - entry, 0.01) if (entry and sl) else orb_range
                    setups.append({
                        "setup": "ORB_SHORT", "setup_label": "ORB Breakdown ↓",
                        "icon": "📉",
                        "window": "9:30–11:00 AM · LIVE confirmed",
                        "data_note": "LIVE — price confirmed below Opening Range Low",
                        "entry": entry, "stop_loss": sl,
                        "target1": _sf(entry - risk * 2),
                        "target2": _sf(entry - risk * 3),
                        "note": (f"ORB Low ₹{orb_low} · ORB High ₹{orb_high} · "
                                 f"Range ₹{_sf(orb_range)} · "
                                 f"Intraday VWAP ₹{intraday_vwap} (price below = bearish) · "
                                 f"SL at ORB High · PDL ₹{pdl} next support"),
                        "rr": "1:2 / 1:3",
                    })

        # Sort: ORB first (live, highest confidence), then PDH/PDL level alerts,
        # then gap plays, then session reversion (timing discipline required)
        order = ["ORB_LONG", "ORB_SHORT",
                 "PDH_BREAKOUT", "PDL_BREAKDOWN", "GAP_UP", "GAP_DOWN",
                 "SESSION_REVERSION_LONG", "SESSION_REVERSION_SHORT"]
        setups.sort(key=lambda x: order.index(x["setup"]) if x["setup"] in order else 99)

        # Swing bias: price vs 20D rolling VWAP (multi-session trend reference)
        above_20d_vwap = cmp > vwap_20d if (cmp and vwap_20d) else None
        # Intraday bias: price vs prior session TP (session anchor)
        above_session_tp = cmp > session_tp if (cmp and session_tp) else None
        ema_bullish = (e9 and e21 and e9 > e21 and cmp >= e9)

        return {
            "symbol":          sym.replace(".NS", ""),
            "raw_symbol":      sym,
            "name":            info.get("name", sym),
            "sector":          info.get("sector", "—"),
            "cmp":             cmp,
            "chg_pct":         chg_pct,
            "gap_pct":         gap_pct,
            # Key levels
            "pdh":             pdh,
            "pdl":             pdl,
            "pdc":             pdc,
            # Session TP — prior session VWAP approximation (intraday anchor)
            "session_tp":      session_tp,
            "session_tp_dev":  session_tp_dev,
            # 20D rolling VWAP — swing trend reference only
            "vwap_20d":        vwap_20d,
            "wk_pivot":        wk_pivot,
            "wk_r1":           wk_r1,
            "wk_s1":           wk_s1,
            "wk_r2":           wk_r2,
            "wk_s2":           wk_s2,
            # Indicators
            "atr_14":          last_atr,
            "atr_pct":         atr_pct,
            "avg_vol_l":       avg20v_l,
            "rsi_14":          rsi_val,
            "ema9":            e9,
            "ema21":           e21,
            # Bias flags
            "above_20d_vwap":   above_20d_vwap,    # swing bias (20D rolling)
            "above_session_tp": above_session_tp,   # intraday bias (prior session TP)
            "ema_bullish":      ema_bullish,
            "qualified":        qualified,
            "qual_atr":         qual_atr,
            "qual_vol":         qual_vol,
            # Live intraday data (populated when market is open / today's 5m data exists)
            "is_live":          is_live,
            "live_price":       live_price,
            "orb_high":         orb_high,
            "orb_low":          orb_low,
            "intraday_vwap":    intraday_vwap,
            "live_volume":      live_volume,
            "orb_complete":     orb_complete,
            # Setups
            "setups":           setups,
            "setup_count":      len(setups),
            "has_setup":        len(setups) > 0,
        }
    except Exception as e:
        logger.warning(f"IntraContra({sym}): {e}")
        return None


# ─── Market Context ───────────────────────────────────────────────────────────

def _market_context() -> dict:
    ctx = {
        "nifty_price": None, "nifty_chg_pct": None,
        "nifty_pdh": None, "nifty_pdl": None,
        "nifty_session_tp": None,   # prior session TP = (PDH+PDL+PDC)/3
        "nifty_vwap_20d": None,     # 20D rolling VWAP — swing trend reference
        "nifty_rsi": None,
        "vix_value": None, "vix_status": "UNKNOWN",
        "trade_bias": "NEUTRAL", "trade_bias_color": "yellow",
    }
    try:
        df = yf.Ticker("^NSEI").history(period="3mo", auto_adjust=True).dropna(subset=["Close"]).sort_index()
        if len(df) >= 10:
            close = df["Close"]; high = df["High"]; low = df["Low"]
            lc    = float(close.iloc[-1])
            prev  = float(close.iloc[-2])
            pdh_n = float(high.iloc[-1])
            pdl_n = float(low.iloc[-1])
            pdc_n = float(close.iloc[-1])
            # Prior session TP — intraday mean-reversion anchor for NIFTY
            nifty_stp = _sf((pdh_n + pdl_n + pdc_n) / 3)
            # 20D rolling VWAP — swing trend reference
            tp    = (high + low + close) / 3
            vol   = df.get("Volume", pd.Series(1, index=df.index))
            vwap_20d = _sf((tp * vol).rolling(20).sum().iloc[-1] / vol.rolling(20).sum().iloc[-1])
            ctx.update({
                "nifty_price":     _sf(lc),
                "nifty_chg_pct":   _sf((lc - prev) / prev * 100),
                "nifty_pdh":       _sf(pdh_n),
                "nifty_pdl":       _sf(pdl_n),
                "nifty_session_tp": nifty_stp,
                "nifty_vwap_20d":  vwap_20d,
                "nifty_rsi":       _sf(_rsi(close).iloc[-1]),
            })
            # Swing bias: NIFTY price vs 20D rolling VWAP
            if vwap_20d:
                bias = "LONG" if lc > vwap_20d else "CAUTION"
                col  = "green" if lc > vwap_20d else "red"
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
    # Market session info (IST wall-clock)
    session = _market_session_info()
    ctx.update({
        "is_market_open":      session["is_open"],
        "orb_complete":        session["orb_complete"],
        "ist_time":            session["ist_time"],
        "ist_date":            session["ist_date"],
        "session_elapsed_min": session["session_elapsed_min"],
    })
    return ctx


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def run_intra_contra(_universe: dict = None) -> dict:
    """
    Run pre-market analysis on a dynamic watchlist sourced from the Screener.

    Watchlist resolution (in priority order):
      1. HIGH_PROB_LONG + HIGH_PROB_SHORT + WATCHLIST stocks from the latest
         Screener run (stored in SQLite by the daily pipeline).
      2. The fixed IC_WATCHLIST baseline — always merged in so the 20 most
         liquid F&O names are never dropped even if the Screener misses them.
      3. Pure IC_WATCHLIST fallback if the Screener has never been run (DB empty).

    This means IntraContra's coverage grows automatically as the Screener
    identifies new setups — no manual watchlist maintenance needed.
    """
    try:
        logger.info("[IntraContra] Market context…")
        market_ctx = _market_context()

        # ── Build dynamic watchlist ───────────────────────────────────────────
        watchlist        = {}
        watchlist_source = "default"
        screener_date    = None

        try:
            from storage.db import get_high_prob_stocks
            db_result = get_high_prob_stocks(limit=40)

            # get_high_prob_stocks returns (dict, date) or empty dict on no data
            if isinstance(db_result, tuple):
                db_stocks, screener_date = db_result
            else:
                db_stocks = db_result

            if db_stocks:
                watchlist        = db_stocks
                watchlist_source = "screener"
                logger.info(
                    "[IntraContra] Dynamic watchlist: %d stocks from Screener (%s)",
                    len(db_stocks), screener_date,
                )
        except Exception as e:
            logger.warning("[IntraContra] Could not load Screener results from DB: %s", e)

        # Always merge the baseline IC_WATCHLIST so the 20 core liquid names
        # are present regardless of whether the Screener caught them.
        # Screener stocks take priority (they carry richer category metadata).
        if watchlist:
            merged = {**IC_WATCHLIST, **watchlist}   # screener overwrites on collision
            logger.info(
                "[IntraContra] Final watchlist: %d stocks (%d from Screener + IC baseline, deduplicated)",
                len(merged), len(watchlist),
            )
        else:
            merged           = IC_WATCHLIST
            watchlist_source = "default"
            logger.info(
                "[IntraContra] No Screener data in DB — using fixed IC_WATCHLIST (%d stocks)",
                len(merged),
            )

        # ── Process all watchlist stocks in parallel ──────────────────────────
        logger.info("[IntraContra] Processing %d stocks…", len(merged))
        results = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(_process_stock, sym, info): sym
                    for sym, info in merged.items()}
            for fut in as_completed(futs):
                r = fut.result()
                if r is not None:
                    sym_key = r["raw_symbol"]
                    if sym_key in watchlist:
                        r["watchlist_source"]  = "screener"
                        r["screener_category"] = watchlist[sym_key].get("category", "")
                    else:
                        r["watchlist_source"]  = "default"
                        r["screener_category"] = ""
                    results.append(r)

        # Sort: setups first, then qualified, then screener-sourced (higher priority), then alpha
        results.sort(key=lambda x: (
            -x["setup_count"],
            -int(x["qualified"]),
            0 if x["watchlist_source"] == "screener" else 1,
            x["symbol"],
        ))

        total         = len(results)
        from_screener = sum(1 for s in results if s.get("watchlist_source") == "screener")
        qualified_n   = sum(1 for s in results if s["qualified"])
        w_setups      = sum(1 for s in results if s["has_setup"])
        pdh_breakout  = sum(1 for s in results for st in s["setups"] if st["setup"] == "PDH_BREAKOUT")
        pdl_breakdown = sum(1 for s in results for st in s["setups"] if st["setup"] == "PDL_BREAKDOWN")
        sess_rev      = sum(1 for s in results for st in s["setups"]
                            if st["setup"] in ("SESSION_REVERSION_LONG", "SESSION_REVERSION_SHORT"))
        gap_plays     = sum(1 for s in results for st in s["setups"]
                            if st["setup"] in ("GAP_UP", "GAP_DOWN"))
        orb_plays     = sum(1 for s in results for st in s["setups"]
                            if st["setup"] in ("ORB_LONG", "ORB_SHORT"))
        live_count    = sum(1 for s in results if s.get("is_live"))
        above_stp     = sum(1 for s in results if s.get("above_session_tp"))
        above_20dvwap = sum(1 for s in results if s.get("above_20d_vwap"))

        now_ist = datetime.now(IST)
        return {
            "status":           "success",
            "run_date":         now_ist.strftime("%Y-%m-%d"),
            "run_time":         now_ist.strftime("%H:%M:%S IST"),
            "is_live":          live_count > 0,
            "watchlist_source": watchlist_source,
            "screener_date":    screener_date,
            "market_context":   market_ctx,
            "market_session":   _market_session_info(),
            "stocks":           results,
            "summary": {
                "total":            total,
                "from_screener":    from_screener,
                "from_baseline":    total - from_screener,
                "qualified":        qualified_n,
                "with_setups":      w_setups,
                "orb_plays":        orb_plays,
                "pdh_breakout":     pdh_breakout,
                "pdl_breakdown":    pdl_breakdown,
                "session_rev":      sess_rev,
                "gap_plays":        gap_plays,
                "live_count":       live_count,
                "above_session_tp": above_stp,
                "above_20d_vwap":   above_20dvwap,
            },
        }
    except Exception as e:
        logger.error(f"[IntraContra] Error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
