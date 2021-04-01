from yliveticker import YLiveTicker


def printRes(ws, res):
    print(res)


def on_close(ws):
    print("bye")


# Connect to Yahoo! Finance and output live data
YLiveTicker(
    on_ticker=printRes,
    on_close=on_close,
    ticker_names=[
        "BTC=X",
        "^GSPC",
        "^DJI",
        "^IXIC",
        "^RUT",
        "CL=F",
        "GC=F",
        "SI=F",
        "EURUSD=X",
        "^TNX",
        "^VIX",
        "GBPUSD=X",
        "JPY=X",
        "BTC-USD",
        "^CMC200",
        "^FTSE",
        "^N225",
    ],
)
