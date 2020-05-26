# Live from Yahoo Finance:

Get market data from Yahoo Finance websocket in near-real time.
wss://streamer.finance.yahoo.com/

Example:
```python
import yliveticker


def on_new_msg(msg):
    print(msg)


yliveticker.YLiveTicker(on_ticker=on_new_msg, ticker_names=[
    "BTC=X", "^GSPC", "^DJI", "^IXIC", "^RUT", "CL=F", "GC=F", "SI=F", "EURUSD=X", "^TNX", "^VIX", "GBPUSD=X", "JPY=X", "BTC-USD", "^CMC200", "^FTSE", "^N225"])
```
