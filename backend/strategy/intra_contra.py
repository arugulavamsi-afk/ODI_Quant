"""
IntraContra — 3M Momentum Swing System
=======================================
Pillars:
  1  Trend Identification  — only trade with the tide (weekly + daily)
  2  Entry Precision       — 4 high-probability setup types
  3  Asymmetric R:R        — minimum 1:2.5 on every trade

Setups:
  A  Flag & Pole Breakout    (~68% win rate)
  B  EMA Pullback Entry      (best R:R)
  C  52-Week High Breakout   (championship maker)
  D  Sector Rotation Play    (ride institutional wave)
"""

import logging
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# ─── Technical Indicators ────────────────────────────────────────────────────

def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _rsi(s: pd.Series, period: int = 14) -> pd.Series:
    delta    = s.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """Returns (adx, +DI, -DI) as three pd.Series."""
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    up   = high.diff()
    down = -(low.diff())

    pdm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    ndm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)

    alpha = 1 / period
    atr   = tr.ewm(alpha=alpha, adjust=False).mean().replace(0, np.nan)
    pdi   = 100 * pdm.ewm(alpha=alpha, adjust=False).mean() / atr
    ndi   = 100 * ndm.ewm(alpha=alpha, adjust=False).mean() / atr

    denom = (pdi + ndi).replace(0, np.nan)
    dx    = 100 * (pdi - ndi).abs() / denom
    adx   = dx.ewm(alpha=alpha, adjust=False).mean()

    return adx, pdi, ndi


def _sf(val, decimals=2):
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, decimals)
    except Exception:
        return None


# ─── Weekly Trend from Daily Data ────────────────────────────────────────────

def _weekly_trend(df: pd.DataFrame) -> str:
    """Downsample daily → weekly, classify BULL / SIDEWAYS / BEAR."""
    try:
        wk = df["Close"].resample("W").last().dropna()
        if len(wk) < 20:
            return "UNKNOWN"
        ema10w = float(_ema(wk, 10).iloc[-1])
        ema20w = float(_ema(wk, 20).iloc[-1])
        lc     = float(wk.iloc[-1])
        if lc > ema10w > ema20w:
            return "BULL"
        if lc < ema10w < ema20w:
            return "BEAR"
        return "SIDEWAYS"
    except Exception:
        return "UNKNOWN"


# ─── Setup Detection ─────────────────────────────────────────────────────────

def _detect_setups(df: pd.DataFrame, sector_rank: int = 99) -> list:
    if len(df) < 60:
        return []

    close  = df["Close"]
    high   = df["High"]
    low    = df["Low"]
    opens  = df["Open"]
    volume = df["Volume"]

    e20  = _ema(close, 20)
    e50  = _ema(close, 50)
    e200 = _ema(close, 200) if len(close) >= 200 else _ema(close, len(close) // 2)

    rsi_s        = _rsi(close)
    adx_s, pdi_s, ndi_s = _adx(high, low, close)

    lc     = float(close.iloc[-1])
    le20   = float(e20.iloc[-1])
    le50   = float(e50.iloc[-1])
    le200  = float(e200.iloc[-1])
    l_rsi  = _sf(rsi_s.iloc[-1])
    l_adx  = _sf(adx_s.iloc[-1])
    avg20v = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean())
    last_v = float(volume.iloc[-1]) if not pd.isna(volume.iloc[-1]) else 0.0
    vol_ratio = round(last_v / avg20v, 2) if avg20v > 0 else 0

    h52 = float(high.iloc[-252:].max() if len(high) >= 252 else high.max())
    l52 = float(low.iloc[-252:].min()  if len(low)  >= 252 else low.min())

    setups = []

    # ── Bullish quality gate ──────────────────────────────────────────────────
    ema_aligned = lc > le20 > le50 > le200

    # ── Setup A: Flag & Pole Breakout ─────────────────────────────────────────
    # Pole = >8% gain in a 5-15 day window ending 5+ days ago
    # Flag = last 3-7 days tight range (<6%), breakout today on 2x vol
    if len(close) >= 25 and ema_aligned:
        pole_start = int(close.iloc[-22])
        pole_end   = int(close.iloc[-8])
        pole_gain  = (pole_end - pole_start) / pole_start * 100 if pole_start > 0 else 0

        flag_candles = close.iloc[-7:-1]
        flag_h = float(high.iloc[-7:-1].max())
        flag_l = float(low.iloc[-7:-1].min())
        flag_range_pct = (flag_h - flag_l) / flag_l * 100 if flag_l > 0 else 99

        breakout = lc > flag_h
        vol_ok   = vol_ratio >= 1.8

        if pole_gain >= 7 and flag_range_pct <= 6 and breakout and vol_ok:
            stop  = round(flag_l * 0.99, 2)
            risk  = max(lc - stop, 0.01)
            t1    = round(lc + risk * 1.5, 2)
            t2    = round(lc + risk * 2.5, 2)
            t3    = round(lc + risk * 4.0, 2)
            setups.append({
                "setup":       "FLAG_POLE",
                "setup_label": "Flag & Pole Breakout",
                "setup_icon":  "🔥",
                "win_rate":    "~68%",
                "entry":       round(lc, 2),
                "stop_loss":   stop,
                "target1":     t1,
                "target2":     t2,
                "target3":     t3,
                "rr_t1":       round(risk * 1.5 / risk, 1),
                "rr_t2":       round(risk * 2.5 / risk, 1),
                "note":        f"Pole +{round(pole_gain,1)}%, flag {round(flag_range_pct,1)}% range, vol {vol_ratio}x",
                "vol_ratio":   vol_ratio,
                "flag_high":   round(flag_h, 2),
                "trail_ref":   round(le20, 2),
                "trail_label": "20 EMA",
            })

    # ── Setup B: EMA Pullback Entry ───────────────────────────────────────────
    # Uptrend, price near 20 or 50 EMA, RSI 40-60, bullish candle
    if ema_aligned and l_rsi is not None and 38 <= l_rsi <= 62:
        dist20 = abs(lc - le20) / le20 * 100
        dist50 = abs(lc - le50) / le50 * 100
        ema_ref = None
        dist_used = None
        if dist20 <= 2.5:
            ema_ref, dist_used = le20, dist20
        elif dist50 <= 3.0:
            ema_ref, dist_used = le50, dist50

        if ema_ref:
            bullish_candle = float(opens.iloc[-1]) < lc  # close > open

            if bullish_candle:
                sw_low = float(low.iloc[-5:].min())
                stop   = round(min(sw_low * 0.995, ema_ref * 0.985), 2)
                risk   = max(lc - stop, 0.01)
                t1     = round(lc + risk * 1.5, 2)
                t2     = round(lc + risk * 2.5, 2)
                t3     = round(lc + risk * 4.0, 2)
                label  = "20 EMA" if ema_ref == le20 else "50 EMA"
                setups.append({
                    "setup":       "EMA_PULLBACK",
                    "setup_label": "EMA Pullback Entry",
                    "setup_icon":  "🔥",
                    "win_rate":    "Best R:R",
                    "entry":       round(lc, 2),
                    "stop_loss":   stop,
                    "target1":     t1,
                    "target2":     t2,
                    "target3":     t3,
                    "rr_t1":       round(risk * 1.5 / risk, 1),
                    "rr_t2":       round(risk * 2.5 / risk, 1),
                    "note":        f"Bouncing off {label} ({round(ema_ref,0):.0f}), RSI {l_rsi:.0f}, dist {round(dist_used,1)}%",
                    "vol_ratio":   vol_ratio,
                    "ema_ref":     round(ema_ref, 2),
                    "ema_ref_label": label,
                    "trail_ref":   round(le20, 2),
                    "trail_label": "20 EMA",
                })

    # ── Setup C: 52-Week High Breakout ────────────────────────────────────────
    # Within 2% of 52W high, consolidated 10-20 days, volume pickup
    if len(close) >= 30:
        dist_52wh = (lc - h52) / h52 * 100
        # At or near 52W high (within 2%)
        if dist_52wh >= -2.0:
            # Check consolidation: last 10-20 days range < 8%
            consol_h = float(high.iloc[-20:-2].max())
            consol_l = float(low.iloc[-20:-2].min())
            consol_range = (consol_h - consol_l) / consol_l * 100 if consol_l > 0 else 99

            if consol_range <= 9 and vol_ratio >= 1.4:
                stop  = round(consol_l * 0.99, 2)
                risk  = max(lc - stop, 0.01)
                t1    = round(lc + risk * 1.5, 2)
                t2    = round(lc + risk * 2.5, 2)
                t3    = round(lc + risk * 5.0, 2)  # 52W breakouts can run
                setups.append({
                    "setup":       "HIGH_BREAKOUT",
                    "setup_label": "52-Week High Breakout",
                    "setup_icon":  "🔥",
                    "win_rate":    "Championship",
                    "entry":       round(lc, 2),
                    "stop_loss":   stop,
                    "target1":     t1,
                    "target2":     t2,
                    "target3":     t3,
                    "rr_t1":       round(risk * 1.5 / risk, 1),
                    "rr_t2":       round(risk * 2.5 / risk, 1),
                    "note":        f"At 52W high ₹{round(h52,0):.0f}, consol range {round(consol_range,1)}%, vol {vol_ratio}x",
                    "vol_ratio":   vol_ratio,
                    "w52_high":    round(h52, 2),
                    "consol_range_pct": round(consol_range, 1),
                    "trail_ref":   round(le20, 2),
                    "trail_label": "20 EMA",
                })

    # ── Setup D: Sector Rotation Play ─────────────────────────────────────────
    # Top-3 sector + uptrend + ADX > 20 + recent momentum
    if sector_rank <= 3 and ema_aligned and l_adx is not None and l_adx >= 20:
        # Check recent momentum: 5-day return > 2%
        ret_5d = (lc / float(close.iloc[-6]) - 1) * 100 if len(close) >= 6 else 0
        if ret_5d >= 1.5:
            stop  = round(float(low.iloc[-5:].min()) * 0.99, 2)
            risk  = max(lc - stop, 0.01)
            t1    = round(lc + risk * 1.5, 2)
            t2    = round(lc + risk * 2.5, 2)
            t3    = round(lc + risk * 3.5, 2)
            setups.append({
                "setup":       "SECTOR_ROTATION",
                "setup_label": "Sector Rotation Play",
                "setup_icon":  "🔥",
                "win_rate":    "5–15 day ride",
                "entry":       round(lc, 2),
                "stop_loss":   stop,
                "target1":     t1,
                "target2":     t2,
                "target3":     t3,
                "rr_t1":       round(risk * 1.5 / risk, 1),
                "rr_t2":       round(risk * 2.5 / risk, 1),
                "note":        f"Sector rank #{sector_rank}, ADX {round(l_adx,1)}, 5d +{round(ret_5d,1)}%",
                "vol_ratio":   vol_ratio,
                "sector_rank": sector_rank,
                "trail_ref":   round(le20, 2),
                "trail_label": "20 EMA",
            })

    return setups


# ─── Per-Stock Processor ─────────────────────────────────────────────────────

def _process_stock(sym: str, info: dict, sector_rank: int = 99) -> dict | None:
    try:
        t  = yf.Ticker(sym)
        df = t.history(period="1y", auto_adjust=True)
        if df is None or len(df) < 60:
            return None

        df.columns = [c.strip() for c in df.columns]
        df = df.dropna(subset=["Close", "Volume"]).sort_index()

        close  = df["Close"]
        high   = df["High"]
        low    = df["Low"]
        volume = df["Volume"]

        lc    = float(close.iloc[-1])
        le20  = float(_ema(close, 20).iloc[-1])
        le50  = float(_ema(close, 50).iloc[-1])
        le200 = float(_ema(close, 200).iloc[-1]) if len(close) >= 200 else float(_ema(close, len(close)//2).iloc[-1])

        rsi_s = _rsi(close)
        adx_s, pdi_s, ndi_s = _adx(high, low, close)

        l_rsi = _sf(rsi_s.iloc[-1])
        l_adx = _sf(adx_s.iloc[-1])
        avg20v = float(volume.rolling(20).mean().iloc[-1]) if len(volume) >= 20 else float(volume.mean())
        vol_ratio = round(float(volume.iloc[-1]) / avg20v, 2) if avg20v > 0 else 0

        # Weekly trend
        wk_trend = _weekly_trend(df)

        # Daily trend
        ema_aligned = lc > le20 > le50 > le200
        if lc > le20 > le50 > le200:
            daily_trend = "STRONG_BULL"
        elif lc > le200:
            daily_trend = "BULL"
        elif lc < le200:
            daily_trend = "BEAR"
        else:
            daily_trend = "NEUTRAL"

        # 52W stats
        h52 = float(high.iloc[-252:].max() if len(high) >= 252 else high.max())
        l52 = float(low.iloc[-252:].min()  if len(low)  >= 252 else low.min())
        dist_52wh = round((lc - h52) / h52 * 100, 1)

        # Daily volume value
        avg_val_cr = round(avg20v * lc / 1e7, 1)

        # Distance from nearest breakout zone (recent 10d high)
        recent_high = float(high.iloc[-10:].max())
        dist_breakout = round((lc - recent_high) / recent_high * 100, 1)

        # 1-day change
        chg_pct = round((lc - float(close.iloc[-2])) / float(close.iloc[-2]) * 100, 2) if len(close) >= 2 else None

        # Detect setups
        setups = _detect_setups(df, sector_rank)

        # Bullish screening score (for sorting)
        score = 0
        if ema_aligned:             score += 30
        if l_rsi and 55 <= l_rsi <= 75: score += 20
        if vol_ratio >= 1.5:        score += 15
        if l_adx and l_adx >= 25:   score += 15
        if wk_trend == "BULL":      score += 10
        if len(setups) > 0:         score += 10 * len(setups)

        return {
            "symbol":         sym.replace(".NS", "").replace(".BO", ""),
            "raw_symbol":     sym,
            "name":           info.get("name", sym),
            "sector":         info.get("sector", "—"),
            "cmp":            round(lc, 2),
            "chg_pct":        chg_pct,
            "weekly_trend":   wk_trend,
            "daily_trend":    daily_trend,
            "ema_aligned":    ema_aligned,
            "ema20":          round(le20, 2),
            "ema50":          round(le50, 2),
            "ema200":         round(le200, 2),
            "rsi_14":         l_rsi,
            "adx_14":         l_adx,
            "vol_ratio":      vol_ratio,
            "avg_val_cr":     avg_val_cr,
            "w52_high":       round(h52, 2),
            "w52_low":        round(l52, 2),
            "dist_52wh":      dist_52wh,
            "dist_breakout":  dist_breakout,
            "sector_rank":    sector_rank,
            "setups":         setups,
            "setup_count":    len(setups),
            "has_setup":      len(setups) > 0,
            "score":          score,
        }
    except Exception as e:
        logger.warning(f"IntraContra process_stock({sym}) error: {e}")
        return None


# ─── Market Context ───────────────────────────────────────────────────────────

def _market_context() -> dict:
    """Nifty weekly + daily trend, VIX, Nifty change."""
    ctx = {
        "nifty_price":      None,
        "nifty_chg_pct":    None,
        "nifty_weekly":     "UNKNOWN",
        "nifty_daily":      "UNKNOWN",
        "nifty_ema20":      None,
        "nifty_ema50":      None,
        "nifty_rsi":        None,
        "nifty_adx":        None,
        "vix_value":        None,
        "vix_status":       "UNKNOWN",
        "trade_bias":       "NEUTRAL",
        "trade_bias_color": "yellow",
    }
    try:
        t  = yf.Ticker("^NSEI")
        df = t.history(period="1y", auto_adjust=True)
        if df is not None and len(df) >= 50:
            df = df.dropna(subset=["Close"]).sort_index()
            close = df["Close"]
            high  = df["High"]
            low   = df["Low"]

            lc     = float(close.iloc[-1])
            le20   = float(_ema(close, 20).iloc[-1])
            le50   = float(_ema(close, 50).iloc[-1])
            l_rsi  = _sf(_rsi(close).iloc[-1])
            adx_s, _, _ = _adx(high, low, close)
            l_adx  = _sf(adx_s.iloc[-1])

            ctx.update({
                "nifty_price":  round(lc, 2),
                "nifty_ema20":  round(le20, 2),
                "nifty_ema50":  round(le50, 2),
                "nifty_rsi":    l_rsi,
                "nifty_adx":    l_adx,
            })
            if len(close) >= 2:
                prev = float(close.iloc[-2])
                ctx["nifty_chg_pct"] = round((lc - prev) / prev * 100, 2)

            ctx["nifty_weekly"] = _weekly_trend(df)
            ctx["nifty_daily"]  = ("STRONG_BULL" if lc > le20 > le50
                                   else "BULL" if lc > le50
                                   else "BEAR")
    except Exception as e:
        logger.warning(f"Nifty context error: {e}")

    try:
        vdf = yf.Ticker("^INDIAVIX").history(period="1mo", auto_adjust=True)
        if vdf is not None and not vdf.empty:
            vv = _sf(vdf["Close"].iloc[-1])
            ctx["vix_value"] = vv
            ctx["vix_status"] = ("LOW" if vv and vv < 18 else
                                 "ELEVATED" if vv and vv <= 22 else
                                 "HIGH")
    except Exception as e:
        logger.warning(f"VIX context error: {e}")

    # Trade bias
    w = ctx["nifty_weekly"]
    d = ctx["nifty_daily"]
    v = ctx["vix_status"]
    if w == "BULL" and d in ("BULL", "STRONG_BULL") and v in ("LOW", "ELEVATED"):
        ctx.update({"trade_bias": "LONG",    "trade_bias_color": "green"})
    elif w == "BEAR" or d == "BEAR" or v == "HIGH":
        ctx.update({"trade_bias": "CAUTION", "trade_bias_color": "red"})
    else:
        ctx.update({"trade_bias": "NEUTRAL", "trade_bias_color": "yellow"})

    return ctx


# ─── Sector Rotation (reuse Sniper approach) ─────────────────────────────────

SECTOR_INDICES = {
    "^NSEBANK":    "Banking",
    "^CNXIT":      "IT",
    "^CNXPHARMA":  "Pharma",
    "^CNXAUTO":    "Auto",
    "^CNXREALTY":  "Realty",
    "^CNXFMCG":    "FMCG",
    "^CNXMETAL":   "Metals",
    "^CNXINFRA":   "Infra",
    "^CNXENERGY":  "Energy",
    "^CNXFINANCE": "Finance",
}

UNIVERSE_TO_IDX = {
    "Banking": "Banking", "IT": "IT", "Pharma": "Pharma",
    "Healthcare": "Pharma", "Auto": "Auto", "Finance": "Finance",
    "FMCG": "FMCG", "Consumer": "FMCG", "Energy": "Energy",
    "Metals": "Metals", "Infra": "Infra", "Telecom": "Infra", "Media": "Infra",
}


def _sector_ranks() -> dict[str, int]:
    """Return {idx_sector_name: rank} ordered by 4-week RS vs Nifty."""
    try:
        ndf = yf.Ticker("^NSEI").history(period="3mo", auto_adjust=True)
        if ndf is None or len(ndf) < 21:
            return {}
        nc   = ndf["Close"].dropna()
        n4w  = (float(nc.iloc[-1]) / float(nc.iloc[-21]) - 1) * 100

        scores = {}
        for sym, name in SECTOR_INDICES.items():
            try:
                df = yf.Ticker(sym).history(period="3mo", auto_adjust=True)
                if df is None or len(df) < 21:
                    continue
                c   = df["Close"].dropna()
                r4w = (float(c.iloc[-1]) / float(c.iloc[-21]) - 1) * 100
                scores[name] = r4w - n4w
            except Exception:
                pass

        ranked = sorted(scores, key=lambda k: scores[k], reverse=True)
        return {name: i + 1 for i, name in enumerate(ranked)}
    except Exception as e:
        logger.warning(f"Sector ranks error: {e}")
        return {}


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def run_intra_contra(universe: dict) -> dict:
    """Orchestrate market context + sector ranks + full NIFTY 100 scan."""
    try:
        logger.info("[IntraContra] Market context…")
        market_ctx = _market_context()

        logger.info("[IntraContra] Sector ranks…")
        sec_ranks = _sector_ranks()

        logger.info("[IntraContra] Scanning %d stocks…", len(universe))

        def _get_rank(info: dict) -> int:
            u_sec  = info.get("sector", "")
            mapped = UNIVERSE_TO_IDX.get(u_sec, u_sec)
            return sec_ranks.get(u_sec, sec_ranks.get(mapped, 99))

        results = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {
                ex.submit(_process_stock, sym, info, _get_rank(info)): sym
                for sym, info in universe.items()
            }
            for fut in as_completed(futs):
                r = fut.result()
                if r is not None:
                    results.append(r)

        # Sort: most setups → highest score → EMA aligned first
        results.sort(key=lambda x: (-x["setup_count"], -x["score"]))

        # Summary
        total     = len(results)
        w_setups  = sum(1 for s in results if s["has_setup"])
        flag_pole = sum(1 for s in results for st in s["setups"] if st["setup"] == "FLAG_POLE")
        ema_pb    = sum(1 for s in results for st in s["setups"] if st["setup"] == "EMA_PULLBACK")
        hi_bo     = sum(1 for s in results for st in s["setups"] if st["setup"] == "HIGH_BREAKOUT")
        sec_rot   = sum(1 for s in results for st in s["setups"] if st["setup"] == "SECTOR_ROTATION")
        aligned   = sum(1 for s in results if s["ema_aligned"])

        # RSI quality zone
        rsi_ok = sum(1 for s in results
                     if s["rsi_14"] is not None and 55 <= s["rsi_14"] <= 75)

        return {
            "status":         "success",
            "run_date":       datetime.now().strftime("%Y-%m-%d"),
            "run_time":       datetime.now().strftime("%H:%M:%S"),
            "market_context": market_ctx,
            "sector_ranks":   sec_ranks,
            "stocks":         results,
            "summary": {
                "total":           total,
                "with_setups":     w_setups,
                "ema_aligned":     aligned,
                "rsi_quality":     rsi_ok,
                "flag_pole":       flag_pole,
                "ema_pullback":    ema_pb,
                "high_breakout":   hi_bo,
                "sector_rotation": sec_rot,
            },
        }
    except Exception as e:
        logger.error(f"[IntraContra] Error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
