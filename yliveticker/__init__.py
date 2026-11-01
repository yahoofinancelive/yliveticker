import base64
import json
import math
import queue
import threading
import time

import websocket

from .logger import writeline
from .observability import new_observation, record_observation
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
                 max_connections=4, queue_size=1000, start=True,
                 include_receipt_time=False):
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
        self._symbols_per_connection = symbols_per_connection
        self._max_connections = max_connections
        self._include_receipt_time = include_receipt_time
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
        self._lock = threading.RLock()
        self._started = False
        self._closed = False
        self._workers = []
        self._backpressure_events = 0
        self._discarded_on_shutdown = 0
        self._callback_errors = 0
        self._symbol_stats = {symbol: self._new_symbol_stats() for symbol in symbols}
        self._stats = [dict(symbols=list(bucket), state="idle", received_count=0,
                            reconnect_count=0, last_message_time=None)
                       for bucket in self.connection_symbols]
        websocket.enableTrace(enable_socket_trace)
        self.connections = tuple(
            self._new_socket() for _ in self.connection_symbols)
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
                        discarded_on_shutdown=self._discarded_on_shutdown,
                        callback_errors=self._callback_errors,
                        symbols={key: dict(value) for key, value in self._symbol_stats.items()})

    @staticmethod
    def _new_symbol_stats():
        return new_observation()

    def _new_socket(self):
        return websocket.WebSocketApp(
            "wss://streamer.finance.yahoo.com/", on_message=self._receive,
            on_error=lambda ws, error: self._enqueue("error", ws, error),
            on_close=lambda ws, code, reason: self._enqueue("close", ws, (code, reason)),
            on_open=self.on_open)

    @staticmethod
    def _normalize_symbols(symbols):
        if isinstance(symbols, str):
            symbols = [symbols]
        result = []
        for symbol in symbols:
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("symbols must contain nonempty strings")
            if symbol.strip() not in result:
                result.append(symbol.strip())
        return result

    def subscribe(self, symbols):
        """Update desired subscriptions without restarting healthy connections.

        Yahoo provides no subscription acknowledgement. A send failure raises;
        desired subscriptions are retained for the next reconnect.
        """
        symbols = self._normalize_symbols(symbols)
        failed = []
        with self._lock:
            if self._closed:
                raise RuntimeError("client is closed")
            added = [s for s in symbols if s not in self.ticker_names]
            if len(self.ticker_names) + len(added) > self._symbols_per_connection * self._max_connections:
                raise ValueError("subscription exceeds max_connections capacity")
            buckets = [list(bucket) for bucket in self.connection_symbols]
            changes = {}
            for symbol in added:
                index = next((i for i, b in enumerate(buckets)
                              if len(b) < self._symbols_per_connection), len(buckets))
                if index == len(buckets):
                    buckets.append([])
                buckets[index].append(symbol)
                changes.setdefault(index, []).append(symbol)
                self._symbol_stats[symbol] = self._new_symbol_stats()
            self.ticker_names.extend(added)
            self.connection_symbols = tuple(tuple(bucket) for bucket in buckets)
            existing = len(self.connections)
            for index in changes:
                if index == len(self.connections):
                    ws = self._new_socket()
                    self.connections += (ws,)
                    self._indices[id(ws)] = index
                    self._stats.append(dict(symbols=list(buckets[index]), state="idle",
                                            received_count=0, reconnect_count=0, last_message_time=None))
                    if self._started:
                        self._start_worker(ws)
                self._stats[index]["symbols"] = list(buckets[index])
                if index < existing and self._started and self._stats[index]["state"] == "closed":
                    self._start_worker(self.connections[index])
            # Commit the entire desired state before any fallible sends. A failed
            # bucket must not prevent later buckets from being created or updated.
            for index in changes:
                if index < existing and self._stats[index]["state"] == "connected":
                    try:
                        self.connections[index].send(json.dumps({"subscribe": changes[index]}))
                    except Exception as error:
                        failed.append((self.connections[index], error))
        self._raise_send_failure(failed)

    def unsubscribe(self, symbols):
        """Remove desired subscriptions; already queued callbacks may still arrive."""
        symbols = set(self._normalize_symbols(symbols))
        failed = []
        with self._lock:
            if self._closed:
                raise RuntimeError("client is closed")
            removed = {}
            buckets = []
            for index, bucket in enumerate(self.connection_symbols):
                removed[index] = [s for s in bucket if s in symbols]
                buckets.append(tuple(s for s in bucket if s not in symbols))
            self.connection_symbols = tuple(buckets)
            self.ticker_names[:] = [s for s in self.ticker_names if s not in symbols]
            for symbol in symbols:
                self._symbol_stats.pop(symbol, None)
            for index, bucket in enumerate(buckets):
                self._stats[index]["symbols"] = list(bucket)
                if removed[index] and self._stats[index]["state"] == "connected":
                    try:
                        self.connections[index].send(json.dumps({"unsubscribe": removed[index]}))
                    except Exception as error:
                        failed.append((self.connections[index], error))
        self._raise_send_failure(failed)

    @staticmethod
    def _raise_send_failure(failed):
        for ws, error in failed:
            try:
                ws.close(timeout=1)  # Worker reconnects using the desired state.
            except Exception as close_error:
                writeline(close_error)
        if failed:
            raise failed[0][1]

    def _start_worker(self, ws):
        self._stats[self._indices[id(ws)]]["state"] = "connecting"
        worker = threading.Thread(target=self._worker, args=(ws,),
                                  name="yliveticker-{}".format(self._indices[id(ws)]), daemon=True)
        self._workers.append(worker)
        worker.start()

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
        received_ns = time.time_ns()
        with self._lock:
            stats = self._stats[self._indices[id(ws)]]
            stats["received_count"] += 1
            stats["last_message_time"] = time.time()
        try:
            data = self._decode(message)
        except Exception as error:
            self._enqueue("error", ws, error)
            return
        with self._lock:
            if data["id"] in self._symbol_stats:
                symbol = self._symbol_stats[data["id"]]
                record_observation(symbol, data, received_ns / 1e9)
        if self._include_receipt_time:
            data["_received_at_ns"] = received_ns
        self._enqueue("tick", ws, data)

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
        # Subscription changes and initial worker creation must be atomic;
        # otherwise a concurrent subscribe can start the same socket twice.
        with self._lock:
            if self._started:
                raise RuntimeError("YLiveTicker.run() can only be called once")
            self._started = True
            if self._stop.is_set():
                return
            for ws in self.connections:
                self._start_worker(ws)
        try:
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
                        with self._lock:
                            self._callback_errors += 1
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

    @staticmethod
    def _decode(message):
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
        return data

    def on_message(self, ws, message):
        data = message if isinstance(message, dict) else self._decode(message)
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
        with self._lock:
            index = self._indices[id(ws)]
            if self._stop.is_set():
                return
            if self.connection_symbols[index]:
                ws.send(json.dumps({"subscribe": self.connection_symbols[index]}))
            self._stats[index]["state"] = "connected"
        writeline("### connection {} is open ###".format(index + 1))


from .async_client import AsyncYLiveTicker  # noqa: E402,F401
