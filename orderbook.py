"""
orderbook.py - Level 2 order book engine.

Maintains a local replica of the order book from the Kraken WebSocket feed.
Kraken sends:
  - Snapshot: full book on subscription (keyed "as"/"bs")
  - Updates: incremental deltas (keyed "a"/"b")
  - Levels: [price, volume, timestamp]
  - Volume == "0.00000000" signals level removal

Kraken uses a fixed-depth book: updates may introduce new levels outside
the initial window without an explicit removal. The local copy is pruned
to max_depth after each update to prevent stale levels from polluting
top-of-book computations.

Thread-safe via Lock (WebSocket runs on a separate thread).
"""

from threading import Lock


class OrderBook:

    def __init__(self, max_depth=25):
        self.bids = {}  # {price: size}
        self.asks = {}
        self.max_depth = max_depth
        self._lock = Lock()
        self.is_initialized = False

    def handle_snapshot(self, asks, bids):
        """Replace book state with the initial snapshot."""
        with self._lock:
            self.bids.clear()
            self.asks.clear()
            for level in bids:
                p, s = float(level[0]), float(level[1])
                if s > 0:
                    self.bids[p] = s
            for level in asks:
                p, s = float(level[0]), float(level[1])
                if s > 0:
                    self.asks[p] = s
            self.is_initialized = True

    def handle_update(self, data):
        """Apply incremental update, then prune stale levels."""
        with self._lock:
            if "b" in data:
                for level in data["b"]:
                    p, s = float(level[0]), float(level[1])
                    if s == 0:
                        self.bids.pop(p, None)
                    else:
                        self.bids[p] = s
            if "a" in data:
                for level in data["a"]:
                    p, s = float(level[0]), float(level[1])
                    if s == 0:
                        self.asks.pop(p, None)
                    else:
                        self.asks[p] = s
            self._prune()

    def _prune(self):
        """Keep only the top max_depth levels per side (assumes lock held)."""
        if len(self.bids) > self.max_depth:
            top_bids = sorted(self.bids.keys(), reverse=True)[:self.max_depth]
            self.bids = {p: self.bids[p] for p in top_bids}
        if len(self.asks) > self.max_depth:
            top_asks = sorted(self.asks.keys())[:self.max_depth]
            self.asks = {p: self.asks[p] for p in top_asks}

    def get_top_levels(self, depth=10):
        """Top N levels per side. Bids: highest first. Asks: lowest first."""
        with self._lock:
            sorted_bids = sorted(self.bids.items(), key=lambda x: -x[0])[:depth]
            sorted_asks = sorted(self.asks.items(), key=lambda x: x[0])[:depth]
        return sorted_bids, sorted_asks

    def get_mid_price(self):
        """Mid-price: (best_bid + best_ask) / 2. None if book is empty or crossed."""
        with self._lock:
            if not self.bids or not self.asks:
                return None
            best_bid = max(self.bids.keys())
            best_ask = min(self.asks.keys())
            if best_bid >= best_ask:
                return None  # crossed book: do not quote
        return (best_bid + best_ask) / 2

    def get_best_bid_ask(self):
        """Returns (best_bid, best_ask). None if side is empty."""
        with self._lock:
            best_bid = max(self.bids.keys()) if self.bids else None
            best_ask = min(self.asks.keys()) if self.asks else None
        return best_bid, best_ask