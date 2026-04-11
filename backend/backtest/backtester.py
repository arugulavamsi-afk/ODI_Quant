"""
Backtesting framework for ODI Quant.

DATA REQUIREMENTS & KNOWN LIMITATIONS
======================================
MA200 warm-up:
  The 200-day moving average needs exactly 200 bars before its first valid value.
  We require _WARMUP_BARS = 220 bars of history before the first tradeable day,
  giving a 20-bar buffer beyond MA200's period.  Slices shorter than this are
  rejected — no signal, no trade.

Minimum data for reliability:
  Signals fire at roughly 3–5% frequency on typical setups.  To collect 30
  trades (the absolute floor for any metric to be non-noise) you need
  30 / 0.04 = 750 tradeable bars ≈ 3 years of daily data AFTER warmup.
  The function requires at least _MIN_HISTORY_BARS total bars and reports
  a `statistical_reliability` rating based on realised trade count.

Intra-bar ordering ambiguity:
  The simulation only has daily OHLC — it cannot know whether the day's high
  or low was reached first.  The current rule (low ≤ SL → loss, else high ≥
  target → win) assumes the worst case for longs (SL checked first).  This is
  conservative but still an approximation.  Real results will differ.  The
  output includes an `intrabar_note` explaining this.

Metrics suppressed when trade count is too low:
  < 30 trades  → reliability = "INSUFFICIENT", all metrics marked unreliable.
  30–99 trades → reliability = "LOW", confidence intervals are wide.
  100–299      → reliability = "MODERATE".
  300+         → reliability = "HIGH".

Confidence interval on win rate:
  Wilson score interval at 95% confidence.  At N=30, the half-width is ±18%.
  At N=100 it narrows to ±10%.  At N=300 it reaches ±5%.
"""
import math
import pandas as pd
import numpy as np
import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicators.trend import calculate_moving_averages, get_trend_bias, get_trend_score, get_market_structure
from indicators.volatility import calculate_atr, get_atr_expansion, get_volatility_score
from indicators.volume import get_volume_spike, get_price_volume_alignment, get_volume_score
from indicators.breakout import get_breakout_status, get_closing_strength, get_breakout_score, get_consolidation_breakout
from signals.signal_engine import generate_long_signal, generate_short_signal
from scoring.scorer import calculate_long_score, calculate_short_score
from config import HIGH_PROB_THRESHOLD, BREAKOUT_PERIOD

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
_WARMUP_BARS     = 220   # bars consumed before first tradeable day (MA200 + 20 buffer)
_MIN_HISTORY_BARS = 440  # minimum total bars accepted (warmup + 220 tradeable minimum)
_MIN_TRADES_LOW   = 30   # floor: metrics exist but are unreliable
_MIN_TRADES_MOD   = 100  # moderate reliability
_MIN_TRADES_HIGH  = 300  # high reliability

_INTRABAR_NOTE = (
    "Intra-bar ordering is unknown (daily OHLC only). "
    "The simulation checks SL before target within each bar — conservative for longs, "
    "optimistic for shorts. Actual fill order may differ. "
    "Win rate could be overstated or understated by several percentage points."
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple:
    """Wilson score confidence interval for a proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
    return (round(max(0.0, centre - margin) * 100, 1),
            round(min(1.0, centre + margin) * 100, 1))


def _reliability_label(n: int) -> str:
    if n < _MIN_TRADES_LOW:
        return "INSUFFICIENT"
    if n < _MIN_TRADES_MOD:
        return "LOW"
    if n < _MIN_TRADES_HIGH:
        return "MODERATE"
    return "HIGH"


def _annualised_sharpe(r_series: list) -> float | None:
    """
    Annualised Sharpe from a list of per-trade R multiples.
    Assumes each trade is one day (conservative — real holding periods vary).
    Returns None when fewer than 2 observations.
    """
    if len(r_series) < 2:
        return None
    arr = np.array(r_series, dtype=float)
    std = arr.std(ddof=1)
    if std == 0:
        return None
    # Scale to annual: sqrt(252) assumes one trade per day on average.
    # With sparse signals this overstates annualisation — acknowledged in output.
    return round(float(arr.mean() / std * math.sqrt(252)), 3)


def _profit_factor(wins_r: list, losses_r: list) -> float | None:
    """Gross profit / gross loss (both as positive numbers)."""
    gross_profit = sum(wins_r) if wins_r else 0.0
    gross_loss   = abs(sum(losses_r)) if losses_r else 0.0
    if gross_loss == 0:
        return None          # no losses → undefined (not infinity)
    return round(gross_profit / gross_loss, 3)


# ── Indicator computation ────────────────────────────────────────────────────

def _compute_indicators_at_row(df_slice: pd.DataFrame) -> dict | None:
    """
    Compute all indicators for a given history slice.

    Requires at least _WARMUP_BARS rows so that MA200 is fully warmed up.
    Returns None (→ skip this day) if the slice is too short OR if MA200
    is still NaN (which can happen when the series has gaps).
    """
    if len(df_slice) < _WARMUP_BARS:
        return None
    try:
        df = calculate_moving_averages(df_slice.copy())
        df = calculate_atr(df)

        last  = df.iloc[-1]
        ma200 = float(df["MA200"].iloc[-1]) if "MA200" in df.columns else float("nan")

        # Hard gate: do not generate signals until MA200 is fully computed.
        if math.isnan(ma200):
            return None

        ma20     = float(df["MA20"].iloc[-1])  if not pd.isna(df["MA20"].iloc[-1])  else None
        ma50     = float(df["MA50"].iloc[-1])  if not pd.isna(df["MA50"].iloc[-1])  else None
        atr_val  = float(df["ATR"].iloc[-1])   if not pd.isna(df["ATR"].iloc[-1])   else 0.0

        trend_bias        = get_trend_bias(df)
        market_structure  = get_market_structure(df)
        breakout_info     = get_breakout_status(df)
        closing_strength  = get_closing_strength(df)
        volume_spike      = get_volume_spike(df)
        pv_alignment      = get_price_volume_alignment(df)
        atr_expansion     = get_atr_expansion(df)
        consol_breakout, _ = get_consolidation_breakout(df)

        return {
            "close":                float(last["Close"]),
            "atr":                  atr_val,
            "ma20":                 ma20,
            "ma50":                 ma50,
            "ma200":                ma200,
            "trend_bias":           trend_bias,
            "market_structure":     market_structure,
            "breakout_status":      breakout_info["status"],
            "breakout_level":       breakout_info.get("breakout_level"),
            "breakdown_level":      breakout_info.get("breakdown_level"),
            "resistance":           breakout_info.get("resistance"),
            "support":              breakout_info.get("support"),
            "closing_strength":     closing_strength,
            "volume_spike":         volume_spike,
            "price_volume_alignment": pv_alignment,
            "atr_expansion":        atr_expansion,
            "range_ratio":          round(float(atr_expansion), 2),
            "consolidation_breakout": consol_breakout,
            "trend_score":          get_trend_score(df),
            "breakout_score":       get_breakout_score(df),
            "volume_score":         get_volume_score(df),
            "volatility_score":     get_volatility_score(df),
        }
    except Exception as e:
        logger.debug(f"Indicator compute error: {e}")
        return None


# ── Single-symbol backtest ───────────────────────────────────────────────────

def run_backtest(symbol: str, df: pd.DataFrame, period_days: int = 504) -> dict:
    """
    Signal-based backtest over historical data.

    Signal generation uses only data available at the time (no look-ahead).
    Trade execution: entry at next day open, exit when SL or target is hit
    (checked intra-bar; ordering ambiguity documented in _INTRABAR_NOTE).

    Minimum requirement: _MIN_HISTORY_BARS total bars.
    Recommended: 3+ years (~756 bars) so that enough trades fire for any
    metric to carry statistical weight.

    Args:
        symbol:      ticker label (display only)
        df:          daily OHLCV DataFrame, sorted ascending
        period_days: how many days of the tail to use as the test window.
                     Warmup bars are added on top of this.

    Returns a metrics dict.  All metrics include a `statistical_reliability`
    rating and a `data_quality` sub-dict explaining sample size constraints.
    """
    if df is None or len(df) < _MIN_HISTORY_BARS:
        bars_have = len(df) if df is not None else 0
        return {
            "error": (
                f"Insufficient data: {bars_have} bars available, "
                f"{_MIN_HISTORY_BARS} required (warmup {_WARMUP_BARS} + "
                f"minimum {_MIN_HISTORY_BARS - _WARMUP_BARS} tradeable bars). "
                f"Fetch at least 2 years of daily data to run a backtest."
            ),
            "symbol": symbol,
            "bars_available": bars_have,
            "bars_required":  _MIN_HISTORY_BARS,
        }

    df = df.copy().sort_index()

    # Use at most `period_days` tradeable bars + warmup buffer.
    total_needed = period_days + _WARMUP_BARS
    if len(df) > total_needed:
        df = df.iloc[-total_needed:]

    trades        = []
    equity_curve  = [1.0]
    equity        = 1.0
    skipped_warmup = 0  # bars skipped because indicators weren't warm yet

    for i in range(_WARMUP_BARS, len(df) - 1):
        df_slice    = df.iloc[:i + 1]
        indicators  = _compute_indicators_at_row(df_slice)
        if indicators is None:
            skipped_warmup += 1
            continue

        long_signal  = generate_long_signal(df_slice, indicators)
        short_signal = generate_short_signal(df_slice, indicators)

        long_score  = calculate_long_score(indicators, long_signal, 0)
        short_score = calculate_short_score(indicators, short_signal, 0)

        direction = signal = score = None
        if long_score >= HIGH_PROB_THRESHOLD and long_score >= short_score:
            direction, score, signal = "LONG", long_score, long_signal
        elif short_score >= HIGH_PROB_THRESHOLD:
            direction, score, signal = "SHORT", short_score, short_signal

        if direction is None:
            continue

        # ── Next-day execution ────────────────────────────────────────────
        next_day  = df.iloc[i + 1]
        entry     = float(next_day["Open"])
        day_high  = float(next_day["High"])
        day_low   = float(next_day["Low"])
        day_close = float(next_day["Close"])

        atr = indicators["atr"] or entry * 0.02

        if direction == "LONG":
            sl     = entry - atr * 1.5
            target = entry + atr * 3.0     # 2:1 RR
            # Conservative: assume SL is checked before target (worst case for long)
            if day_low <= sl:
                outcome, pnl_r = "LOSS", -1.0
            elif day_high >= target:
                outcome, pnl_r = "WIN", 2.0
            else:
                sl_dist = entry - sl
                pnl_r   = (day_close - entry) / sl_dist if sl_dist > 0 else 0
                outcome = "WIN" if pnl_r > 0 else "LOSS"
        else:  # SHORT
            sl     = entry + atr * 1.5
            target = entry - atr * 3.0
            # Conservative: assume SL is checked before target (worst case for short)
            if day_high >= sl:
                outcome, pnl_r = "LOSS", -1.0
            elif day_low <= target:
                outcome, pnl_r = "WIN", 2.0
            else:
                sl_dist = sl - entry
                pnl_r   = (entry - day_close) / sl_dist if sl_dist > 0 else 0
                outcome = "WIN" if pnl_r > 0 else "LOSS"

        trades.append({
            "date":           str(df.index[i].date()),
            "direction":      direction,
            "score":          score,
            "entry":          round(entry, 2),
            "sl":             round(sl, 2),
            "target":         round(target, 2),
            "outcome":        outcome,
            "pnl_r":          round(pnl_r, 2),
            "signal_quality": signal.get("signal", "N/A") if signal else "N/A",
        })

        # Fixed-fractional equity update: 1R = 2% of equity
        equity *= (1 + pnl_r * 0.02)
        equity_curve.append(round(equity, 4))

    # ── Data quality assessment ───────────────────────────────────────────────
    tradeable_bars = len(df) - _WARMUP_BARS - 1
    total_trades   = len(trades)
    reliability    = _reliability_label(total_trades)

    data_quality = {
        "total_bars":          len(df),
        "warmup_bars":         _WARMUP_BARS,
        "tradeable_bars":      tradeable_bars,
        "bars_still_warming":  skipped_warmup,
        "total_trades":        total_trades,
        "statistical_reliability": reliability,
        "reliability_note": (
            f"{total_trades} trades observed over {tradeable_bars} tradeable bars "
            f"(signal frequency {round(total_trades/tradeable_bars*100, 1) if tradeable_bars else 0}%). "
            + {
                "INSUFFICIENT": (
                    f"Need ≥ {_MIN_TRADES_LOW} trades for metrics to be non-noise. "
                    "All numbers below are unreliable — do not act on them. "
                    f"Fetch more history or lower the score threshold temporarily."
                ),
                "LOW":          (
                    f"30–99 trades: confidence intervals are very wide (±10–18% on win rate). "
                    "Treat as directional indication only, not a validated edge."
                ),
                "MODERATE":     (
                    "100–299 trades: moderate confidence. Win-rate CI half-width ~±5–10%. "
                    "Edge is visible but not production-validated."
                ),
                "HIGH":         (
                    "300+ trades: high confidence. Win-rate CI half-width ~±3–5%. "
                    "Results are statistically meaningful."
                ),
            }[reliability]
        ),
        "intrabar_note": _INTRABAR_NOTE,
        "ma200_warmup_note": (
            f"MA200 requires 200 bars before its first valid value. "
            f"This backtest enforces a {_WARMUP_BARS}-bar warmup gate — "
            "no signal is generated until every indicator is fully computed. "
            f"Bars still warming after the gate: {skipped_warmup}."
        ),
    }

    if not trades:
        return {
            "error":        "No trades generated after warmup gate.",
            "symbol":       symbol,
            "data_quality": data_quality,
        }

    # ── Metrics ───────────────────────────────────────────────────────────────
    wins   = [t for t in trades if t["outcome"] == "WIN"]
    losses = [t for t in trades if t["outcome"] == "LOSS"]

    win_rate   = len(wins) / total_trades * 100
    avg_win_r  = float(np.mean([t["pnl_r"] for t in wins]))   if wins   else 0.0
    avg_loss_r = float(np.mean([t["pnl_r"] for t in losses])) if losses else 0.0
    avg_rr     = float(np.mean([t["pnl_r"] for t in trades]))

    loss_rate  = 1 - win_rate / 100
    expectancy = (win_rate / 100 * avg_win_r) + (loss_rate * avg_loss_r)

    pf = _profit_factor([t["pnl_r"] for t in wins],
                        [t["pnl_r"] for t in losses])

    sharpe = _annualised_sharpe([t["pnl_r"] for t in trades])

    ci_lo, ci_hi = _wilson_ci(len(wins), total_trades)

    # Max drawdown
    peak = max_dd = 0.0
    peak = 1.0
    for e in equity_curve:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd:
            max_dd = dd

    final_equity = equity_curve[-1] if equity_curve else 1.0
    total_return = (final_equity - 1.0) * 100

    # Mark all metrics as potentially unreliable when sample is too small.
    metrics_reliable = reliability not in ("INSUFFICIENT",)

    return {
        "symbol":               symbol,
        "period_days":          period_days,
        "total_trades":         total_trades,
        "wins":                 len(wins),
        "losses":               len(losses),
        "win_rate":             round(win_rate, 1),
        "win_rate_ci_95":       [ci_lo, ci_hi],   # 95% Wilson confidence interval
        "avg_win_r":            round(avg_win_r, 2),
        "avg_loss_r":           round(avg_loss_r, 2),
        "avg_rr":               round(avg_rr, 2),
        "expectancy":           round(expectancy, 3),
        "profit_factor":        pf,
        "sharpe_annualised":    sharpe,
        "max_drawdown_pct":     round(max_dd, 2),
        "total_return_pct":     round(total_return, 2),
        "metrics_reliable":     metrics_reliable,
        "statistical_reliability": reliability,
        "data_quality":         data_quality,
        "trades":               trades[-20:],      # last 20 for display
    }


# ── Portfolio backtest ────────────────────────────────────────────────────────

def run_portfolio_backtest(stock_data: dict, period_days: int = 504) -> dict:
    """
    Run backtests across all stocks and aggregate results.

    Only stocks with `statistical_reliability` ≠ "INSUFFICIENT" are included
    in aggregate metrics.  Stocks that returned errors or had too few trades
    are counted separately so the caller knows how many were dropped.
    """
    all_results      = []
    skipped_symbols  = []
    unreliable_symbols = []

    for symbol, df in stock_data.items():
        try:
            result = run_backtest(symbol, df, period_days)
            if "error" in result:
                skipped_symbols.append({"symbol": symbol, "reason": result["error"]})
                logger.info(f"Backtest skipped {symbol}: {result['error']}")
            elif result.get("statistical_reliability") == "INSUFFICIENT":
                unreliable_symbols.append({
                    "symbol": symbol,
                    "trades": result["total_trades"],
                    "note":   "Too few trades — excluded from aggregate metrics",
                })
                logger.info(f"Backtest {symbol}: {result['total_trades']} trades — INSUFFICIENT, excluded")
            else:
                all_results.append(result)
                logger.info(
                    f"Backtest {symbol}: {result['total_trades']} trades, "
                    f"{result['win_rate']}% WR [{result['statistical_reliability']}]"
                )
        except Exception as e:
            logger.warning(f"Backtest failed for {symbol}: {e}")
            skipped_symbols.append({"symbol": symbol, "reason": str(e)})

    if not all_results:
        return {
            "error": (
                "No stocks produced sufficient data for reliable backtest metrics. "
                f"{len(skipped_symbols)} skipped (errors), "
                f"{len(unreliable_symbols)} excluded (< {_MIN_TRADES_LOW} trades). "
                "Fetch 3+ years of daily data per symbol."
            ),
            "skipped":    skipped_symbols,
            "unreliable": unreliable_symbols,
        }

    all_win_rates  = [r["win_rate"]         for r in all_results]
    all_expectancy = [r["expectancy"]        for r in all_results]
    all_dd         = [r["max_drawdown_pct"]  for r in all_results]
    all_trades     = [r["total_trades"]      for r in all_results]
    all_pf         = [r["profit_factor"]     for r in all_results if r["profit_factor"] is not None]
    all_sharpe     = [r["sharpe_annualised"] for r in all_results if r["sharpe_annualised"] is not None]

    total_trades_agg = sum(all_trades)
    agg_reliability  = _reliability_label(total_trades_agg)

    return {
        "period_days":            period_days,
        "stocks_tested":          len(all_results),
        "stocks_skipped":         len(skipped_symbols),
        "stocks_unreliable":      len(unreliable_symbols),
        "total_trades":           total_trades_agg,
        "statistical_reliability": agg_reliability,
        "avg_win_rate":           round(float(np.mean(all_win_rates)), 1),
        "avg_expectancy":         round(float(np.mean(all_expectancy)), 3),
        "avg_profit_factor":      round(float(np.mean(all_pf)), 3) if all_pf else None,
        "avg_sharpe":             round(float(np.mean(all_sharpe)), 3) if all_sharpe else None,
        "avg_max_drawdown_pct":   round(float(np.mean(all_dd)), 2),
        "best_stock":             max(all_results, key=lambda x: x["win_rate"])["symbol"],
        "worst_stock":            min(all_results, key=lambda x: x["win_rate"])["symbol"],
        "individual_results":     sorted(all_results,
                                         key=lambda x: x["win_rate"],
                                         reverse=True)[:10],
        "skipped":                skipped_symbols,
        "unreliable":             unreliable_symbols,
    }
