import asyncio
import json
import websockets
import csv
import time
import hmac
import hashlib
from statistics import median
from datetime import datetime, timezone
from collections import deque
import threading
import argparse
import subprocess
import sys

# ----------------------- COMMON UTILITIES ------------------------------------
URI_PUBLIC = "wss://stream.bybit.com/v5/public/linear"
CHANNEL_DEFAULT = "orderbook.50.BTCUSDT"

# OFI calculation
def calc_ofi(prev_bids, prev_asks, bids, asks):
    ofi = 0.0
    for p, q in bids.items():
        ofi += q - prev_bids.get(p, 0.0)
    for p, q in asks.items():
        ofi -= q - prev_asks.get(p, 0.0)
    return ofi

# ----------------------- BYBIT HELLO (demo) ----------------------------------
async def run_hello():
    args = ["orderbook.1.BTCUSDT"]
    async with websockets.connect(URI_PUBLIC, ping_interval=20) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": args}))
        print("\u2713 Subscribed, waiting for data …")
        while True:
            msg = json.loads(await ws.recv())
            print(msg)

# ----------------------- OFI LIVE SCANNER -----------------------------------
last_bids = {}
last_asks = {}
ofi_window = []

# log to CSV
def log_to_csv(ts, raw_ofi, smoothed):
    with open("data.csv", "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([ts, raw_ofi, smoothed])

async def ofi_scanner(channel=CHANNEL_DEFAULT):
    global last_bids, last_asks, ofi_window
    try:
        async with websockets.connect(URI_PUBLIC, ping_interval=20) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": [channel]}))
            print(f"\u2705 Subscribed to {channel}")
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("type") != "delta" or msg.get("topic") != channel:
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
        print(f"Connection error: {e}. Reconnecting in 3s…")
        await asyncio.sleep(3)
        await ofi_scanner(channel)

# ----------------------- QT DASHBOARD ---------------------------------------
try:
    from PyQt5 import QtWidgets, QtCore
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
except Exception:
    QtWidgets = None

async def ws_loop_dashboard(channel, data_buffer):
    last_bids, last_asks = {}, {}
    async with websockets.connect(URI_PUBLIC, ping_interval=20) as ws:
        await ws.send(json.dumps({"op": "subscribe", "args": [channel]}))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("topic") != channel or msg.get("type") != "delta":
                continue
            bids = {float(p): float(q) for p, q in msg["data"]["b"]}
            asks = {float(p): float(q) for p, q in msg["data"]["a"]}
            if last_bids:
                ofi = calc_ofi(last_bids, last_asks, bids, asks)
                data_buffer.append((datetime.now(timezone.utc), ofi))
            last_bids, last_asks = bids, asks

def start_ws_thread(channel, data_buffer):
    asyncio.run(ws_loop_dashboard(channel, data_buffer))

class OFIDashboard(QtWidgets.QMainWindow):
    def __init__(self, channel):
        super().__init__()
        self.channel = channel
        self.setWindowTitle('Bybit Real-Time OFI Dashboard')
        self.fig = Figure(figsize=(8,4))
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        self.setCentralWidget(self.canvas)
        self.data_buffer = deque(maxlen=200)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(1000)
        self.ws_thread = threading.Thread(target=start_ws_thread, args=(self.channel, self.data_buffer), daemon=True)
        self.ws_thread.start()

    def update_plot(self):
        if not self.data_buffer:
            return
        times, ofi_vals = zip(*self.data_buffer)
        self.ax.clear()
        self.ax.plot(times, ofi_vals, marker='o')
        self.ax.set_title(f'OFI {self.channel}')
        self.ax.set_ylabel('OFI')
        self.fig.autofmt_xdate()
        self.canvas.draw()

# ----------------------- STREAMLIT DASHBOARD --------------------------------
# run streamlit dashboard in a subprocess to keep this file self-contained
STREAMLIT_FILE = "streamlit_dashboard.py"

def run_streamlit():
    subprocess.run([sys.executable, "-m", "streamlit", "run", STREAMLIT_FILE])

# ----------------------- MAIN CLI -------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Unified OFI Bybit application")
    parser.add_argument("mode", choices=["cli", "qt", "streamlit", "hello"], nargs='?', default="cli", help="Which interface to run")
    parser.add_argument("--channel", default=CHANNEL_DEFAULT, help="Bybit channel to subscribe")
    args = parser.parse_args()

    if args.mode == "hello":
        asyncio.run(run_hello())
    elif args.mode == "qt":
        if QtWidgets is None:
            print("PyQt5 not available")
            return
        app = QtWidgets.QApplication(sys.argv)
        win = OFIDashboard(args.channel)
        win.show()
        sys.exit(app.exec_())
    elif args.mode == "streamlit":
        run_streamlit()
    else:  # cli scanner
        asyncio.run(ofi_scanner(args.channel))

if __name__ == "__main__":
    main()
