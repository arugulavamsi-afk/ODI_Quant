"""
Data fetching module using yfinance.
Handles stock OHLCV data and global market data.
"""
import yfinance as yf
import pandas as pd
import numpy as np
import warnings
import logging
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

GLOBAL_SYMBOLS = {
    "^GSPC": "S&P 500",
    "^IXIC": "NASDAQ",
    "^N225": "Nikkei 225",
    "^HSI": "Hang Seng",
    "CL=F": "Crude Oil",
    "GC=F": "Gold",
    "DX-Y.NYB": "US Dollar Index",
    "^NSEI": "Nifty 50",
}


def fetch_stock_data(symbol: str, period: str = "1y") -> pd.DataFrame | None:
    """
    Fetch OHLCV data for a single stock symbol.
    Returns a clean DataFrame or None if fetch fails.
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, auto_adjust=True)

        if df is None or df.empty:
            logger.warning(f"No data returned for {symbol}")
            return None

        # Standardize column names
        df.columns = [c.strip() for c in df.columns]
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # Drop rows with all NaN
        df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])

        if len(df) < 50:
            logger.warning(f"Insufficient data for {symbol}: {len(df)} rows")
            return None

        return df

    except Exception as e:
        logger.warning(f"Error fetching {symbol}: {e}")
        return None


def fetch_all_stocks(universe: dict) -> dict:
    """
    Fetch OHLCV data for all stocks in the universe.
    Returns dict: {symbol: DataFrame}
    Skips failed symbols gracefully.
    """
    results = {}
    total = len(universe)
    logger.info(f"Fetching data for {total} stocks...")

    for i, symbol in enumerate(universe.keys()):
        try:
            df = fetch_stock_data(symbol)
            if df is not None and len(df) >= 200:
                results[symbol] = df
                logger.info(f"[{i+1}/{total}] {symbol}: {len(df)} days OK")
            else:
                logger.warning(f"[{i+1}/{total}] {symbol}: skipped (insufficient data)")
        except Exception as e:
            logger.warning(f"[{i+1}/{total}] {symbol}: failed - {e}")

    logger.info(f"Successfully fetched {len(results)}/{total} stocks")
    return results


def fetch_global_data() -> dict:
    """
    Fetch global market data: S&P500, NASDAQ, Nikkei, HSI, Crude, Gold, DXY, Nifty50.
    Returns dict with 1d % change and 5d trend for each symbol.
    """
    global_data = {}

    for symbol, name in GLOBAL_SYMBOLS.items():
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="10d", auto_adjust=True)

            if df is None or df.empty or len(df) < 2:
                logger.warning(f"No global data for {symbol}")
                global_data[symbol] = {
                    "name": name,
                    "change_1d": 0.0,
                    "change_5d": 0.0,
                    "last_close": None,
                    "trend": "NEUTRAL",
                }
                continue

            df = df.dropna(subset=["Close"])
            df = df.sort_index()

            last_close = float(df["Close"].iloc[-1])
            prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else last_close
            change_1d = ((last_close - prev_close) / prev_close * 100) if prev_close != 0 else 0.0

            # 5-day trend
            if len(df) >= 6:
                close_5d_ago = float(df["Close"].iloc[-6])
                change_5d = ((last_close - close_5d_ago) / close_5d_ago * 100) if close_5d_ago != 0 else 0.0
            else:
                change_5d = change_1d

            trend = "BULLISH" if change_5d > 1 else ("BEARISH" if change_5d < -1 else "NEUTRAL")

            global_data[symbol] = {
                "name": name,
                "change_1d": round(change_1d, 3),
                "change_5d": round(change_5d, 3),
                "last_close": round(last_close, 2),
                "trend": trend,
            }

        except Exception as e:
            logger.warning(f"Error fetching global data for {symbol}: {e}")
            global_data[symbol] = {
                "name": name,
                "change_1d": 0.0,
                "change_5d": 0.0,
                "last_close": None,
                "trend": "NEUTRAL",
            }

    return global_data


def fetch_nifty_data(period: str = "1y") -> pd.DataFrame | None:
    """
    Fetch NIFTY 50 (^NSEI) OHLCV data.
    More lenient than fetch_stock_data — volume may be zero for indices.
    Returns clean DataFrame or None on failure.
    """
    try:
        ticker = yf.Ticker("^NSEI")
        df = ticker.history(period=period, auto_adjust=True)

        if df is None or df.empty:
            logger.warning("No data returned for ^NSEI")
            return None

        df.columns = [c.strip() for c in df.columns]
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df.dropna(subset=["Open", "High", "Low", "Close"])

        if "Volume" not in df.columns:
            df["Volume"] = 0

        if len(df) < 50:
            logger.warning(f"Insufficient NIFTY data: {len(df)} rows")
            return None

        logger.info(f"NIFTY data fetched: {len(df)} days")
        return df

    except Exception as e:
        logger.warning(f"Error fetching NIFTY data: {e}")
        return None
