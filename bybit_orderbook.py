

"""
pip install websockets==12.0
python bybit_orderbook.py
"""
import asyncio, json, time, hmac, hashlib, websockets
from collections import defaultdict

# ---------- 1. KONFIG --------------------------------------------------------
PUBLIC_WS  = "wss://stream.bybit.com/v5/public/linear"   # testnet: .../stream-testnet...
PRIVATE_WS = "wss://stream.bybit.com/v5/private"

SYMBOL      = "BTCUSDT"
DEPTH_LEVEL = 50            # orderbook.50 / 200 / 1000
CHANNEL     = f"orderbook.{DEPTH_LEVEL}.{SYMBOL}"

API_KEY    = "YOUR_API_KEY"       # tylko jeśli chcesz dane prywatne
API_SECRET = "YOUR_API_SECRET"

# ---------- 2. OFI -----------------------------------------------------------
def ofi_delta(prev_bids, prev_asks, bids, asks):
    """ΔBidQty - ΔAskQty  (>0 popyt, <0 podaż)."""
    ofi = 0.0
    for p, q in bids.items():
        ofi += q - prev_bids.get(p, 0.0)
    for p, q in asks.items():
        ofi -= q - prev_asks.get(p, 0.0)
    return ofi

# ---------- 3. PUBLIC STREAM -------------------------------------------------
async def run_public():
    last_bids, last_asks = {}, {}
    async with websockets.connect(PUBLIC_WS, ping_interval=20) as ws:
        # subskrypcja orderbooku 50-poziomowego
        await ws.send(json.dumps({"op": "subscribe", "args": [CHANNEL]}))

        while True:
            msg = json.loads(await ws.recv())
            # Bybit wysyła snapshot + delta; interesują nas tylko update’y
            if msg.get("topic") != CHANNEL or msg.get("type") != "delta":
                continue

            bids = {float(p): float(q) for p, q in msg["data"]["b"]}
            asks = {float(p): float(q) for p, q in msg["data"]["a"]}

            if last_bids:        # pomiń pierwszy tick (brak bazowego porównania)
                print(f"ΔOFI = {ofi_delta(last_bids, last_asks, bids, asks):+.2f}")

            last_bids, last_asks = bids, asks

# ---------- 4. PRIVATE STREAM (autoryzacja) ----------------------------------
async def run_private():
    ts   = int(time.time() * 1000)
    sign = hmac.new(API_SECRET.encode(),
                    f"GET/realtime{ts}".encode(),
                    digestmod=hashlib.sha256).hexdigest()

    async with websockets.connect(PRIVATE_WS, ping_interval=20) as ws:
        # AUTH (trzy argumenty: api_key, expires, signature)
        await ws.send(json.dumps({"op": "auth", "args": [API_KEY, ts, sign]}))
        auth_resp = json.loads(await ws.recv())
        if auth_resp.get("success") is not True:
            raise RuntimeError(f"Auth failed: {auth_resp}")

        # przykład: subskrybcja własnych zleceń
        await ws.send(json.dumps({"op": "subscribe", "args": [f"order.{SYMBOL}"]}))
        while True:
            print(await ws.recv())

# ---------- 5. MAIN ----------------------------------------------------------
if __name__ == "__main__":
    try:
        asyncio.run(run_public())          # ← usuń tę linię i odkomentuj niżej,
        # asyncio.run(run_private())       # jeżeli chcesz testować kanały prywatne
    except KeyboardInterrupt:
        pass
