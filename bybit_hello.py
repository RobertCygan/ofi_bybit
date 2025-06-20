import asyncio, json, websockets

URI  = "wss://stream.bybit.com/v5/public/linear"
ARGS = ["orderbook.1.BTCUSDT"]          # 1 poziom, ~100 ms cadence

async def main():
    async with websockets.connect(URI, ping_interval=20) as ws:
        # 1. Wyślij prośbę o subskrypcję
        await ws.send(json.dumps({"op": "subscribe", "args": ARGS}))
        print("✓ Subscribed, czekam na dane …")

        # 2. Pętla odbierająca kolejne komunikaty
        while True:
            raw = await ws.recv()       # <- czeka aż coś przyjdzie
            msg = json.loads(raw)
            print(msg)                  # na razie wypisujemy „jak leci”

# Uruchom „event-loop” asyncio
if __name__ == "__main__":
    asyncio.run(main())
