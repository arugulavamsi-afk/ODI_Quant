"""
"Ride the Trend, Snipe the Pullback" — Strategy Engine
=======================================================
Phases implemented:
  1  Market Context Filter  — Nifty 50 vs 50 EMA, India VIX allocation
  2  Sector Rotation        — 4-week RS scores for Nifty sectoral indices
  3  Quality Gate           — 200 EMA, volume, sector alignment
  4  Pattern Arsenal        — EMA Pullback | Base Breakout | Gap-up Reversal
  5  Risk / Position Sizing — returned with every pattern match
  6  Scale-out Levels       — 1:2 R:R trigger, 10 EMA trail
"""

import logging
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# ─── Sectoral index symbols ───────────────────────────────────────────────────
SECTOR_INDICES = {
    "^NSEBANK":   "Banking",
    "^CNXIT":     "IT",
    "^CNXPHARMA": "Pharma",
    "^CNXAUTO":   "Auto",
    "^CNXREALTY": "Realty",
    "^CNXFMCG":   "FMCG",
    "^CNXMETAL":  "Metals",
    "^CNXINFRA":  "Infra",
    "^CNXENERGY": "Energy",
    "^CNXFINANCE":"Finance",
}

# Map stock universe sector → sectoral index sector name
UNIVERSE_TO_IDX_SECTOR = {
    "Banking":    "Banking",
    "IT":         "IT",
    "Pharma":     "Pharma",
    "Healthcare": "Pharma",
    "Auto":       "Auto",
    "Finance":    "Finance",
    "FMCG":       "FMCG",
    "Consumer":   "FMCG",
    "Energy":     "Energy",
    "Metals":     "Metals",
    "Infra":      "Infra",
    "Telecom":    "Infra",
    "Media":      "Infra",
}

# Quarterly sector calendar
SECTOR_CALENDAR = {
    "Q1 (Apr–Jun)": ["IT", "Pharma", "FMCG"],
    "Q2 (Jul–Sep)": ["Banking", "Auto", "Infra"],
    "Q3 (Oct–Dec)": ["Realty", "Infra", "Metals"],
    "Q4 (Jan–Mar)": ["Banking", "Finance", "Metals"],
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sf(val, default=None, decimals=2):
    """Safe float conversion — returns None for NaN / Inf."""
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return default
        return round(f, decimals)
    except Exception:
        return default


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _fetch(symbol: str, period: str = "3mo") -> pd.DataFrame | None:
    try:
        t = yf.Ticker(symbol)
        df = t.history(period=period, auto_adjust=True)
        if df is None or df.empty or len(df) < 10:
            return None
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df.columns = [c.strip() for c in df.columns]
        return df
    except Exception as e:
        logger.warning(f"Fetch {symbol} error: {e}")
        return None


# ─── Phase 1 — Market Context ─────────────────────────────────────────────────

def phase1_market_context() -> dict:
    """
    Returns:
      nifty_price, nifty_50ema, above_50ema, nifty_change_pct,
      vix_value, vix_status, allocation_pct, vix_label,
      market_bias (LONG / NEUTRAL / CAUTION)
    """
    result = {
        "nifty_price": None,
        "nifty_50ema": None,
        "nifty_200ema": None,
        "above_50ema": None,
        "nifty_change_pct": None,
        "vix_value": None,
        "vix_status": "UNKNOWN",
        "allocation_pct": 100,
        "vix_label": "–",
        "market_bias": "NEUTRAL",
        "bias_color": "yellow",
        "status": "ok",
    }

    # Nifty 50
    nifty_df = _fetch("^NSEI", period="1y")
    if nifty_df is not None and len(nifty_df) >= 50:
        close = nifty_df["Close"]
        ema50  = _ema(close, 50)
        lc     = _sf(close.iloc[-1])
        le50   = _sf(ema50.iloc[-1])
        result.update({"nifty_price": lc, "nifty_50ema": le50})

        if lc is not None and le50 is not None:
            result["above_50ema"] = lc > le50

        if len(close) >= 200:
            result["nifty_200ema"] = _sf(_ema(close, 200).iloc[-1])

        if len(close) >= 2:
            prev = _sf(close.iloc[-2])
            if prev and lc:
                result["nifty_change_pct"] = _sf((lc - prev) / prev * 100)

    # India VIX
    vix_df = _fetch("^INDIAVIX", period="1mo")
    if vix_df is not None and not vix_df.empty:
        vv = _sf(vix_df["Close"].iloc[-1])
        result["vix_value"] = vv
        if vv is not None:
            if vv < 18:
                result.update({"vix_status": "LOW",      "allocation_pct": 100,
                                "vix_label": "Full Allocation — VIX < 18"})
            elif vv <= 22:
                result.update({"vix_status": "ELEVATED", "allocation_pct": 70,
                                "vix_label": "70 % Allocation — VIX 18–22"})
            else:
                result.update({"vix_status": "HIGH",     "allocation_pct": 0,
                                "vix_label": "Cash / Short Hedges — VIX > 22"})

    # Final bias
    above     = result.get("above_50ema")
    vix_status = result.get("vix_status", "LOW")
    if above is True and vix_status == "LOW":
        result.update({"market_bias": "LONG",    "bias_color": "green"})
    elif above is False or vix_status == "HIGH":
        result.update({"market_bias": "CAUTION", "bias_color": "red"})
    else:
        result.update({"market_bias": "NEUTRAL", "bias_color": "yellow"})

    return result


# ─── Phase 2 — Sector Rotation ────────────────────────────────────────────────

def phase2_sector_rotation() -> dict:
    """
    Returns ranked sector list with 4-week and 1-week returns,
    relative-strength score vs Nifty, and momentum direction.
    """
    nifty_df = _fetch("^NSEI", period="3mo")
    if nifty_df is None or len(nifty_df) < 21:
        return {"sectors": [], "top_sectors": [], "status": "error"}

    nc  = nifty_df["Close"]
    n4w = (float(nc.iloc[-1]) / float(nc.iloc[-21]) - 1) * 100 if len(nc) > 21 else 0.0
    n1w = (float(nc.iloc[-1]) / float(nc.iloc[-6])  - 1) * 100 if len(nc) > 6  else 0.0

    sectors = []
    for symbol, name in SECTOR_INDICES.items():
        df = _fetch(symbol, period="3mo")
        if df is None or len(df) < 21:
            sectors.append({"symbol": symbol, "sector": name,
                             "return_4w": None, "return_1w": None,
                             "rs_score": None, "momentum": "—", "rank": 99})
            continue

        c   = df["Close"]
        r4w = (float(c.iloc[-1]) / float(c.iloc[-21]) - 1) * 100 if len(c) > 21 else 0.0
        r1w = (float(c.iloc[-1]) / float(c.iloc[-6])  - 1) * 100 if len(c) > 6  else 0.0
        rs  = r4w - n4w

        # Momentum: is 1-week pace above the average weekly pace over 4 weeks?
        avg_wk = r4w / 4.0
        momentum = "ACCELERATING" if r1w > avg_wk else "DECELERATING"

        sectors.append({
            "symbol":    symbol,
            "sector":    name,
            "return_4w": round(r4w, 2),
            "return_1w": round(r1w, 2),
            "rs_score":  round(rs, 2),
            "momentum":  momentum,
            "rank":      0,
        })

    # Rank valid entries
    valid = [s for s in sectors if s["rs_score"] is not None]
    valid.sort(key=lambda x: x["rs_score"], reverse=True)
    for i, s in enumerate(valid):
        s["rank"] = i + 1

    top_sectors = [s["sector"] for s in valid[:3]]

    # Current quarter hint
    month = datetime.now().month
    if 4 <= month <= 6:
        qkey = "Q1 (Apr–Jun)"
    elif 7 <= month <= 9:
        qkey = "Q2 (Jul–Sep)"
    elif 10 <= month <= 12:
        qkey = "Q3 (Oct–Dec)"
    else:
        qkey = "Q4 (Jan–Mar)"

    return {
        "sectors":         valid,
        "top_sectors":     top_sectors,
        "nifty_4w_return": round(n4w, 2),
        "nifty_1w_return": round(n1w, 2),
        "current_quarter": qkey,
        "calendar_sectors": SECTOR_CALENDAR.get(qkey, []),
        "status":          "ok",
    }


# ─── Phase 4 — Pattern Detection (per stock) ──────────────────────────────────

def _detect_patterns(df: pd.DataFrame) -> list:
    """
    Three patterns:
      EMA_PULLBACK  — price to 21 EMA with contracting then expanding volume
      BASE_BREAKOUT — 4–8 week tight base broken on ≥ 1.5× volume
      GAP_REVERSAL  — post-gap consolidation resuming above gap-day high
    """
    if len(df) < 60:
        return []

    close  = df["Close"]
    high   = df["High"]
    low    = df["Low"]
    volume = df["Volume"]
    opens  = df["Open"]

    ema21 = _ema(close, 21)
    ema50 = _ema(close, 50)
    ema10 = _ema(close, 10)

    lc      = float(close.iloc[-1])
    le21    = float(ema21.iloc[-1])
    le50    = float(ema50.iloc[-1])
    le10    = float(ema10.iloc[-1])
    avg20v  = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean())
    last_v  = float(volume.iloc[-1]) if not pd.isna(volume.iloc[-1]) else 0.0

    patterns = []

    # ── Pattern 1: EMA Pullback ───────────────────────────────────────────────
    if lc > le50:                                   # must be in uptrend
        dist_pct = abs(lc - le21) / le21
        if dist_pct < 0.03:                         # within 3 % of 21 EMA
            if len(volume) >= 5:
                recent_3v = [float(v) for v in volume.iloc[-4:-1] if not pd.isna(v)]
                vol_contracted = (len(recent_3v) < 2 or
                                  all(recent_3v[i] >= recent_3v[i+1]
                                      for i in range(len(recent_3v)-1)))
                vol_pickup = avg20v > 0 and last_v > avg20v * 0.75

                if vol_pickup:
                    sw_low  = float(low.iloc[-5:].min())
                    stop    = round(min(sw_low * 0.995, le21 * 0.99), 2)
                    entry   = round(lc, 2)
                    risk    = max(entry - stop, 0.01)
                    t1, t2, t3 = (round(entry + risk * m, 2) for m in (2, 3, 4))

                    # Phase 6: scale-out at 1:2; trail with 10 EMA
                    scale_out_50pct = t1
                    trail_stop      = round(le10, 2)

                    patterns.append({
                        "pattern":        "EMA_PULLBACK",
                        "pattern_label":  "EMA Pullback",
                        "pattern_icon":   "📉",
                        "entry":          entry,
                        "stop_loss":      stop,
                        "target1":        t1,
                        "target2":        t2,
                        "target3":        t3,
                        "rr_t1":          round(risk * 2 / risk, 1),
                        "rr_t2":          round(risk * 3 / risk, 1),
                        "note":           f"Pulled to 21 EMA (₹{le21:.0f}), vol contracting → expanding",
                        "ema21":          round(le21, 2),
                        "ema50":          round(le50, 2),
                        "ema10":          round(le10, 2),
                        "vol_ratio":      round(last_v / avg20v, 2) if avg20v > 0 else None,
                        "scale_out_50pct": scale_out_50pct,
                        "trail_stop":     trail_stop,
                    })

    # ── Pattern 2: Base Breakout ──────────────────────────────────────────────
    lookback = 30   # ~6 weeks
    if len(close) >= lookback + 5:
        base_h = float(high.iloc[-(lookback+5):-5].max())
        base_l = float(low.iloc[-(lookback+5):-5].min())
        base_range_pct = (base_h - base_l) / base_l if base_l > 0 else 99

        if base_range_pct < 0.12 and lc > base_h:          # tight base + breakout
            vol_ratio = last_v / avg20v if avg20v > 0 else 0
            if vol_ratio >= 1.5:
                stop  = round(base_h * 0.98, 2)
                entry = round(lc, 2)
                risk  = max(entry - stop, 0.01)
                t1, t2, t3 = (round(entry + risk * m, 2) for m in (2, 3, 4))

                patterns.append({
                    "pattern":        "BASE_BREAKOUT",
                    "pattern_label":  "Base Breakout",
                    "pattern_icon":   "🚀",
                    "entry":          entry,
                    "stop_loss":      stop,
                    "target1":        t1,
                    "target2":        t2,
                    "target3":        t3,
                    "rr_t1":          round(risk * 2 / risk, 1),
                    "rr_t2":          round(risk * 3 / risk, 1),
                    "note":           (f"{lookback}d base "
                                       f"({round(base_range_pct*100,1)}% range), "
                                       f"vol {round(vol_ratio,1)}x avg"),
                    "base_high":      round(base_h, 2),
                    "base_low":       round(base_l, 2),
                    "vol_ratio":      round(vol_ratio, 2),
                    "scale_out_50pct": round(entry + risk * 2, 2),
                    "trail_stop":      round(float(_ema(close, 10).iloc[-1]), 2),
                })

    # ── Pattern 3: Gap-up Reversal ────────────────────────────────────────────
    if len(close) >= 10:
        for gap_idx in range(-7, -2):
            try:
                g_open    = float(opens.iloc[gap_idx])
                prev_high = float(high.iloc[gap_idx - 1])
                gap_pct   = (g_open - prev_high) / prev_high * 100

                if gap_pct < 1.5:
                    continue

                g_high = float(high.iloc[gap_idx])

                # Ensure subsequent bars consolidated within gap-day range
                consol = True
                for ci in range(gap_idx + 1, min(gap_idx + 4, 0)):
                    if float(high.iloc[ci]) > g_high * 1.012:
                        consol = False
                        break

                if consol and lc > g_high:
                    post_low = float(low.iloc[gap_idx:].min())
                    stop     = round(post_low * 0.99, 2)
                    entry    = round(lc, 2)
                    risk     = max(entry - stop, 0.01)
                    t1, t2, t3 = (round(entry + risk * m, 2) for m in (2, 3, 4))

                    patterns.append({
                        "pattern":        "GAP_REVERSAL",
                        "pattern_label":  "Gap-up Reversal",
                        "pattern_icon":   "⚡",
                        "entry":          entry,
                        "stop_loss":      stop,
                        "target1":        t1,
                        "target2":        t2,
                        "target3":        t3,
                        "rr_t1":          round(risk * 2 / risk, 1),
                        "rr_t2":          round(risk * 3 / risk, 1),
                        "note":           (f"Gap +{round(gap_pct,1)}%, "
                                           f"consolidated {abs(gap_idx)-1}d, "
                                           f"resuming above gap high"),
                        "gap_pct":        round(gap_pct, 2),
                        "gap_high":       round(g_high, 2),
                        "vol_ratio":      round(last_v / avg20v, 2) if avg20v > 0 else None,
                        "scale_out_50pct": round(entry + risk * 2, 2),
                        "trail_stop":      round(float(_ema(close, 10).iloc[-1]), 2),
                    })
                    break   # only most-recent gap
            except (IndexError, ZeroDivisionError):
                continue

    return patterns


# ─── Phase 3+4 — Quality Gate + Pattern Scan ─────────────────────────────────

def _process_stock(sym: str, info: dict) -> dict | None:
    try:
        df = _fetch(sym, period="1y")
        if df is None or len(df) < 200:
            return None

        df = df.dropna(subset=["Close", "Volume"]).sort_index()
        close  = df["Close"]
        volume = df["Volume"]
        high   = df["High"]
        low    = df["Low"]

        lc       = float(close.iloc[-1])
        ema200_s = _ema(close, 200)
        le200    = float(ema200_s.iloc[-1])

        # Quality gate: price must be above 200 EMA
        if lc <= le200:
            return None

        # Volume quality gate: avg daily value ≥ ₹10 Cr (relaxed from ₹50 Cr for breadth)
        avg20v = float(volume.rolling(20).mean().iloc[-1])
        if avg20v * lc < 100_000_000:          # ₹10 Cr
            return None

        # Key EMA levels
        le21  = float(_ema(close, 21).iloc[-1])
        le50  = float(_ema(close, 50).iloc[-1])
        le10  = float(_ema(close, 10).iloc[-1])

        # 52-week stats
        win = close.iloc[-252:] if len(close) >= 252 else close
        h52 = float(df["High"].iloc[-252:].max() if len(df) >= 252 else df["High"].max())
        l52 = float(df["Low"].iloc[-252:].min()  if len(df) >= 252 else df["Low"].min())
        dist_52wh = round((lc - h52) / h52 * 100, 1)

        # 1-day change
        chg_pct = round((lc - float(close.iloc[-2])) / float(close.iloc[-2]) * 100, 2) \
                  if len(close) >= 2 else None

        # Trend label
        if lc > le50 > le200:
            trend = "STRONG_UP"
        elif lc > le200:
            trend = "UPTREND"
        else:
            trend = "DOWNTREND"

        patterns = _detect_patterns(df)

        return {
            "symbol":            sym.replace(".NS", "").replace(".BO", ""),
            "raw_symbol":        sym,
            "name":              info.get("name", sym),
            "sector":            info.get("sector", "—"),
            "cmp":               round(lc, 2),
            "chg_pct":           chg_pct,
            "ema10":             round(le10, 2),
            "ema21":             round(le21, 2),
            "ema50":             round(le50, 2),
            "ema200":            round(le200, 2),
            "trend":             trend,
            "w52_high":          round(h52, 2),
            "w52_low":           round(l52, 2),
            "dist_52wh":         dist_52wh,
            "avg_vol_20d":       int(avg20v),
            "avg_daily_val_cr":  round(avg20v * lc / 1e7, 1),
            "patterns":          patterns,
            "pattern_count":     len(patterns),
            "has_setup":         len(patterns) > 0,
        }
    except Exception as e:
        logger.warning(f"process_stock({sym}) error: {e}")
        return None


def phase3_4_stock_screen(top_sectors: list, universe: dict) -> list:
    """
    Returns quality-gate stocks (above 200 EMA, sufficient volume)
    from the top-ranked sectors, with pattern matches attached.
    """
    # Resolve which universe sector names map to top idx sector names
    target_idx_sectors = set(top_sectors)
    candidate_stocks = {}
    for sym, info in universe.items():
        u_sector = info.get("sector", "")
        mapped   = UNIVERSE_TO_IDX_SECTOR.get(u_sector, u_sector)
        if not top_sectors or mapped in target_idx_sectors or u_sector in target_idx_sectors:
            candidate_stocks[sym] = info

    if not candidate_stocks:
        candidate_stocks = universe   # fallback: scan all

    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_process_stock, sym, info): sym
                for sym, info in candidate_stocks.items()}
        for fut in as_completed(futs):
            r = fut.result()
            if r is not None:
                results.append(r)

    # Priority: stocks with patterns first, then closest to 52w high
    results.sort(key=lambda x: (-x["pattern_count"], x["dist_52wh"]))
    return results


# ─── Main entry point ────────────────────────────────────────────────────────

def run_trend_pullback_strategy(universe: dict) -> dict:
    """Orchestrate all phases and return a single JSON-serializable dict."""
    try:
        logger.info("[TrendPullback] Phase 1: Market Context…")
        market_ctx = phase1_market_context()

        logger.info("[TrendPullback] Phase 2: Sector Rotation…")
        sector_data = phase2_sector_rotation()

        top_sectors = sector_data.get("top_sectors", [])
        logger.info(f"[TrendPullback] Top sectors: {top_sectors}")

        logger.info("[TrendPullback] Phase 3+4: Stock Screen + Patterns…")
        stocks = phase3_4_stock_screen(top_sectors, universe)

        # Summary
        total      = len(stocks)
        w_patterns = sum(1 for s in stocks if s["has_setup"])
        ema_pb     = sum(1 for s in stocks for p in s["patterns"] if p["pattern"] == "EMA_PULLBACK")
        bb         = sum(1 for s in stocks for p in s["patterns"] if p["pattern"] == "BASE_BREAKOUT")
        gr         = sum(1 for s in stocks for p in s["patterns"] if p["pattern"] == "GAP_REVERSAL")

        return {
            "status":          "success",
            "run_date":        datetime.now().strftime("%Y-%m-%d"),
            "run_time":        datetime.now().strftime("%H:%M:%S"),
            "market_context":  market_ctx,
            "sector_rotation": sector_data,
            "stocks":          stocks,
            "summary": {
                "total_qualified":    total,
                "with_patterns":      w_patterns,
                "ema_pullback_count": ema_pb,
                "base_breakout_count": bb,
                "gap_reversal_count": gr,
                "top_sectors":        top_sectors,
            },
        }
    except Exception as e:
        logger.error(f"[TrendPullback] Strategy error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
