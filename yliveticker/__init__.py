import base64
import json
from .logger import writeline

import websocket

from .yaticker_pb2 import yaticker

try:
    import thread
except ImportError:
    import _thread as thread


class YLiveTicker:
    def __init__(
        self,
        on_ticker=None,
        ticker_names=["AMZN"],
        on_error=None,
        on_close=None,
        enable_socket_trace=False,
    ):

        self.symbol_list = dict()
        self.symbol_list["subscribe"] = ticker_names

        websocket.enableTrace(enable_socket_trace)

        self.on_ticker = on_ticker
        self.on_custom_close = on_close
        self.on_custom_error = on_error

        self.yaticker = yaticker()

        self.ticker_names = ticker_names
        self.ws = websocket.WebSocketApp(
            "wss://streamer.finance.yahoo.com/",
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )
        self.ws.on_open = self.on_open
        self.ws.run_forever()

    def on_message(self, ws, message):
        message_bytes = base64.b64decode(message)
        self.yaticker.ParseFromString(message_bytes)
        data = {
                "id": self.yaticker.id,
                "exchange": self.yaticker.exchange,
                "quoteType": self.yaticker.quoteType,
                "price": self.yaticker.price,
                "timestamp": self.yaticker.time,
                "marketHours": self.yaticker.marketHours,
                "changePercent": self.yaticker.changePercent,
                "dayVolume": self.yaticker.dayVolume,
                "change": self.yaticker.change,
                "priceHint": self.yaticker.priceHint
            }
        
        if self.on_ticker is None:
            print(json.dumps(data))
        else:
            self.on_ticker(ws, data)

    def on_error(self, ws, error):
        if self.on_custom_error is None:
            writeline(error)
        else:
            self.on_custom_error(error)

    def on_close(self, ws):
        if self.on_custom_close is None:
            writeline("### connection is closed ###")
        else:
            self.on_custom_close()

    def on_open(self, ws):
        def run(*args):
            self.ws.send(json.dumps(self.symbol_list))

        thread.start_new_thread(run, ())
        writeline("### connection is open ###")
