import base64
import json
import math
import queue
import threading
import time

import websocket

from .logger import writeline
from .yaticker_pb2 import yaticker
from .timeseries import YTimeSeries  # noqa: F401


class YLiveTicker:
    """Stream deduplicated symbols over a bounded pool of Yahoo connections.

    Construction blocks by default. Use ``start=False`` followed by ``run()``
    to obtain the client before streaming begins. Application callbacks run
    serially on the thread calling ``run()``.
    """

    def __init__(self, on_ticker=None, ticker_names=None, on_error=None,
                 on_close=None, enable_socket_trace=False, reconnect=5,
                 ping_interval=15, ping_timeout=10, symbols_per_connection=100,
                 max_connections=4, queue_size=1000, start=True):
        for name, value in (("symbols_per_connection", symbols_per_connection),
                            ("max_connections", max_connections),
                            ("queue_size", queue_size)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("{} must be a positive integer".format(name))
        if symbols_per_connection > 100:
            raise ValueError("symbols_per_connection must not exceed 100")
        if ticker_names is None:
            ticker_names = ["AMZN"]
        if isinstance(ticker_names, str):
            ticker_names = [ticker_names]
        symbols, seen = [], set()
        for symbol in ticker_names:
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("ticker_names must contain nonempty strings")
            symbol = symbol.strip()
            if symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
        if not symbols:
            raise ValueError("ticker_names must contain at least one symbol")
        required = (len(symbols) + symbols_per_connection - 1) // symbols_per_connection
        if required > max_connections:
            raise ValueError(
                "{} symbols require {} connections; increase max_connections "
                "(currently {})".format(len(symbols), required, max_connections))
        reconnect = 0 if reconnect is None else reconnect
        if not isinstance(reconnect, (int, float)) or not math.isfinite(reconnect) or reconnect < 0:
            raise ValueError("reconnect must be a finite nonnegative number")
        if (not isinstance(ping_interval, (int, float)) or
                not math.isfinite(ping_interval) or ping_interval < 0):
            raise ValueError("ping_interval must be a finite nonnegative number")
        if ping_timeout is not None:
            if (not isinstance(ping_timeout, (int, float)) or
                    not math.isfinite(ping_timeout) or ping_timeout <= 0):
                raise ValueError("ping_timeout must be a finite positive number or None")
            if ping_interval and ping_interval <= ping_timeout:
                raise ValueError("ping_interval must be greater than ping_timeout")

        self.ticker_names = symbols
        self.symbol_list = {"subscribe": symbols}
        self.connection_symbols = tuple(
            tuple(symbols[i:i + symbols_per_connection])
            for i in range(0, len(symbols), symbols_per_connection))
        self.on_ticker = on_ticker
        self.on_custom_error = on_error
        self.on_custom_close = on_close
        self.yaticker = yaticker()  # Compatibility; parsing uses a local message.
        self._reconnect = reconnect
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._events = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._started = False
        self._closed = False
        self._workers = []
        self._backpressure_events = 0
        self._discarded_on_shutdown = 0
        self._stats = [dict(symbols=list(bucket), state="idle", received_count=0,
                            reconnect_count=0, last_message_time=None)
                       for bucket in self.connection_symbols]
        websocket.enableTrace(enable_socket_trace)
        self.connections = tuple(
            websocket.WebSocketApp(
                "wss://streamer.finance.yahoo.com/",
                on_message=self._receive,
                on_error=lambda ws, error: self._enqueue("error", ws, error),
                on_close=lambda ws, code, reason: self._enqueue("close", ws, (code, reason)),
                on_open=self.on_open,
            ) for _ in self.connection_symbols)
        self.ws = self.connections[0]
        self._indices = {id(ws): i for i, ws in enumerate(self.connections)}
        if start:
            self.run()

    @property
    def diagnostics(self):
        """Return a snapshot of pool activity without exposing mutable state."""
        with self._lock:
            connections = [dict(item, symbols=list(item["symbols"])) for item in self._stats]
            return dict(connections=connections, queue_depth=self._events.qsize(),
                        backpressure_events=self._backpressure_events,
                        discarded_on_shutdown=self._discarded_on_shutdown)

    def _enqueue(self, kind, ws, payload):
        # Bound memory and apply backpressure to slow sinks. Stop releases
        # producers even when the callback queue is full.
        while not self._stop.is_set():
            try:
                self._events.put((kind, ws, payload), timeout=0.1)
                return
            except queue.Full:
                with self._lock:
                    self._backpressure_events += 1
        if kind == "tick":
            with self._lock:
                self._discarded_on_shutdown += 1

    def _receive(self, ws, message):
        with self._lock:
            stats = self._stats[self._indices[id(ws)]]
            stats["received_count"] += 1
            stats["last_message_time"] = time.time()
        self._enqueue("tick", ws, message)

    def _worker(self, ws):
        index = self._indices[id(ws)]
        try:
            while not self._stop.is_set():
                with self._lock:
                    self._stats[index]["state"] = "connecting"
                try:
                    # Retry clean server closes as well as errors. A failed
                    # socket never restarts the other buckets.
                    ws.run_forever(reconnect=0, ping_interval=self._ping_interval,
                                   ping_timeout=self._ping_timeout)
                except Exception as error:
                    self._enqueue("error", ws, error)
                if not self._reconnect or self._stop.is_set():
                    break
                with self._lock:
                    self._stats[index]["state"] = "reconnecting"
                    self._stats[index]["reconnect_count"] += 1
                if self._stop.wait(self._reconnect):
                    break
        finally:
            with self._lock:
                self._stats[index]["state"] = "closed"

    def run(self):
        """Block until closed; each client can be started only once."""
        with self._lock:
            if self._started:
                raise RuntimeError("YLiveTicker.run() can only be called once")
            self._started = True
        if self._stop.is_set():
            return
        self._workers = [threading.Thread(target=self._worker, args=(ws,),
                                          name="yliveticker-{}".format(i), daemon=True)
                         for i, ws in enumerate(self.connections)]
        try:
            for worker in self._workers:
                worker.start()
            shutdown_deadline = None
            while True:
                if self._stop.is_set() and shutdown_deadline is None:
                    shutdown_deadline = time.monotonic() + 5
                try:
                    kind, ws, payload = self._events.get(timeout=0.1)
                except queue.Empty:
                    if not any(w.is_alive() for w in self._workers):
                        break
                    if shutdown_deadline is not None and time.monotonic() >= shutdown_deadline:
                        break
                    continue
                if kind == "tick":
                    try:
                        self.on_message(ws, payload)
                    except Exception as error:
                        self.on_error(ws, error)
                elif kind == "error":
                    self.on_error(ws, payload)
                else:
                    self.on_close(ws, *payload)
        except KeyboardInterrupt:
            pass
        finally:
            self.close()
            deadline = time.monotonic() + 5
            for worker in self._workers:
                if worker.ident is not None:
                    worker.join(max(0, deadline - time.monotonic()))

    def close(self):
        """Stop all connections. ``run()`` drains already queued callbacks."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
        for ws in self.connections:
            try:
                ws.close(timeout=1)
            except Exception as error:
                writeline(error)

    def on_message(self, ws, message):
        decoded = yaticker()
        decoded.ParseFromString(base64.b64decode(message, validate=True))
        data = {
            "id": decoded.id,
            "exchange": decoded.exchange,
            "quoteType": decoded.quoteType,
            "price": decoded.price,
            "timestamp": decoded.time,
            "marketHours": decoded.marketHours,
            "changePercent": decoded.changePercent,
            "dayVolume": decoded.dayVolume,
            "dayHigh": decoded.dayHigh,
            "dayLow": decoded.dayLow,
            "change": decoded.change,
            "openPrice": decoded.openPrice,
            "priceHint": decoded.priceHint,
        }
        if decoded.currency:
            data["currency"] = decoded.currency
        if self.on_ticker is None:
            print(json.dumps(data))
        else:
            self.on_ticker(ws, data)

    def on_error(self, ws, error):
        if self.on_custom_error is None:
            writeline(error)
        else:
            self.on_custom_error(error)

    def on_close(self, ws, close_status_code=None, close_msg=None):
        if self.on_custom_close is None:
            writeline("### connection is closed ###")
        else:
            self.on_custom_close()

    def on_open(self, ws):
        if self._stop.is_set():
            ws.close(timeout=1)
            return
        index = self._indices[id(ws)]
        ws.send(json.dumps({"subscribe": self.connection_symbols[index]}))
        with self._lock:
            self._stats[index]["state"] = "connected"
        writeline("### connection {} is open ###".format(index + 1))
