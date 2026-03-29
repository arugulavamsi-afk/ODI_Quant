"""
SQLite storage layer for ODI Quant results.
Stores daily scan results and global sentiment snapshots.
"""
import sqlite3
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# On cloud (Linux), use /tmp. On Windows, use local storage folder.
_default_db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "odi_quant.db")
DB_PATH = os.environ.get("DB_PATH", _default_db if os.name == "nt" else "/tmp/odi_quant.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT,
                sector TEXT,
                long_score INTEGER,
                short_score INTEGER,
                category TEXT,
                direction TEXT,
                entry REAL,
                stop_loss REAL,
                target1 REAL,
                target2 REAL,
                risk_pct REAL,
                explanation TEXT,
                indicators_json TEXT,
                long_signal_json TEXT,
                short_signal_json TEXT,
                trade_levels_json TEXT,
                rank INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS global_sentiment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT NOT NULL,
                score REAL,
                classification TEXT,
                long_adjustment INTEGER,
                short_adjustment INTEGER,
                components_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_daily_results_date ON daily_results(run_date)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_global_sentiment_date ON global_sentiment(run_date)")
        conn.commit()
        logger.info("Database initialized successfully")
    finally:
        conn.close()


def save_results(run_date: str, stocks: list, global_sentiment: dict):
    """Save pipeline results to database."""
    conn = get_connection()
    try:
        c = conn.cursor()

        # Delete existing results for this date
        c.execute("DELETE FROM daily_results WHERE run_date = ?", (run_date,))
        c.execute("DELETE FROM global_sentiment WHERE run_date = ?", (run_date,))

        # Save global sentiment
        c.execute("""
            INSERT INTO global_sentiment (run_date, score, classification, long_adjustment, short_adjustment, components_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            run_date,
            global_sentiment.get("score", 0),
            global_sentiment.get("classification", "NEUTRAL"),
            global_sentiment.get("long_adjustment", 0),
            global_sentiment.get("short_adjustment", 0),
            json.dumps(global_sentiment.get("components", {})),
        ))

        # Save each stock result
        for stock in stocks:
            indicators = stock.get("indicators", {})
            trade_levels = stock.get("trade_levels", {})
            classification = stock.get("classification", {})

            c.execute("""
                INSERT INTO daily_results (
                    run_date, symbol, name, sector, long_score, short_score,
                    category, direction, entry, stop_loss, target1, target2, risk_pct,
                    explanation, indicators_json, long_signal_json, short_signal_json,
                    trade_levels_json, rank
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run_date,
                stock.get("symbol"),
                stock.get("name"),
                stock.get("sector"),
                stock.get("long_score", 0),
                stock.get("short_score", 0),
                classification.get("category", "NO_TRADE"),
                classification.get("direction", "LONG"),
                trade_levels.get("entry"),
                trade_levels.get("stop_loss"),
                trade_levels.get("target1"),
                trade_levels.get("target2"),
                trade_levels.get("risk_pct"),
                stock.get("explanation", ""),
                json.dumps(indicators),
                json.dumps(stock.get("long_signal", {})),
                json.dumps(stock.get("short_signal", {})),
                json.dumps(trade_levels),
                stock.get("rank", 0),
            ))

        conn.commit()
        logger.info(f"Saved {len(stocks)} results for {run_date}")
    finally:
        conn.close()


def get_latest_results() -> dict:
    """Get the most recent pipeline results."""
    conn = get_connection()
    try:
        c = conn.cursor()

        # Get latest run date
        c.execute("SELECT MAX(run_date) as max_date FROM daily_results")
        row = c.fetchone()
        if not row or not row["max_date"]:
            return None

        run_date = row["max_date"]
        return get_results_by_date(run_date)
    finally:
        conn.close()


def get_results_by_date(run_date: str) -> dict:
    """Get pipeline results for a specific date."""
    conn = get_connection()
    try:
        c = conn.cursor()

        # Fetch stocks
        c.execute("""
            SELECT * FROM daily_results WHERE run_date = ? ORDER BY rank ASC
        """, (run_date,))
        rows = c.fetchall()

        stocks = []
        for row in rows:
            stock = dict(row)
            # Parse JSON fields
            for field in ("indicators_json", "long_signal_json", "short_signal_json", "trade_levels_json"):
                try:
                    stock[field] = json.loads(stock[field]) if stock[field] else {}
                except Exception:
                    stock[field] = {}
            stocks.append(stock)

        # Fetch global sentiment
        c.execute("SELECT * FROM global_sentiment WHERE run_date = ? ORDER BY id DESC LIMIT 1", (run_date,))
        gs_row = c.fetchone()
        global_sentiment = None
        if gs_row:
            global_sentiment = dict(gs_row)
            try:
                global_sentiment["components_json"] = json.loads(global_sentiment["components_json"])
            except Exception:
                global_sentiment["components_json"] = {}

        # Summary
        categories = [s.get("category", "NO_TRADE") for s in stocks]
        summary = {
            "total": len(stocks),
            "high_prob_long": sum(1 for c in categories if c == "HIGH_PROB_LONG"),
            "high_prob_short": sum(1 for c in categories if c == "HIGH_PROB_SHORT"),
            "watchlist": sum(1 for c in categories if c == "WATCHLIST"),
            "no_trade": sum(1 for c in categories if c == "NO_TRADE"),
        }

        return {
            "run_date": run_date,
            "stocks": stocks,
            "global_sentiment": global_sentiment,
            "summary": summary,
        }
    finally:
        conn.close()


def get_available_dates() -> list:
    """Get list of all dates with results."""
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT DISTINCT run_date FROM daily_results ORDER BY run_date DESC LIMIT 30")
        rows = c.fetchall()
        return [row["run_date"] for row in rows]
    finally:
        conn.close()
