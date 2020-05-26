import yliveticker


def printRes(res):
    print(res)


def on_close():
    print("bye")


print("Test output:", yliveticker.yliveticker.test())

yliveticker.yliveticker(on_ticker=printRes,
                                  on_close=on_close,
                                  ticker_names=[
                                      "BTC=X", "^GSPC", "^DJI", "^IXIC", "^RUT", "CL=F", "GC=F", "SI=F", "EURUSD=X", "^TNX", "^VIX", "GBPUSD=X", "JPY=X", "BTC-USD", "^CMC200", "^FTSE", "^N225"])
