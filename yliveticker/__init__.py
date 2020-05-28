from .yaticker_pb2 import yaticker
import sys
import base64
import websocket
try:
    import thread
except ImportError:
    import _thread as thread
import time
import json
import asyncio
import random


class YLiveTicker:

    def __init__(self,
                 on_ticker=None,
                 ticker_names=['MSFT'],
                 on_error=None,
                 on_close=None,
                 enable_socket_trace=False):

        self.symbol_list = dict()
        self.symbol_list["subscribe"] = ticker_names
        
        websocket.enableTrace(enable_socket_trace)

        self.on_ticker = on_ticker
        self.on_custom_close = on_close
        self.on_custom_error = on_error

        self.yaticker = yaticker()

        self.ticker_names = ticker_names


        self.ws = websocket.WebSocketApp("wss://streamer.finance.yahoo.com/",
                                         on_message=self.on_message,
                                         on_error=self.on_error,
                                         on_close=self.on_close)
        self.ws.on_open = self.on_open
        self.ws.run_forever()

    @staticmethod
    def test():
        messages = ["CgRNU0ZUFT1KMUMY8MzyjcNcKgNOTVMwCDgBRVe55b9InLTBCmVAXE/A2AEE",
                    "CgRNU0ZUFYVrMUMY0KLMjcNcKgNOTVMwCDgBRZ+B3L9IuPn8CVU0IjRDXYVrMUNlQApHwNgBBA==",
                    "CgRNU0ZUFR9FMUMYgJ7yjcNcKgNOTVMwCDgBRSkk579I2IjBCmXAo1DA2AEE",
                    "CgRNU0ZUFT1KMUMY8MzyjcNcKgNOTVMwCDgBRVe55b9IhrLBCmVAXE/A2AEE"]

        message_bytes = base64.b64decode(random.choice(messages))
        yaticker = yaticker()
        yaticker.ParseFromString(message_bytes)
        return json.dumps({
            "id": yaticker.id,
            "exchange": yaticker.exchange,
            "quoteType": yaticker.quoteType,
            "price": yaticker.price,
            "timestamp": yaticker.time,
            "marketHours": yaticker.marketHours,
            "changePercent": yaticker.changePercent,
            "dayVolume": yaticker.dayVolume,
            "change": yaticker.change,
            "priceHint": yaticker.priceHint
        })

    def on_message(self, message):
        message_bytes = base64.b64decode(message)
        self.yaticker.ParseFromString(message_bytes)
        data = json.dumps({
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
        })
        if self.on_ticker is None:
            print(data)
        else:
            self.on_ticker(data)

    def on_error(self, error):
        if self.on_custom_error is None:
            print(error)
        else:
            self.on_custom_error(error)

    def on_close(self):
        if self.on_custom_close is None:
            print("### connection is closed ###")
        else:
            self.on_custom_close()

    def on_open(self):
        def run(*args):
            self.ws.send(json.dumps(self.symbol_list))
        thread.start_new_thread(run, ())
        print("### connection is open ###")
