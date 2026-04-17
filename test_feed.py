"""
test_feed.py - Combined book + trades + spread analytics validation.

Usage: python test_feed.py
"""

import websocket
import json
from datetime import datetime
from config import WS_URL, PRODUCT_ID, ORDER_BOOK_DEPTH, ORDER_SIZES
from orderbook import OrderBook
from trades import TradeFeed
from spread_analytics import SpreadAnalytics

book = OrderBook()
feed = TradeFeed()
spreads = SpreadAnalytics(ORDER_SIZES)
msg_count = 0


def on_message(ws, message):
    global msg_count
    data = json.loads(message)

    if isinstance(data, dict):
        event = data.get("event", "")
        if event == "systemStatus":
            print(f"[INFO] Kraken status: {data.get('status')}")
        elif event == "subscriptionStatus":
            print(f"[INFO] Subscribed: {data.get('channelName')} - {data.get('pair')}")
        return

    if not isinstance(data, list) or len(data) < 4:
        return

    channel = data[-2]

    if channel.startswith("book"):
        book_data = data[1]
        if "as" in book_data and "bs" in book_data:
            book.handle_snapshot(asks=book_data["as"], bids=book_data["bs"])
            print(f"[INFO] Book snapshot - {len(book.bids)} bids, {len(book.asks)} asks")
        else:
            book.handle_update(book_data)
            if len(data) == 5:
                book.handle_update(data[2])
    elif channel == "trade":
        feed.handle_trade(data[1])

    msg_count += 1
    if msg_count % 100 == 0 and book.is_initialized:
        display_dashboard()


def display_dashboard():
    """Print book, recent trades, and spread analytics."""
    bids, asks = book.get_top_levels(10)
    mid = book.get_mid_price()
    recent = feed.get_recent(5)
    spread_data = spreads.compute_spreads(book)

    # -- Order Book --
    print(f"\n{'=' * 60}")
    print(f"  Mid Price: ${mid:,.2f}")
    print(f"{'=' * 60}")
    print(f"  {'ASK':>10} {'SIZE':>12}")
    for p, s in reversed(asks):
        print(f"  ${p:>10,.2f} {s:>12.6f}")
    print(f"  {'---':>10} {'---':>12}")
    for p, s in bids:
        print(f"  ${p:>10,.2f} {s:>12.6f}")
    print(f"  {'BID':>10} {'SIZE':>12}")

    # -- Recent Trades --
    print(f"\n  Recent Trades:")
    for t in recent:
        ts = datetime.fromtimestamp(t["timestamp"]).strftime("%H:%M:%S")
        side = t["side"].upper()
        print(f"    {ts}  {side:>4}  ${t['price']:>10,.2f}  x {t['volume']:.6f}")

    # -- Spread Analytics --
    print(f"\n  Effective Spreads:")
    print(f"  {'Size':>6} {'Spread':>10} {'Avg':>10} {'Median':>10} {'Min':>10} {'Max':>10}")
    for size in ORDER_SIZES:
        s = spread_data.get(size)
        stats = spreads.get_statistics(size)
        if s and stats:
            print(f"  {size:>5.1f}  ${s['spread']:>9.2f} "
                  f"${stats['avg']:>9.2f} ${stats['median']:>9.2f} "
                  f"${stats['min']:>9.2f} ${stats['max']:>9.2f}")
        elif s:
            print(f"  {size:>5.1f}  ${s['spread']:>9.2f}    (collecting data...)")
        else:
            print(f"  {size:>5.1f}   insufficient liquidity")
    print()


def on_error(ws, error):
    print(f"[ERROR] {error}")


def on_close(ws, close_status, close_msg):
    print(f"[INFO] Connection closed: {close_status} - {close_msg}")


def on_open(ws):
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
    print(f"[INFO] Subscribing to {PRODUCT_ID} book (depth={ORDER_BOOK_DEPTH}) + trades")


if __name__ == "__main__":
    ws = websocket.WebSocketApp(
        WS_URL,
        on_message=on_message,
        on_open=on_open,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever(
        skip_utf8_validation=True,
        ping_interval=30,
        ping_timeout=10
    )