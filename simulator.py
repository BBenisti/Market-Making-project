"""
simulator.py - Main simulation loop.

Orchestrates the full market making simulation:
  1. Connects to Kraken WebSocket feed
  2. Maintains the Level 2 order book and trade feed
  3. Runs the market maker strategy (quote, fill, risk check)
  4. Displays a live dashboard with book, trades, quotes, and P&L

Usage: python simulator.py
Press Ctrl+C to stop.
"""

import websocket
import json
import time
import threading
import os
from datetime import datetime

from config import (
    WS_URL, PRODUCT_ID, ORDER_BOOK_DEPTH, ORDER_SIZES,
    DISPLAY_REFRESH_INTERVAL, INITIAL_CAPITAL, SPREAD_REFERENCE_SIZE
)
from orderbook import OrderBook
from trades import TradeFeed
from spread_analytics import SpreadAnalytics
from market_maker import MarketMaker


# Global components
book = OrderBook(max_depth=ORDER_BOOK_DEPTH)
feed = TradeFeed()
spreads = SpreadAnalytics(ORDER_SIZES)
mm = MarketMaker()


def on_message(ws, message):
    """Route Kraken messages to the appropriate handler."""
    data = json.loads(message)

    # System/subscription events (dicts)
    if isinstance(data, dict):
        event = data.get("event", "")
        if event == "systemStatus":
            print(f"[INFO] Kraken status: {data.get('status')}")
        elif event == "subscriptionStatus":
            print(f"[INFO] Subscribed: {data.get('channelName')} - {data.get('pair')}")
        return

    # Channel data (lists)
    if not isinstance(data, list) or len(data) < 4:
        return

    channel = data[-2]

    if channel.startswith("book"):
        book_data = data[1]
        if "as" in book_data and "bs" in book_data:
            book.handle_snapshot(asks=book_data["as"], bids=book_data["bs"])
            print(f"[INFO] Book snapshot received")
        else:
            book.handle_update(book_data)
            if len(data) == 5:
                book.handle_update(data[2])

        # Refresh quotes on every book update
        if book.is_initialized:
            spread_data = spreads.compute_spreads(book)
            mm.update_market_spread(spread_data, SPREAD_REFERENCE_SIZE)
            mm.update_quotes(book)

    elif channel == "trade":
        feed.handle_trade(data[1])
        mm.check_fills(feed)
        


def on_error(ws, error):
    print(f"[ERROR] {error}")


def on_close(ws, close_status, close_msg):
    print(f"[INFO] Connection closed")


def on_open(ws):
    """Subscribe to book and trade channels."""
    ws.send(json.dumps({
        "event": "subscribe",
        "pair": [PRODUCT_ID],
        "subscription": {"name": "book", "depth": ORDER_BOOK_DEPTH}
    }))
    ws.send(json.dumps({
        "event": "subscribe",
        "pair": [PRODUCT_ID],
        "subscription": {"name": "trade"}
    }))
    print(f"[INFO] Subscribing to {PRODUCT_ID} book + trades")


def format_pnl(value):
    """Format P&L with color-like prefix."""
    if value > 0:
        return f"+${value:>12,.2f}"
    elif value < 0:
        return f"-${abs(value):>12,.2f}"
    return f" ${value:>12,.2f}"


def display_dashboard():
    """Render the full trading dashboard to the terminal."""
    if not book.is_initialized:
        return

    mid = book.get_mid_price()
    if mid is None:
        return

    bids, asks = book.get_top_levels(5)
    recent_trades = feed.get_recent(5)
    spread_data = spreads.compute_spreads(book)
    status = mm.get_status(mid)

    # Clear screen for live refresh
    os.system("cls" if os.name == "nt" else "clear")

    # --- Header ---
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{'=' * 72}")
    print(f"  MAREX CRYPTO MM SIMULATOR  |  {PRODUCT_ID}  |  {ts}")
    print(f"{'=' * 72}")

    # --- Market state ---
    print(f"\n  MARKET")
    print(f"  Mid Price:    ${mid:>12,.2f}")
    if status["vol"] is not None:
        print(f"  Realized Vol: ${status['vol']:>12,.2f}  (rolling)")
    else:
        print(f"  Realized Vol:     warming up...")

    # --- Top of book ---
    print(f"\n  TOP OF BOOK")
    print(f"  {'ASK':>12} {'SIZE':>14}")
    for p, s in reversed(asks):
        print(f"  ${p:>11,.2f} {s:>14.6f}")
    print(f"  {'---':>12} {'---':>14}")
    for p, s in bids:
        print(f"  ${p:>11,.2f} {s:>14.6f}")
    print(f"  {'BID':>12} {'SIZE':>14}")

    # --- Our quotes ---
    print(f"\n  OUR QUOTES")
    if status["is_halted"]:
        print(f"  [HALTED - risk limit breached]")
    else:
        bid_str = f"${status['bid']:,.2f}" if status['bid'] else "---"
        ask_str = f"${status['ask']:,.2f}" if status['ask'] else "---"
        hs_str = f"${status['half_spread']:,.2f}" if status['half_spread'] else "---"
        print(f"  Bid: {bid_str:>12}    Ask: {ask_str:>12}    Half-Spread: {hs_str}")
        print(f"  Quote Size: {status['quote_size']:.4f} BTC")

    # --- Effective market spreads ---
    print(f"\n  EFFECTIVE MARKET SPREADS (by size)")
    print(f"  {'Size':>6} {'Spread':>10} {'Avg':>10} {'Median':>10} {'Min':>10} {'Max':>10}")
    for size in ORDER_SIZES:
        s = spread_data.get(size)
        stats = spreads.get_statistics(size)
        if s and stats:
            print(f"  {size:>5.1f}  ${s['spread']:>9.2f} "
                  f"${stats['avg']:>9.2f} ${stats['median']:>9.2f} "
                  f"${stats['min']:>9.2f} ${stats['max']:>9.2f}")

    # --- Strategy state ---
    print(f"\n  STRATEGY")
    print(f"  Position:        {status['position_btc']:>14.6f} BTC")
    if status['position_btc'] != 0:
        print(f"  Avg Entry:      ${status['avg_entry']:>12,.2f}")
    print(f"  Exposure:       ${status['exposure_usd']:>12,.2f}  USD")
    print(f"  Realized P&L:    {format_pnl(status['realized_pnl'])}")
    print(f"  Unrealized P&L:  {format_pnl(status['unrealized_pnl'])}")
    print(f"  Total P&L:       {format_pnl(status['total_pnl'])}")
    print(f"  Fills:           {status['trade_count']:>14}")

    # --- Recent market trades ---
    print(f"\n  RECENT MARKET TRADES")
    for t in recent_trades:
        t_ts = datetime.fromtimestamp(t["timestamp"]).strftime("%H:%M:%S")
        side = t["side"].upper()
        print(f"    {t_ts}  {side:>4}  ${t['price']:>10,.2f}  x {t['volume']:.6f}")

    # --- Our recent fills ---
    if mm.executed_trades:
        print(f"\n  OUR RECENT FILLS")
        for t in mm.executed_trades[-5:][::-1]:
            t_ts = datetime.fromtimestamp(t["timestamp"]).strftime("%H:%M:%S")
            side = t["side"].upper()
            print(f"    {t_ts}  {side:>4}  ${t['price']:>10,.2f}  x {t['size']:.6f}")

    print()


def display_loop():
    """Background thread that refreshes the dashboard at fixed interval."""
    while True:
        try:
            display_dashboard()
        except Exception as e:
            print(f"[DISPLAY ERROR] {e}")
        time.sleep(DISPLAY_REFRESH_INTERVAL)


def run():
    """Start the dashboard thread and the WebSocket loop with auto-reconnect."""
    print(f"[INFO] Starting Marex Crypto MM Simulator")
    print(f"[INFO] Initial capital: ${INITIAL_CAPITAL:,}")

    display_thread = threading.Thread(target=display_loop, daemon=True)
    display_thread.start()

    try:
        while True:
            ws = websocket.WebSocketApp(
                WS_URL,
                on_message=on_message,
                on_open=on_open,
                on_error=on_error,
                on_close=on_close
            )
            try:
                ws.run_forever(
                    skip_utf8_validation=True,
                    ping_interval=20,
                    ping_timeout=10
                )
            except Exception as e:
                print(f"[ERROR] {e}")

            print(f"[INFO] Connection lost - reconnecting in 3 seconds...")
            book.is_initialized = False
            time.sleep(3)

    except KeyboardInterrupt:
        pass

    # Export always runs after Ctrl+C
    from export import export_trades, export_spread_history
    from plots import plot_spread_history, plot_pnl

    print("\n[INFO] Shutting down - exporting data...")
    export_trades(mm)
    export_spread_history(spreads)
    plot_spread_history(spreads)
    plot_pnl(mm)
    print("[INFO] Done.")


if __name__ == "__main__":
    run()