"""
trades.py - Trade feed handler.

Captures real-time executed trades from the Kraken WebSocket feed.
Each trade entry is [price, volume, timestamp, side, order_type, misc].
Stores the N most recent trades for display and fill simulation.
Thread-safe via Lock.
"""

from collections import deque
from threading import Lock


class TradeFeed:

    def __init__(self, max_trades=100):
        self.trades = deque(maxlen=max_trades)
        self._lock = Lock()

    def handle_trade(self, trade_list):
        """
        Process a Kraken trade message.
        Each entry: [price, volume, timestamp, side, order_type, misc]
          - side: "b" (buy) or "s" (sell)
        """
        with self._lock:
            for t in trade_list:
                self.trades.append({
                    "price": float(t[0]),
                    "volume": float(t[1]),
                    "timestamp": float(t[2]),
                    "side": "buy" if t[3] == "b" else "sell"
                })

    def get_recent(self, n=10):
        """Return the last N trades, most recent first."""
        with self._lock:
            return list(self.trades)[-n:][::-1]

    def get_last_price(self):
        """Return the most recent trade price, or None."""
        with self._lock:
            if self.trades:
                return self.trades[-1]["price"]
            return None
        