# Configuration constants for ODI Quant Trading System

# ── Portfolio / Risk Settings ──────────────────────────────────────────────────
# ACCOUNT_CAPITAL: Set this to your actual trading capital in INR.
#   Position sizing, capital-at-risk %, and risk warnings are all derived from
#   this number. Leaving it at the wrong value gives misleading position sizes.
#   Examples: 500_000 = ₹5L, 1_000_000 = ₹10L, 5_000_000 = ₹50L
ACCOUNT_CAPITAL      = 500_000     # ₹ — CHANGE THIS to your real trading capital

# RISK_PER_TRADE_PCT: Maximum % of ACCOUNT_CAPITAL to risk on a single trade.
#   Professional standard: 1–2%. Aggressive: up to 2%. Never exceed 2% per trade.
#   A losing streak of 10 trades at 2% each = 18% drawdown before compounding.
RISK_PER_TRADE_PCT   = 1.0         # % of capital — max risk per trade (default: 1%)

# RISK_WARNING_PCT: Warn in trade output when effective risk exceeds this level.
#   Set to 2.0 to flag any trade that would risk more than 2% of your capital.
RISK_WARNING_PCT     = 2.0         # % of capital — threshold for ⚠ risk warning

# ── Portfolio-Level Risk Controls ─────────────────────────────────────────────
# MAX_DAILY_LOSS_PCT: Stop trading for the day when cumulative loss hits this %.
#   Professional desks enforce this without exception. Prevents revenge trading
#   and spiral losses. At 2%, 3 losers at 1% risk = you stop for the day.
MAX_DAILY_LOSS_PCT        = 2.0    # % of capital — stop trading if hit

# MAX_CONCURRENT_POSITIONS: Maximum open positions at any time.
#   Prevents correlated exposure on broad market selloffs. All signals on a scan
#   day are correlated (same market conditions triggered them all). Take at most 5.
MAX_CONCURRENT_POSITIONS  = 5      # max open trades simultaneously

# MAX_SECTOR_EXPOSURE_PCT: Maximum % of capital in any single sector at once.
#   Prevents HDFC/ICICI/Axis/Kotak all getting long signals on the same banking day.
MAX_SECTOR_EXPOSURE_PCT   = 25.0   # % of capital per sector

# ── Commission / Cost Model ────────────────────────────────────────────────────
# COMMISSION_PCT: One-way cost per trade (brokerage + STT + exchange fees).
#   Used in backtest to compute commission-adjusted expectancy.
#   Zerodha equity delivery: ~0.03% + STT. Intraday F&O: ~0.05% all-in per leg.
#   Conservative estimate for swing trades (delivery + STT + exchange): 0.05% one-way.
#   Round-trip = 2 × COMMISSION_PCT applied to entry value.
COMMISSION_PCT            = 0.0005  # 0.05% per leg → 0.1% round-trip

MIN_VOLUME = 500000          # Minimum daily volume for liquidity
MIN_PRICE = 10               # Minimum stock price (INR)
MAX_PRICE = 50000            # Maximum stock price
LOOKBACK_DAYS = 252          # 1 year lookback for indicators
ATR_PERIOD = 14
MA_SHORT = 20
MA_MEDIUM = 50
MA_LONG = 200
VOLUME_LOOKBACK = 20
BREAKOUT_PERIOD = 252        # 52-week high/low — clears multi-month institutional resistance
HIGH_PROB_THRESHOLD = 70     # Base HIGH_PROB threshold (sentiment-adjusted in ranker.py)
WATCHLIST_THRESHOLD = 50     # Score 50-69 -> Watchlist
DB_PATH = "storage/odi_quant.db"
API_HOST = "0.0.0.0"
API_PORT = 8000
