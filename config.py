"""
config.py - Simulation parameters for BTC-USD market making.
"""

# Connection — Kraken public WebSocket (no API key required)
WS_URL = "wss://ws.kraken.com"
PRODUCT_ID = "XBT/USD"

# Order book depth (levels per side)
ORDER_BOOK_DEPTH = 100

# Target sizes for effective spread computation (in BTC)
ORDER_SIZES = [0.1, 1, 5, 10]

# Adaptive spread parameters
SPREAD_MARKET_MULTIPLIER = 1.5
MIN_SPREAD_BPS = 0.5
MAX_SPREAD_BPS = 20
VOL_SENSITIVITY = 0.5
VOL_WINDOW_SECONDS = 60
MIN_TICKS_FOR_VOL = 10
SPREAD_REFERENCE_SIZE = 5

# Market making — dynamic quote sizing
BASE_QUOTE_SIZE_BTC = 3.0
MIN_QUOTE_SIZE_BTC = 0.01
SKEW_FACTOR = 2.0

# Risk limits
INITIAL_CAPITAL = 1_000_000
MAX_NOTIONAL_EXPOSURE = 1_000_000
MAX_LOSS = 100_000

# Dashboard refresh rate (seconds)
DISPLAY_REFRESH_INTERVAL = 1