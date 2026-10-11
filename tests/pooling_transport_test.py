"""Exercise pool reconnection with real websocket-client and a local server."""

import base64
import hashlib
import json
import socket
import socketserver
import struct
import threading
from collections import Counter

import websocket

from yliveticker import YLiveTicker
from yliveticker.yaticker_pb2 import yaticker


def read_frame(stream):
    header = stream.read(2)
    if len(header) != 2:
        raise EOFError
    size = header[1] & 127
    if size == 126:
        size = struct.unpack("!H", stream.read(2))[0]
    elif size == 127:
        size = struct.unpack("!Q", stream.read(8))[0]
    mask = stream.read(4) if header[1] & 128 else None
    body = stream.read(size)
    if len(body) != size:
        raise EOFError
    if mask:
        body = bytes(value ^ mask[i % 4] for i, value in enumerate(body))
    return header[0] & 15, body


def send_frame(stream, opcode, body):
    length = bytes([len(body)]) if len(body) < 126 else b"\x7e" + struct.pack("!H", len(body))
    stream.write(bytes([128 | opcode]) + length + body)
    stream.flush()


def test_real_transport_recovers_clean_close_without_restarting_other_bucket(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    subscriptions = Counter()
    subscription_lock = threading.Lock()
    errors, ticks = [], Counter()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                self.request.settimeout(3)
                self.rfile.readline()  # GET request
                headers = {}
                while True:
                    line = self.rfile.readline().decode().strip()
                    if not line:
                        break
                    name, value = line.split(":", 1)
                    headers[name.lower()] = value.strip()
                key = headers["sec-websocket-key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                accept = base64.b64encode(hashlib.sha1(key.encode()).digest()).decode()
                self.wfile.write(("HTTP/1.1 101 Switching Protocols\r\n"
                                  "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                                  "Sec-WebSocket-Accept: " + accept + "\r\n\r\n").encode())
                self.wfile.flush()
                opcode, body = read_frame(self.rfile)
                assert opcode == 1
                symbol, = json.loads(body)["subscribe"]
                with subscription_lock:
                    subscriptions[symbol] += 1
                    count = subscriptions[symbol]
                message = yaticker(id=symbol, price=123, time=count)
                send_frame(self.wfile, 1, base64.b64encode(message.SerializeToString()))
                if symbol == "BTC-USD" and count == 1:
                    send_frame(self.wfile, 8, struct.pack("!H", 1000))
                    return
                while True:
                    opcode, body = read_frame(self.rfile)
                    if opcode == 8:
                        send_frame(self.wfile, 8, body)
                        return
                    if opcode == 9:
                        send_frame(self.wfile, 10, body)
            except (EOFError, ConnectionError, socket.timeout):
                return

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    server = Server(("127.0.0.1", 0), Handler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    pool = YLiveTicker(ticker_names=["BTC-USD", "ETH-USD"],
                       symbols_per_connection=1, start=False, reconnect=0.01,
                       on_error=errors.append)
    url = "ws://127.0.0.1:{}/".format(server.server_address[1])
    for ws in pool.connections:
        ws.url = url

    def on_tick(ws, tick):
        ticks[tick["id"]] += 1
        if ticks["BTC-USD"] >= 2 and ticks["ETH-USD"] >= 1:
            pool.close()

    pool.on_ticker = on_tick
    watchdog = threading.Timer(5, pool.close)
    watchdog.start()
    try:
        pool.run()
    finally:
        watchdog.cancel()
        pool.close()
        server.shutdown()
        server.server_close()
        serving.join(2)
    # Some websocket-client versions also deliver a normal close as on_error.
    assert all(isinstance(error, websocket.WebSocketConnectionClosedException) and
               "code 1000" in str(error) for error in errors)
    assert ticks == {"BTC-USD": 2, "ETH-USD": 1}
    assert subscriptions == {"BTC-USD": 2, "ETH-USD": 1}
    assert all(not worker.is_alive() for worker in pool._workers)
    assert pool.diagnostics["queue_depth"] == 0
