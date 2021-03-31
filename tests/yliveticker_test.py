import json
from unittest import mock

from yliveticker import YLiveTicker


def test_on_message():
    with mock.patch("yliveticker.websocket"):
        def on_msg(ws, msg):
            assert {
                "id": "MSFT",
                "exchange": "NMS",
                "quoteType": 8,
                "price": 177.4199981689453,
                "timestamp": 1589554809000,
                "marketHours": 1,
                "changePercent": -1.7227057218551636,
                "dayVolume": 10460764,
                "change": -3.1100006103515625,
                "priceHint": 2,
            } == msg

        yticker = YLiveTicker(on_ticker=on_msg)
        yticker.on_message(None,
            "CgRNU0ZUFYVrMUMY0KLMjcNcKgNOTVMwCDgBRZ\
                +B3L9IuPn8CVU0IjRDXYVrMUNlQApHwNgBBA=="
        )
