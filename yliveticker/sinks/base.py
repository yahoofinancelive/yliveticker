"""Bounded in-memory batching. Retries are best effort, not durable delivery."""

import abc
import logging
import math
import threading
import time

logger = logging.getLogger(__name__)


class SinkWriteError(RuntimeError):
    """Shutdown could not persist all accepted records; inspect diagnostics."""


class BaseTSDBSink(abc.ABC):
    def __init__(self, batch_size=100, flush_interval=5.0, max_buffer_size=10000,
                 retry_interval=1.0, max_retry_interval=30.0):
        for name, value in (("batch_size", batch_size), ("max_buffer_size", max_buffer_size)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(name + " must be a positive integer")
        for name, value in (("flush_interval", flush_interval),
                            ("retry_interval", retry_interval),
                            ("max_retry_interval", max_retry_interval)):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(name + " must be finite and positive")
        if max_buffer_size < batch_size:
            raise ValueError("max_buffer_size must be at least batch_size")
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.max_buffer_size = max_buffer_size
        self.retry_interval = retry_interval
        self.max_retry_interval = max_retry_interval
        self._buffer = []
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._retry_at = 0
        self._failures = 0
        self._stats = dict(accepted=0, written=0, write_failures=0, rejected=0,
                           last_error=None, first_write_seconds=None)
        self._started_at = time.monotonic()
        self._next_flush = self._started_at + flush_interval
        self._written_by_symbol = {}
        self._flush_thread = threading.Thread(target=self._periodic_flush,
                                               name="yliveticker-sink", daemon=True)
        self._flush_thread.start()

    @property
    def diagnostics(self):
        with self._lock:
            return dict(self._stats, pending=len(self._buffer),
                        written_by_symbol=dict(self._written_by_symbol))

    def on_ticker(self, ws, msg):
        with self._lock:
            if self._stop_event.is_set():
                self._stats["rejected"] += 1
                raise RuntimeError("sink is stopped")
            if len(self._buffer) >= self.max_buffer_size:
                self._stats["rejected"] += 1
                raise BufferError("sink buffer is full; tick not accepted (see diagnostics)")
            self._buffer.append(dict(msg))
            self._stats["accepted"] += 1
            if len(self._buffer) >= self.batch_size:
                self._flush_locked()

    def _periodic_flush(self):
        while not self._stop_event.wait(min(self.flush_interval, self.retry_interval)):
            with self._lock:
                if self._failures or time.monotonic() >= self._next_flush:
                    self._flush_locked()

    def flush(self):
        """Attempt pending writes; False means storage failed or is backing off."""
        with self._lock:
            return self._flush_locked()

    def _flush_locked(self, force=False):
        if self._buffer and not force and time.monotonic() < self._retry_at:
            return False
        while self._buffer:
            batch = self._buffer[:self.batch_size]
            try:
                self.write_batch(batch)
            except Exception as error:
                # Retain the batch. A lost response after commit can cause
                # duplicates on retry; this is not exactly-once delivery.
                self._failures += 1
                self._stats["write_failures"] += 1
                self._stats["last_error"] = str(error)
                self._retry_at = time.monotonic() + min(
                    self.max_retry_interval, self.retry_interval * 2 ** min(self._failures - 1, 16))
                logger.error("TSDB write failed; retaining %d ticks for retry: %s", len(self._buffer), error)
                return False
            del self._buffer[:len(batch)]
            self._stats["written"] += len(batch)
            for msg in batch:
                symbol = msg.get("id")
                self._written_by_symbol[symbol] = self._written_by_symbol.get(symbol, 0) + 1
            if self._stats["first_write_seconds"] is None:
                self._stats["first_write_seconds"] = time.monotonic() - self._started_at
            self._failures = 0
            self._retry_at = 0
            self._stats["last_error"] = None
        self._next_flush = time.monotonic() + self.flush_interval
        return True

    @abc.abstractmethod
    def write_batch(self, batch):
        pass

    def stop(self):
        self._stop_event.set()
        self._flush_thread.join()
        with self._lock:
            if not self._flush_locked(force=True):
                raise SinkWriteError("{} ticks remain unpersisted in memory: {}".format(
                    len(self._buffer), self._stats["last_error"]))
