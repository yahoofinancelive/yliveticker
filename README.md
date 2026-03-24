![Python package](https://github.com/yahoofinancelive/yliveticker/workflows/Python%20package/badge.svg)
![Upload Python Package](https://github.com/yahoofinancelive/yliveticker/workflows/Upload%20Python%20Package/badge.svg)
# Live from Yahoo Finance

Get market data from Yahoo Finance websocket in near-real time.
wss://streamer.finance.yahoo.com/

## Setup
```bash
pip install yliveticker
```

For pandas support (to generate time series and OHLCV data):
```bash
pip install yliveticker[pandas]
```

[pypi package home](https://pypi.org/project/yliveticker/)

## Example

The following snippet prints out live metrics in console output. You can follow other symbols by providing them in `ticker_names`.

```python
import yliveticker


# this function is called on each ticker update
def on_new_msg(ws, msg):
    print(msg)


yliveticker.YLiveTicker(on_ticker=on_new_msg, ticker_names=[
    "BTC=X", "^GSPC", "^DJI", "^IXIC", "^RUT", "CL=F", "GC=F", "SI=F", "EURUSD=X", "^TNX", "^VIX", "GBPUSD=X", "JPY=X", "BTC-USD", "^CMC200", "^FTSE", "^N225"])
```

### Time Series and OHLCV (Pandas)

You can use `YTimeSeries` to collect data and convert it to a pandas DataFrame or resampled OHLCV candles.

```python
import yliveticker
from yliveticker import YTimeSeries
import time

ts = YTimeSeries()

# Run for 30 seconds to collect some data
# Note: YLiveTicker is blocking by default. 
# You might want to run it in a separate thread for interactive use.
try:
    yliveticker.YLiveTicker(on_ticker=ts.on_ticker, ticker_names=["BTC-USD"])
except KeyboardInterrupt:
    pass

# Get raw collected data as a DataFrame
df = ts.get_dataframe()
print(df.head())

# Get 1-minute OHLCV candles
ohlcv = ts.get_ohlcv(interval='1Min')
for symbol, data in ohlcv.items():
    print(f"\n--- {symbol} ---")
    print(data)
```

**Note**
*Check trading hours for your market if you don't observe any live metrics*
