# Live Market Data from Yahoo! Finance

[![Python package](https://github.com/yahoofinancelive/yliveticker/workflows/Python%20package/badge.svg)](https://github.com/yahoofinancelive/yliveticker/actions)
[![Upload Python Package](https://github.com/yahoofinancelive/yliveticker/workflows/Upload%20Python%20Package/badge.svg)](https://github.com/yahoofinancelive/yliveticker/actions)
[![PyPI version](https://badge.fury.io/py/yliveticker.svg)](https://pypi.org/project/yliveticker/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Get real-time market data from Yahoo! Finance via WebSockets. Lightweight, efficient, and easy to use.

## ✨ Features

- **Real-time updates**: Stream near-instant price changes from Yahoo! Finance.
- **Robust Connectivity**: Built-in automatic reconnection and keep-alive (heartbeats).
- **Modern Support**: Fully compatible with Protobuf 4.x/5.x/7.x.
- **Data Analysis Ready**: Optional pandas integration to generate Time Series and OHLCV candles.
- **Comprehensive Data**: Includes price, volume, change, day high/low, and more.

## 🚀 Setup

### Basic Installation
```bash
pip install yliveticker
```

### 🖥️ Full Experience (CLI & Data Analysis)
To get the interactive terminal UI and pandas support:
```bash
pip install yliveticker[cli,pandas]
```

## 📖 Usage Examples

### 1. Command Line Interface (CLI)
The easiest way to watch stocks. It provides a real-time, color-coded dashboard in your terminal.

```bash
# Watch multiple symbols
yliveticker watch AAPL MSFT TSLA BTC-USD
```

**How it looks:**
```text
Yahoo! Finance Live Ticker
┏━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Symbol  ┃    Price ┃ Day Change       ┃
┡━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ AAPL    │   234.12 │ +1.45 (0.62%)    │
│ BTC-USD │ 98450.00 │ -120.50 (-0.12%) │
└─────────┴━━━━━━━━━━┴━━━━━━━━━━━━━━━━━━┘
```

### 2. Basic Ticker (Blocking)
This is the simplest way to print live updates to the console.

```python
import yliveticker

# this function is called on each ticker update
def on_new_msg(ws, msg):
    print(msg)

yliveticker.YLiveTicker(on_ticker=on_new_msg, ticker_names=["BTC-USD", "AAPL", "EURUSD=X"])
```

### 2. Time Series and OHLCV (Pandas)
Use `YTimeSeries` to collect data into a structured format for analysis.

```python
import yliveticker
from yliveticker import YTimeSeries

ts = YTimeSeries()

# Collect data (press Ctrl+C to stop and see results)
try:
    yliveticker.YLiveTicker(on_ticker=ts.on_ticker, ticker_names=["BTC-USD"])
except KeyboardInterrupt:
    pass

# Get raw collected data as a pandas DataFrame
df = ts.get_dataframe()
print(df.head())

# Get 1-minute OHLCV candles
ohlcv = ts.get_ohlcv(interval='1Min')
for symbol, data in ohlcv.items():
    print(f"\n--- {symbol} ---")
    print(data)
```

### 3. Non-Blocking Usage (Threading)
If you want to keep the ticker running in the background while your main script continues.

```python
import yliveticker
import threading
import time

def start_ticker():
    yliveticker.YLiveTicker(ticker_names=["BTC-USD"])

# Start the ticker in a separate thread
t = threading.Thread(target=start_ticker, daemon=True)
t.start()

# Do other things in your main script
for i in range(5):
    print(f"Main thread is doing work... {i}")
    time.sleep(1)
```

## 🛠 Configuration

The `YLiveTicker` constructor accepts several parameters for fine-tuning:

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `on_ticker` | `None` | Callback function `f(ws, msg)` called on each update. |
| `ticker_names` | `["AMZN"]` | List of Yahoo Finance symbols to subscribe to. |
| `reconnect` | `5` | Delay in seconds before attempting to reconnect on failure. |
| `ping_interval` | `15` | Interval in seconds to send WebSocket pings. |
| `ping_timeout` | `10` | Timeout in seconds to wait for a pong response. |
| `enable_socket_trace` | `False` | Set to `True` to see raw WebSocket frames. |

## 📝 Note on Trading Hours
If you don't observe any live metrics, please check the **trading hours** for your specific market. Many traditional stock symbols will only provide updates during market hours. Crypto symbols (like `BTC-USD`) usually stream 24/7.

## ⚖️ License
Distributed under the MIT License. See `LICENSE` for more information.
