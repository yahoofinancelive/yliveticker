import base64
import json
import threading
import time

import pytest

from yliveticker import YLiveTicker
from yliveticker.cli import Dashboard
from yliveticker.yaticker_pb2 import yaticker


def tick(symbol):
    message = yaticker(id=symbol, price=123, time=123456)
    return base64.b64encode(message.SerializeToString()).decode()


class Socket:

    def __init__(self, url, **callbacks):
        self.callbacks = callbacks
        self.sent = []
        self.runs = 0
        self.closes = 0
        self.stopped = threading.Event()
        self.behavior = None

    def send(self, payload):
        self.sent.append(json.loads(payload)["subscribe"])

    def close(self, **kwargs):
        self.closes += 1
        self.stopped.set()

    def run_forever(self, **kwargs):
        assert kwargs["reconnect"] == 0
        self.runs += 1
        self.callbacks["on_open"](self)
        if self.behavior:
            self.behavior(self)
        self.callbacks["on_close"](self, 1000, "closed")

    def emit(self, symbol):
        self.callbacks["on_message"](self, tick(symbol))


@pytest.fixture(autouse=True)
def sockets(monkeypatch):
    monkeypatch.setattr("yliveticker.websocket.WebSocketApp", Socket)


def client(**kwargs):
    return YLiveTicker(start=False, reconnect=0, **kwargs)


@pytest.mark.parametrize("count,sizes", [(1, [1]), (100, [100]), (101, [100, 1]),
                                         (280, [100, 100, 80]), (400, [100] * 4)])
def test_bucket_boundaries(count, sizes):
    symbols = ["T{}".format(i) for i in range(count)]
    received = []
    caller = threading.get_ident()
    pool = client(ticker_names=symbols, on_ticker=lambda ws, t: received.append(
        (ws, t["id"], threading.get_ident())))
    for ws in pool.connections:
        ws.behavior = lambda socket: [socket.emit(s) for s in socket.sent[-1]]
    pool.run()
    assert [len(ws.sent[0]) for ws in pool.connections] == sizes
    assert [s for ws in pool.connections for s in ws.sent[0]] == symbols
    assert sorted(t[1] for t in received) == sorted(symbols)
    assert all(t[0] in pool.connections and t[2] == caller for t in received)
    assert all(ws.closes == 1 for ws in pool.connections)
    assert all(not worker.is_alive() for worker in pool._workers)


def test_deduplicates_without_mutating_input():
    symbols = [" BTC-USD ", "ETH-USD", "BTC-USD"]
    pool = client(ticker_names=symbols, symbols_per_connection=1)
    assert pool.connection_symbols == (("BTC-USD",), ("ETH-USD",))
    assert symbols == [" BTC-USD ", "ETH-USD", "BTC-USD"]
    assert pool.ws is pool.connections[0]
    assert client(ticker_names="BTC-USD").ticker_names == ["BTC-USD"]


@pytest.mark.parametrize("kwargs", [
    {"ticker_names": []}, {"ticker_names": [""]}, {"ticker_names": [None]},
    {"symbols_per_connection": 101}, {"symbols_per_connection": 0},
    {"symbols_per_connection": True}, {"max_connections": 0}, {"queue_size": 0},
    {"queue_size": 1.5}, {"reconnect": -1}, {"reconnect": float("nan")},
    {"ping_interval": -1}, {"ping_timeout": 0}, {"ping_interval": 10},
])
def test_invalid_configuration_opens_no_sockets(monkeypatch, kwargs):

    def unexpected(*args, **values):
        pytest.fail("must validate before creating sockets")
    monkeypatch.setattr("yliveticker.websocket.WebSocketApp", unexpected)
    with pytest.raises(ValueError):
        YLiveTicker(start=False, **kwargs)


def test_capacity_is_explicit_and_configurable():
    symbols = ["T{}".format(i) for i in range(401)]
    with pytest.raises(ValueError, match="increase max_connections"):
        client(ticker_names=symbols)
    assert len(client(ticker_names=symbols, max_connections=5).connections) == 5


def test_default_constructor_blocks_until_callbacks_finish():
    received = []
    original = Socket.run_forever

    def run(self, **kwargs):
        self.behavior = lambda socket: socket.emit("AMZN")
        original(self, **kwargs)
    from unittest.mock import patch
    with patch.object(Socket, "run_forever", run):
        pool = YLiveTicker(reconnect=0, on_ticker=lambda ws, t: received.append(t))
    assert received[0]["id"] == "AMZN"
    assert pool.connections[0].closes == 1


@pytest.mark.parametrize("failure", ["clean_close", "exception"])
def test_reconnect_only_failed_bucket_and_resubscribe(failure):
    pool = YLiveTicker(ticker_names=["BTC-USD", "ETH-USD"],
                       symbols_per_connection=1, start=False, reconnect=0.01)
    first, second = pool.connections
    second_open = threading.Event()

    def flaky(socket):
        assert second_open.wait(2)
        if socket.runs == 1:
            if failure == "exception":
                raise RuntimeError("connection lost")
            return  # A clean server close must reconnect too.
        socket.emit("BTC-USD")
        socket.stopped.wait(2)

    def healthy(socket):
        second_open.set()
        socket.stopped.wait(2)
    first.behavior, second.behavior = flaky, healthy
    pool.on_ticker = lambda ws, t: pool.close()
    pool.run()
    assert first.sent == [["BTC-USD"], ["BTC-USD"]]
    assert second.sent == [["ETH-USD"]]
    assert [s["reconnect_count"] for s in pool.diagnostics["connections"]] == [1, 0]


def test_callbacks_errors_and_closes_are_serialized():
    calls = []
    caller = threading.get_ident()
    pool = client(on_ticker=lambda ws, t: calls.append(("tick", threading.get_ident())),
                  on_error=lambda error: calls.append((str(error), threading.get_ident())),
                  on_close=lambda: calls.append(("close", threading.get_ident())))

    def emit(socket):
        socket.callbacks["on_error"](socket, "oops")
        socket.emit("BTC-USD")
    pool.ws.behavior = emit
    pool.run()
    assert calls == [("oops", caller), ("tick", caller), ("close", caller)]


def test_bad_message_and_callback_exception_do_not_kill_pool():
    errors, delivered = [], []

    def callback(ws, data):
        delivered.append(data["id"])
        if data["id"] == "BTC-USD":
            raise RuntimeError("sink failed")
    pool = client(on_ticker=callback, on_error=errors.append)

    def emit(socket):
        socket.callbacks["on_message"](socket, "bad!")
        socket.emit("BTC-USD")
        socket.emit("ETH-USD")
    pool.ws.behavior = emit
    pool.run()
    assert delivered == ["BTC-USD", "ETH-USD"]
    assert len(errors) == 2
    assert str(errors[1]) == "sink failed"


def test_slow_callback_applies_backpressure_without_dropping():
    received = []
    pool = client(queue_size=1)

    def callback(ws, data):
        if not received:
            time.sleep(0.25)
        received.append(data["id"])
    pool.on_ticker = callback
    pool.ws.behavior = lambda socket: [socket.emit(str(i)) for i in range(10)]
    pool.run()
    assert received == [str(i) for i in range(10)]
    assert pool.diagnostics["backpressure_events"] > 0
    assert pool.diagnostics["discarded_on_shutdown"] == 0
    assert pool.diagnostics["queue_depth"] == 0


def test_close_from_callback_releases_full_queue_and_closes_all():
    pool = client(ticker_names=["BTC-USD", "ETH-USD"], symbols_per_connection=1,
                  queue_size=1)

    def callback(ws, data):
        time.sleep(0.15)
        pool.close()
    pool.on_ticker = callback
    for socket in pool.connections:
        socket.behavior = lambda s: [s.emit(str(i)) for i in range(10)]
    pool.run()
    assert all(s.closes == 1 for s in pool.connections)
    assert all(not worker.is_alive() for worker in pool._workers)
    assert pool.diagnostics["discarded_on_shutdown"] > 0
    assert pool.diagnostics["queue_depth"] == 0


def test_close_before_run_and_late_open_cannot_subscribe():
    pool = client()
    pool.close()
    pool.run()
    assert pool.ws.runs == 0
    pool.on_open(pool.ws)
    assert pool.ws.sent == []
    with pytest.raises(RuntimeError, match="only be called once"):
        pool.run()


def test_diagnostics_are_copies():
    pool = client()
    snapshot = pool.diagnostics
    snapshot["connections"][0]["symbols"].append("OTHER")
    assert pool.diagnostics["connections"][0]["symbols"] == ["AMZN"]


def test_out_of_order_session_snapshot_keeps_newest_quote_in_pool():
    received = []
    pool = client(ticker_names=["AAPL"], on_ticker=lambda ws, data: received.append(data))

    def emit(socket):
        for stamp, session in ((1791790800000, 4), (1791576000000, 1)):
            message = yaticker(id="AAPL", price=337, time=stamp, marketHours=session)
            socket.callbacks["on_message"](socket, base64.b64encode(message.SerializeToString()).decode())
    pool.ws.behavior = emit
    pool.run()
    observation = pool.diagnostics["symbols"]["AAPL"]
    assert observation["last_quote_time"] == 1791790800
    assert observation["last_message_quote_time"] == 1791576000
    assert observation["quote_market_hours"] == 4
    assert observation["older_quote_count"] == 1
    assert observation["received_count"] == len(received) == 2


def test_cli_can_close_client_while_run_is_blocking():
    dashboard = Dashboard(["BTC-USD"])
    original = Socket.run_forever
    from unittest.mock import patch
    entered = threading.Event()

    def run(self, **kwargs):
        self.behavior = lambda socket: (entered.set(), socket.stopped.wait(2))
        original(self, **kwargs)
    with patch.object(Socket, "run_forever", run):
        worker = threading.Thread(target=dashboard.run_ws, args=(False,))
        worker.start()
        assert entered.wait(2)
        assert dashboard.yt is not None
        dashboard.stop()
        worker.join(2)
    assert not worker.is_alive()
    assert dashboard.yt.ws.closes == 1


def test_cli_capacity_error_stops_instead_of_retrying():
    dashboard = Dashboard(["T{}".format(i) for i in range(401)])
    dashboard.run_ws(False)
    assert dashboard.stop_event.is_set()
    assert isinstance(dashboard.fatal_error, ValueError)
    assert "increase max_connections" in str(dashboard.fatal_error)


def test_cli_configuration_error_exits_with_clear_message(monkeypatch, capsys):
    from yliveticker import cli
    monkeypatch.setattr(cli, "Console", None)
    monkeypatch.setattr(
        "sys.argv", ["yliveticker", "watch", "BTC-USD", "--symbols-per-connection", "101"],
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert "must not exceed 100" in capsys.readouterr().err
