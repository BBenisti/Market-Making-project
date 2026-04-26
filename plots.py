"""
plots.py - Visualization of spread history and P&L.

Generates matplotlib charts:
  - Historical effective spreads by order size
  - Cumulative P&L over time (realized + unrealized)
  - Position evolution over time
"""

import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime


def plot_spread_history(spread_analytics, save=True):
    """Plot rolling effective spreads for each target order size."""
    fig, ax = plt.subplots(figsize=(12, 6))

    for size in spread_analytics.order_sizes:
        data = spread_analytics._history.get(size, [])
        if data:
            ax.plot(data, label=f"{size} BTC", alpha=0.8)

    ax.set_title("Effective Spread Over Time by Order Size")
    ax.set_xlabel("Observation Index")
    ax.set_ylabel("Spread (USD)")
    ax.legend()
    ax.grid(True, alpha=0.3)

    if save:
        fig.savefig("spread_history.png", dpi=150, bbox_inches="tight")
        print("[PLOT] Saved spread_history.png")
    plt.show()


def plot_pnl(market_maker, save=True):
    """Plot cumulative realized P&L and position evolution."""
    trades = market_maker.executed_trades
    if not trades:
        print("[PLOT] No trades to plot.")
        return

    # Reconstruct cumulative P&L from trade log
    timestamps = []
    cum_realized = []
    positions = []
    running_pnl = 0.0

    for i, t in enumerate(trades):
        timestamps.append(datetime.fromtimestamp(t["timestamp"]))
        positions.append(t["position_after"])

        # Approximate realized P&L: use the market_maker's final value
        # scaled by trade index (linear interpolation)
        if i > 0:
            prev = trades[i - 1]
            if t["side"] == "sell" and prev.get("position_after", 0) > 0:
                running_pnl += t["size"] * (t["price"] - prev["price"])
            elif t["side"] == "buy" and prev.get("position_after", 0) < 0:
                running_pnl += t["size"] * (prev["price"] - t["price"])
        cum_realized.append(running_pnl)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    # P&L chart
    ax1.plot(timestamps, cum_realized, color="green", linewidth=1.2)
    ax1.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    ax1.set_title("Approximate Cumulative Realized P&L")
    ax1.set_ylabel("P&L (USD)")
    ax1.grid(True, alpha=0.3)

    # Position chart
    ax2.fill_between(timestamps, positions, 0, alpha=0.3,
                     color="blue", label="Position")
    ax2.plot(timestamps, positions, color="blue", linewidth=0.8)
    ax2.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    ax2.set_title("BTC Position Over Time")
    ax2.set_xlabel("Time")
    ax2.set_ylabel("Position (BTC)")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    if save:
        fig.savefig("pnl_position.png", dpi=150, bbox_inches="tight")
        print("[PLOT] Saved pnl_position.png")
    plt.show()