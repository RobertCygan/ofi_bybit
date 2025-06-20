import asyncio
import json
import websockets
import threading
from collections import deque
from datetime import datetime, timezone

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd

# --- KONFIGURACJA STRONY ---
st.set_page_config(page_title="Bybit OFI Dashboard", layout="wide")

# --- INTERAKTYWNE KONTROLKI ---
symbol   = st.sidebar.text_input("Symbol", value="BTCUSDT")
depth    = st.sidebar.selectbox("Depth (poziomy)", options=[1,5,25,50,200,500], index=3)
buf      = st.sidebar.slider("Horyzont (ticks)", min_value=50, max_value=1000, value=200, step=50)
interval = st.sidebar.slider("Refresh (ms)",     min_value=200, max_value=5000, value=1000, step=200)

# --- PARAMETRY STREAMU ---
CHANNEL    = f"orderbook.{depth}.{symbol}"
MAX_POINTS = buf

# --- BUFOR DANYCH w session_state ---
if 'data_buffer' not in st.session_state:
    st.session_state.data_buffer = deque(maxlen=MAX_POINTS)
else:
    # jeżeli zmienił się buf, zachowaj ostatnie punkty, ale dostosuj maxlen
    old = st.session_state.data_buffer
    if old.maxlen != MAX_POINTS:
        st.session_state.data_buffer = deque(old, maxlen=MAX_POINTS)

data_buffer = st.session_state.data_buffer

# --- FUNKCJA OBLICZAJĄCA OFI ---
def calc_ofi(prev_bids, prev_asks, bids, asks):
    ofi = 0.0
    for p, q in bids.items():
        ofi += q - prev_bids.get(p, 0.0)
    for p, q in asks.items():
        ofi -= q - prev_asks.get(p, 0.0)
    return ofi

# --- WEBSOCKET LOOP ---
async def ws_loop():
    last_bids, last_asks = {}, {}
    uri = "wss://stream.bybit.com/v5/public/linear"
    try:
        async with websockets.connect(uri, ping_interval=20) as ws:
            await ws.send(json.dumps({"op": "subscribe", "args": [CHANNEL]}))
            while True:
                msg_txt = await ws.recv()
                msg = json.loads(msg_txt)
                if msg.get("topic") != CHANNEL or msg.get("type") != "delta":
                    continue
                bids = {float(p): float(q) for p, q in msg["data"]["b"]}
                asks = {float(p): float(q) for p, q in msg["data"]["a"]}
                if last_bids:
                    ofi = calc_ofi(last_bids, last_asks, bids, asks)
                    data_buffer.append((datetime.now(timezone.utc), ofi))
                last_bids, last_asks = bids, asks
    except Exception as e:
        st.error(f"WebSocket error: {e}")

# --- START WEBSOCKET W WĄTKU ---
def start_ws_thread():
    asyncio.run(ws_loop())

if 'ws_thread' not in st.session_state:
    thread = threading.Thread(target=start_ws_thread, daemon=True)
    thread.start()
    st.session_state.ws_thread = thread

# --- AUTOMATYCZNE ODŚWIEŻANIE ---
st_autorefresh(interval=interval, key=f"refresh_{symbol}_{depth}")

# --- WYKRES i TABELA ---
st.title(f"🛰️ Real-Time OFI for {symbol} (Depth {depth})")
if data_buffer:
    df = pd.DataFrame(list(data_buffer), columns=["timestamp","ofi"]).set_index("timestamp")
    st.line_chart(df["ofi"])
    st.dataframe(df.tail(10))
else:
    st.info("Ładowanie danych... Poczekaj kilka sekund, aż pojawią się pierwsze ticki.")
