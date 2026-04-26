"""
market_maker.py - Market making strategy with adaptive spread and dynamic sizing.

Core logic:
  1. Compute mid-price from the live order book
  2. Calculate half-spread based on observed market spread and realized vol
  3. Apply position-based skewing to incentivize inventory mean-reversion
  4. Compute dynamic quote size based on vol regime and risk capacity
  5. Post bid and ask quotes around the adjusted mid
  6. Simulate fills using the real-time trade feed
  7. Enforce risk limits (max notional exposure, max loss)
"""

import time
import math
from collections import deque
from threading import Lock
from config import (
    MAX_SPREAD_BPS, MIN_SPREAD_BPS, VOL_SENSITIVITY,
    SPREAD_MARKET_MULTIPLIER,
    VOL_WINDOW_SECONDS, MIN_TICKS_FOR_VOL, BASE_QUOTE_SIZE_BTC,
    MIN_QUOTE_SIZE_BTC, SKEW_FACTOR, MAX_NOTIONAL_EXPOSURE,
    MAX_LOSS, INITIAL_CAPITAL, SPREAD_REFERENCE_SIZE
)


class VolatilityTracker:

    def __init__(self, window_seconds=60, min_ticks=10):
        self.window = window_seconds
        self.min_ticks = min_ticks
        self._ticks = deque()
        self._lock = Lock()

    def add_tick(self, mid_price):
        now = time.time()
        with self._lock:
            self._ticks.append((now, mid_price))
            cutoff = now - self.window
            while self._ticks and self._ticks[0][0] < cutoff:
                self._ticks.popleft()

    def get_volatility(self):
        with self._lock:
            if len(self._ticks) < self.min_ticks:
                return None
            prices = [t[1] for t in self._ticks]

        log_returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0:
                log_returns.append(math.log(prices[i] / prices[i - 1]))

        if len(log_returns) < 2:
            return None

        mean = sum(log_returns) / len(log_returns)
        variance = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
        vol_pct = math.sqrt(variance)
        last_price = prices[-1]
        return vol_pct * last_price

    def is_ready(self):
        with self._lock:
            return len(self._ticks) >= self.min_ticks


class MarketMaker:

    def __init__(self):
        self.position_btc = 0.0
        self.avg_entry_price = 0.0
        self.realized_pnl = 0.0
        self.executed_trades = []

        self.bid_price = None
        self.ask_price = None
        self.quote_size = BASE_QUOTE_SIZE_BTC

        self.vol_tracker = VolatilityTracker(
            window_seconds=VOL_WINDOW_SECONDS,
            min_ticks=MIN_TICKS_FOR_VOL
        )

        self._last_market_spread = None

        self.is_halted = False
        self._last_processed_ts = 0.0
        self._lock = Lock()

    def update_market_spread(self, spread_data, reference_size):
        """Update the observed market spread for adaptive quoting."""
        if spread_data and reference_size in spread_data:
            s = spread_data[reference_size]
            if s is not None:
                self._last_market_spread = s["spread"] / 2

    def _compute_quote_size(self, mid_price):
        """Dynamic quote size based on vol regime and risk utilization."""
        if mid_price is None or mid_price == 0:
            return MIN_QUOTE_SIZE_BTC

        vol = self.vol_tracker.get_volatility()
        if vol is not None and self._last_market_spread is not None:
            vol_ratio = vol / self._last_market_spread if self._last_market_spread > 0 else 1.0
            vol_factor = 1.0 / (1.0 + vol_ratio)
        elif vol is not None:
            vol_factor = 0.5
        else:
            vol_factor = 0.5

        vol_adjusted_base = BASE_QUOTE_SIZE_BTC * vol_factor

        current_exposure = abs(self.position_btc * mid_price)
        exposure_ratio = current_exposure / MAX_NOTIONAL_EXPOSURE
        exposure_factor = max(0.0, 1.0 - exposure_ratio)

        unrealized = self.get_unrealized_pnl(mid_price)
        total_pnl = self.realized_pnl + unrealized
        if total_pnl < 0:
            loss_ratio = abs(total_pnl) / MAX_LOSS
            loss_factor = max(0.0, 1.0 - loss_ratio)
        else:
            loss_factor = 1.0

        risk_factor = min(exposure_factor, loss_factor)

        raw_size = MIN_QUOTE_SIZE_BTC + (vol_adjusted_base - MIN_QUOTE_SIZE_BTC) * risk_factor
        return round(max(MIN_QUOTE_SIZE_BTC, raw_size), 4)

    def _compute_half_spread(self, mid_price):
        """
        Compute half-spread based on observed market spread + vol.
        Clamped between absolute floor and ceiling.
        """
        floor_spread = mid_price * MIN_SPREAD_BPS / 10_000
        max_spread = mid_price * MAX_SPREAD_BPS / 10_000

        if self._last_market_spread is not None:
            base = self._last_market_spread * SPREAD_MARKET_MULTIPLIER
        else:
            base = floor_spread

        vol = self.vol_tracker.get_volatility()
        if vol is not None:
            half_spread = base + VOL_SENSITIVITY * vol
        else:
            half_spread = base

        return max(floor_spread, min(half_spread, max_spread))

    def _compute_skew(self, mid_price):
        """Position-based skew. Long -> shift down, short -> shift up."""
        if mid_price == 0 or self.quote_size <= 0:
            return 0.0
        normalized_pos = self.position_btc / self.quote_size
        if self._last_market_spread is not None:
            ref_spread = self._last_market_spread
        else:
            ref_spread = mid_price * MIN_SPREAD_BPS / 10_000
        return -SKEW_FACTOR * normalized_pos * ref_spread

    def update_quotes(self, book):
        """Recompute quotes based on book, vol, position, and risk."""
        if self.is_halted:
            self.bid_price = None
            self.ask_price = None
            return

        mid = book.get_mid_price()
        if mid is None:
            return

        self.vol_tracker.add_tick(mid)
        self.quote_size = self._compute_quote_size(mid)

        half_spread = self._compute_half_spread(mid)
        skew = self._compute_skew(mid)

        adjusted_mid = mid + skew
        self.bid_price = round(adjusted_mid - half_spread, 2)
        self.ask_price = round(adjusted_mid + half_spread, 2)

        self._check_risk_pre_quote(mid)

    def _check_risk_pre_quote(self, mid_price):
        """Cancel quotes on the side that would breach risk limits."""
        if self.bid_price:
            potential_pos = self.position_btc + self.quote_size
            if abs(potential_pos * mid_price) > MAX_NOTIONAL_EXPOSURE:
                self.bid_price = None

        if self.ask_price:
            potential_pos = self.position_btc - self.quote_size
            if abs(potential_pos * mid_price) > MAX_NOTIONAL_EXPOSURE:
                self.ask_price = None

        unrealized = self.get_unrealized_pnl(mid_price)
        total_pnl = self.realized_pnl + unrealized
        if total_pnl < -MAX_LOSS:
            self.is_halted = True
            self.bid_price = None
            self.ask_price = None

    def check_fills(self, trade_feed):
        """Check new market trades against our quotes."""
        if self.is_halted:
            return

        recent = trade_feed.get_recent(20)
        new_trades = [t for t in reversed(recent)
                      if t["timestamp"] > self._last_processed_ts]

        for trade in new_trades:
            if (trade["side"] == "sell"
                    and self.bid_price is not None
                    and trade["price"] <= self.bid_price):
                self._execute_fill("buy", self.bid_price,
                                   self.quote_size, trade["timestamp"])

            elif (trade["side"] == "buy"
                  and self.ask_price is not None
                  and trade["price"] >= self.ask_price):
                self._execute_fill("sell", self.ask_price,
                                   self.quote_size, trade["timestamp"])

            self._last_processed_ts = trade["timestamp"]

    def _execute_fill(self, side, price, size, trade_ts):
        """Record a simulated fill, update position, cancel filled quote."""
        with self._lock:
            if side == "buy":
                self._update_position_buy(price, size)
                self.bid_price = None
            else:
                self._update_position_sell(price, size)
                self.ask_price = None

            self.executed_trades.append({
                "timestamp": time.time(),
                "side": side,
                "price": price,
                "size": size,
                "position_after": self.position_btc,
                "quote_size_at_fill": size
            })

    def _update_position_buy(self, price, size):
        if self.position_btc >= 0:
            total_cost = self.avg_entry_price * self.position_btc + price * size
            self.position_btc += size
            self.avg_entry_price = total_cost / self.position_btc if self.position_btc != 0 else 0
        else:
            cover_size = min(size, abs(self.position_btc))
            self.realized_pnl += cover_size * (self.avg_entry_price - price)
            self.position_btc += size
            if self.position_btc > 0:
                self.avg_entry_price = price
            elif self.position_btc == 0:
                self.avg_entry_price = 0.0

    def _update_position_sell(self, price, size):
        if self.position_btc <= 0:
            total_cost = abs(self.avg_entry_price * self.position_btc) + price * size
            self.position_btc -= size
            self.avg_entry_price = total_cost / abs(self.position_btc) if self.position_btc != 0 else 0
        else:
            sell_size = min(size, self.position_btc)
            self.realized_pnl += sell_size * (price - self.avg_entry_price)
            self.position_btc -= size
            if self.position_btc < 0:
                self.avg_entry_price = price
            elif self.position_btc == 0:
                self.avg_entry_price = 0.0

    def get_unrealized_pnl(self, mid_price):
        if self.position_btc == 0 or mid_price is None:
            return 0.0
        if self.position_btc > 0:
            return self.position_btc * (mid_price - self.avg_entry_price)
        else:
            return abs(self.position_btc) * (self.avg_entry_price - mid_price)

    def get_exposure(self, mid_price):
        if mid_price is None:
            return 0.0
        return abs(self.position_btc * mid_price)

    def get_status(self, mid_price):
        unrealized = self.get_unrealized_pnl(mid_price)
        return {
            "position_btc": self.position_btc,
            "avg_entry": self.avg_entry_price,
            "exposure_usd": self.get_exposure(mid_price),
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": unrealized,
            "total_pnl": self.realized_pnl + unrealized,
            "bid": self.bid_price,
            "ask": self.ask_price,
            "quote_size": self.quote_size,
            "half_spread": (self.ask_price - self.bid_price) / 2 if self.bid_price and self.ask_price else None,
            "vol": self.vol_tracker.get_volatility(),
            "is_halted": self.is_halted,
            "trade_count": len(self.executed_trades)
        }