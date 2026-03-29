# Configuration constants for ODI Quant Trading System

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
