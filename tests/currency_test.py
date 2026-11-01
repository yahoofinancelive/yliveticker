import base64
from unittest import mock

from yliveticker import YLiveTicker
from yliveticker.yaticker_pb2 import yaticker


def test_callback_preserves_yahoo_currency():
    callback = mock.Mock()
    message = yaticker(
        id="7203.T",
        price=3000,
        time=1600000000000,
        currency="JPY",
        exchange="JPX",
    )

    with mock.patch("yliveticker.websocket"):
        client = YLiveTicker(on_ticker=callback, start=False)
        client.on_message(None, base64.b64encode(message.SerializeToString()).decode())

    assert callback.call_args.args[1]["currency"] == "JPY"
