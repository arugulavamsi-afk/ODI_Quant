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

MIN_VOLUME = 500000          # Minimum daily volume for liquidity
MIN_PRICE = 10               # Minimum stock price (INR)
MAX_PRICE = 50000            # Maximum stock price
LOOKBACK_DAYS = 252          # 1 year lookback for indicators
ATR_PERIOD = 14
MA_SHORT = 20
MA_MEDIUM = 50
MA_LONG = 200
VOLUME_LOOKBACK = 20
BREAKOUT_PERIOD = 20
HIGH_PROB_THRESHOLD = 70     # Score >= 70 -> High Probability
WATCHLIST_THRESHOLD = 50     # Score 50-69 -> Watchlist
LONG_SCORE_BOOST = 5         # Applied when global sentiment bullish
SHORT_SCORE_BOOST = 5
DB_PATH = "storage/odi_quant.db"
API_HOST = "0.0.0.0"
API_PORT = 8000
