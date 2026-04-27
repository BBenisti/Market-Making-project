"""
export.py - Export trade logs and spread history to CSV.
"""

import csv
from datetime import datetime


def export_trades(market_maker, filename="trade_log.csv"):
    """Export all executed trades with cumulative realized P&L."""
    trades = market_maker.executed_trades
    if not trades:
        print("[EXPORT] No trades to export.")
        return

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "datetime", "side", "price", "size",
            "position_after", "realized_pnl_cumul"
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
                f"{t['position_after']:.6f}",
                f"{t.get('realized_pnl_cumul', 0.0):.2f}"
            ])
    print(f"[EXPORT] {len(trades)} trades exported to {filename}")


def export_spread_history(spread_analytics, filename="spread_history.csv"):
    """Export spread history for all tracked sizes."""
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