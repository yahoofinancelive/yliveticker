import abc
import threading
import time
import logging

logger = logging.getLogger(__name__)

class BaseTSDBSink(abc.ABC):
    def __init__(self, batch_size=100, flush_interval=5.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._buffer = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._last_flush_time = time.time()
        
        self._flush_thread = threading.Thread(target=self._periodic_flush, daemon=True)
        self._flush_thread.start()

    def on_ticker(self, ws, msg):
        with self._lock:
            self._buffer.append(msg)
            if len(self._buffer) >= self.batch_size:
                self._flush_locked()

    def _periodic_flush(self):
        while not self._stop_event.is_set():
            time.sleep(1.0)
            with self._lock:
                if time.time() - self._last_flush_time >= self.flush_interval:
                    self._flush_locked()

    def _flush_locked(self):
        if not self._buffer:
            self._last_flush_time = time.time()
            return

        batch_to_write = list(self._buffer)
        self._buffer.clear()
        self._last_flush_time = time.time()
        
        try:
            self.write_batch(batch_to_write)
        except Exception as e:
            logger.error(f"Error writing batch to TSDB: {e}")

    @abc.abstractmethod
    def write_batch(self, batch):
        pass

    def stop(self):
        self._stop_event.set()
        self._flush_thread.join(timeout=2.0)
        with self._lock:
            self._flush_locked()
