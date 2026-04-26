"""
export.py - Export trade logs and P&L history to CSV files.

Generates two files:
  - trade_log.csv: all simulated fills with position/P&L state
  - pnl_summary.csv: periodic snapshots of strategy metrics
"""

import csv
import time
from datetime import datetime


def export_trades(market_maker, filename="trade_log.csv"):
    """Export all executed trades to CSV."""
    trades = market_maker.executed_trades
    if not trades:
        print("[EXPORT] No trades to export.")
        return

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "datetime", "side", "price", "size",
            "position_after"
        ])
        for t in trades:
            dt = datetime.fromtimestamp(t["timestamp"]).strftime(
                "%Y-%m-%d %H:%M:%S")
            writer.writerow([
                f"{t['timestamp']:.6f}",
                dt,
                t["side"],
                f"{t['price']:.2f}",
                f"{t['size']:.6f}",
                f"{t['position_after']:.6f}"
            ])
    print(f"[EXPORT] {len(trades)} trades exported to {filename}")


def export_spread_history(spread_analytics, filename="spread_history.csv"):
    """Export spread history for all tracked sizes to CSV."""
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["size_btc", "index", "spread_usd"])
        for size in spread_analytics.order_sizes:
            data = spread_analytics._history.get(size, [])
            for i, spread in enumerate(data):
                writer.writerow([
                    f"{size:.1f}",
                    i,
                    f"{spread:.4f}"
                ])
    print(f"[EXPORT] Spread history exported to {filename}")