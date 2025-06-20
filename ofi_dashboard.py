import sys, asyncio, json, websockets, threading
from collections import deque
from datetime import datetime, timezone

from PyQt5 import QtWidgets, QtCore
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# --- KONFIGURACJA APLIKACJI ---
URI = "wss://stream.bybit.com/v5/public/linear"
CHANNEL = "orderbook.50.BTCUSDT"  # możesz zmienić symbol / depth
MAX_POINTS = 200                  # ile ticków trzymać w buforze
REFRESH_MS = 1000                 # odświeżanie wykresu w ms

# globalny bufor danych
data_buffer = deque(maxlen=MAX_POINTS)

# obliczanie OFI
def calc_ofi(prev_bids, prev_asks, bids, asks):
    ofi = 0.0
    for p, q in bids.items(): ofi += q - prev_bids.get(p, 0.0)
    for p, q in asks.items(): ofi -= q - prev_asks.get(p, 0.0)
    return ofi

# websocket loop
async def ws_loop():
    last_bids, last_asks = {}, {}
    try:
        async with websockets.connect(URI, ping_interval=20) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": [CHANNEL]}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("topic") != CHANNEL or msg.get("type") != "delta": continue
                bids = {float(p): float(q) for p, q in msg["data"]["b"]}
                asks = {float(p): float(q) for p, q in msg["data"]["a"]}
                if last_bids:
                    ofi = calc_ofi(last_bids, last_asks, bids, asks)
                    data_buffer.append((datetime.now(timezone.utc), ofi))
                last_bids, last_asks = bids, asks
    except Exception as e:
        print("WebSocket error:", e)

# wątek uruchamiający asyncio ws_loop
def start_ws_thread():
    asyncio.run(ws_loop())

# Qt Widget z wykresem
class OFIDashboard(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Bybit Real-Time OFI Dashboard')
        # matplotlib Figure
        self.fig = Figure(figsize=(8,4))
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvas(self.fig)
        self.setCentralWidget(self.canvas)
        # Timer odświeżania
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(REFRESH_MS)

    def update_plot(self):
        if not data_buffer: return
        times, ofi_vals = zip(*data_buffer)
        self.ax.clear()
        self.ax.plot(times, ofi_vals, marker='o')
        self.ax.set_title(f'OFI {CHANNEL}')
        self.ax.set_ylabel('OFI')
        self.fig.autofmt_xdate()
        self.canvas.draw()

# uruchomienie aplikacji
if __name__ == '__main__':
    # start ws thread
    ws_thread = threading.Thread(target=start_ws_thread, daemon=True)
    ws_thread.start()
    # Qt app
    app = QtWidgets.QApplication(sys.argv)
    window = OFIDashboard()
    window.show()
    sys.exit(app.exec_())
