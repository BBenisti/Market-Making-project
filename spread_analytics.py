"""
spread_analytics.py - Effective spread computation engine.

For each target order size, computes the volume-weighted average price
(VWAP) on both bid and ask sides by sweeping through the book.
The effective spread is the difference between ask VWAP and bid VWAP.

Tracks historical spread values to compute running statistics:
average, median, min, max.
"""

from collections import defaultdict
from threading import Lock
import numpy as np


class SpreadAnalytics:

    def __init__(self, order_sizes):
        self.order_sizes = order_sizes  # [0.1, 1, 5, 10]
        self._history = defaultdict(list)  # {size: [spread_values]}
        self._lock = Lock()

    def compute_vwap(self, levels, target_size):
        """
        Sweep through price levels to fill target_size.
        Returns the volume-weighted average price, or None if
        the book does not have enough liquidity.

        Args:
            levels: list of (price, size) sorted by aggressiveness
            target_size: quantity to fill in BTC
        """
        filled = 0.0
        cost = 0.0

        for price, size in levels:
            fill_qty = min(size, target_size - filled)
            cost += fill_qty * price
            filled += fill_qty
            if filled >= target_size - 1e-10:
                return cost / filled

        return None  # insufficient liquidity

    def compute_spreads(self, book):
        """
        Compute effective spreads for all target sizes given the
        current order book state.

        Returns:
            dict: {size: {"spread": float, "bid_vwap": float,
                          "ask_vwap": float}} or None per size
                  if liquidity is insufficient.
        """
        bids, asks = book.get_top_levels(depth=500)
        results = {}

        for size in self.order_sizes:
            bid_vwap = self.compute_vwap(bids, size)
            ask_vwap = self.compute_vwap(asks, size)

            if bid_vwap and ask_vwap:
                spread = ask_vwap - bid_vwap
                results[size] = {
                    "spread": spread,
                    "bid_vwap": bid_vwap,
                    "ask_vwap": ask_vwap
                }
                with self._lock:
                    self._history[size].append(spread)
            else:
                results[size] = None

        return results

    def get_statistics(self, size):
        """
        Return running statistics for a given order size.

        Returns:
            dict with keys: avg, median, min, max, count.
            None if no data has been recorded yet.
        """
        with self._lock:
            data = self._history.get(size, [])
        if not data:
            return None
        arr = np.array(data)
        return {
            "avg": float(np.mean(arr)),
            "median": float(np.median(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "count": len(data)
        }