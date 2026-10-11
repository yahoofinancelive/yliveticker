"""Local-only run measurements and best-effort dashboard heartbeats."""

import json
import logging
import threading
import time
from pathlib import Path

from .observability import symbol_status

logger = logging.getLogger(__name__)


class CollectorMonitor:
    def __init__(self, sink, symbols, synthetic=False, metrics_path=None):
        self.sink = sink
        self.symbols = ["SYNTH-" + s if synthetic else s for s in symbols]
        self.synthetic = synthetic
        self.metrics_path = Path(metrics_path) if metrics_path else None
        self.client = None
        self.started_at = time.monotonic()
        self._observations = {s: {} for s in self.symbols}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="yliveticker-monitor", daemon=True)

    def on_ticker(self, ws, msg):
        msg = dict(msg)
        msg.setdefault("_received_at_ns", time.time_ns())
        with self._lock:
            if msg["id"] in self._observations:
                old = self._observations[msg["id"]]
                self._observations[msg["id"]] = dict(
                    received_count=old.get("received_count", 0) + 1,
                    last_received_time=msg["_received_at_ns"] / 1e9,
                    last_quote_time=msg["timestamp"] / 1000)
        self.sink.on_ticker(ws, msg)

    def snapshot(self):
        storage = self.sink.diagnostics
        pool = self.client.diagnostics if self.client else {}
        with self._lock:
            observations = {k: dict(v) for k, v in self._observations.items()}
        states = []
        for symbol in self.symbols:
            observation = pool.get("symbols", {}).get(symbol, observations[symbol])
            state = symbol_status(symbol, observation, storage)
            state["connection"] = "Synthetic" if self.synthetic else next(
                (c["state"] for c in pool.get("connections", []) if symbol in c["symbols"]), "Unknown")
            states.append(state)
        return dict(mode="synthetic" if self.synthetic else "live", uptime_seconds=time.monotonic() - self.started_at,
                    measured_at=time.time(), storage=storage, pool=pool, symbols=states)

    def save_metrics(self):
        snapshot = self.snapshot()
        if self.metrics_path:
            temporary = self.metrics_path.with_suffix(self.metrics_path.suffix + ".tmp")
            temporary.write_text(json.dumps(snapshot, indent=2) + "\n")
            temporary.replace(self.metrics_path)
        return snapshot

    def _run(self):
        while not self._stop.is_set():
            try:
                self.sink.write_status(self.save_metrics()["symbols"])
            except Exception as error:
                logger.warning("Status heartbeat failed; dashboard status will become unknown: %s", error)
            self._stop.wait(5)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()
