![Python package](https://github.com/yahoofinancelive/yliveticker/workflows/Python%20package/badge.svg)
![Upload Python Package](https://github.com/yahoofinancelive/yliveticker/workflows/Upload%20Python%20Package/badge.svg)
# Live from Yahoo Finance

Get market data from Yahoo Finance websocket in near-real time.
wss://streamer.finance.yahoo.com/

## Setup
```bash
pip install yliveticker
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

**Note**
*Check trading hours for your market if you don't observe any live metrics*
