import asyncio, json, websockets, csv
from statistics import median
from datetime import datetime

URI = "wss://stream.bybit.com/v5/public/linear"
CHANNEL = "orderbook.50.BTCUSDT"

last_bids = {}
last_asks = {}
ofi_window = []

# Zapisz do pliku CSV
def log_to_csv(ts, raw_ofi, smoothed):
    with open("data.csv", mode="a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([ts, raw_ofi, smoothed])

# Oblicz OFI = ΔBID - ΔASK
def calc_ofi(prev_bids, prev_asks, bids, asks):
    ofi = 0.0
    for p, q in bids.items():
        ofi += q - prev_bids.get(p, 0.0)
    for p, q in asks.items():
        ofi -= q - prev_asks.get(p, 0.0)
    return ofi

# Główna pętla: łączy się z Bybit i liczy OFI
async def bybit_ofi_loop():
    global last_bids, last_asks, ofi_window
    try:
        async with websockets.connect(URI, ping_interval=20) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": [CHANNEL]}))
            print("✅ Subscribed to Bybit orderbook.50.BTCUSDT")
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("type") != "delta" or msg.get("topic") != CHANNEL:
                    continue
                bids = {float(p): float(q) for p, q in msg["data"]["b"]}
                asks = {float(p): float(q) for p, q in msg["data"]["a"]}

                if last_bids:
                    raw_ofi = calc_ofi(last_bids, last_asks, bids, asks)
                    ofi_window.append(raw_ofi)
                    if len(ofi_window) > 3:
                        ofi_window.pop(0)
                    smoothed = median(ofi_window)
                    ts = datetime.utcnow().strftime("%H:%M:%S")
                    print(f"{ts} | OFI: {raw_ofi:+.4f} | median(3): {smoothed:+.4f}")
                    log_to_csv(ts, raw_ofi, smoothed)

                last_bids, last_asks = bids, asks

    except Exception as e:
        print(f"🔌 Connection error: {e}. Reconnecting in 3s…")
        await asyncio.sleep(3)
        await bybit_ofi_loop()

# Uruchom event-loop
if __name__ == "__main__":
    asyncio.run(bybit_ofi_loop())
