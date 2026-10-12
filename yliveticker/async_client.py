"""Async iteration over the same bounded pool used by the callback API."""

import asyncio
import concurrent.futures
import threading


class AsyncYLiveTicker:
    """Use as ``async with AsyncYLiveTicker(...) as feed: async for tick in feed``.

    A full async queue backpressures the dispatcher. Closing discards unread
    async items; it cannot interrupt arbitrary user callbacks or replay gaps.
    """

    def __init__(self, ticker_names=None, queue_size=1000, **options):
        from . import YLiveTicker
        self._loop = None
        self._queue = asyncio.Queue(maxsize=queue_size)
        self._closing = threading.Event()
        self._done = threading.Event()
        self._thread = None
        self._error = None
        self.client = YLiveTicker(ticker_names=ticker_names, start=False,
                                  queue_size=queue_size, on_ticker=self._receive, **options)

    @property
    def diagnostics(self):
        return dict(self.client.diagnostics, async_queue_depth=self._queue.qsize())

    def _receive(self, ws, tick):
        if self._closing.is_set():
            return
        future = asyncio.run_coroutine_threadsafe(self._queue.put(tick), self._loop)
        while not self._closing.is_set():
            try:
                future.result(timeout=0.1)
                return
            except concurrent.futures.TimeoutError:
                continue
        future.cancel()

    def _run(self):
        try:
            self.client.run()
        except BaseException as error:
            self._error = error
        finally:
            self._done.set()

    async def __aenter__(self):
        if self._thread is not None:
            raise RuntimeError("AsyncYLiveTicker can only be started once")
        self._loop = asyncio.get_running_loop()
        self._thread = threading.Thread(target=self._run, name="yliveticker-async", daemon=True)
        self._thread.start()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._thread is None:
            raise RuntimeError("Use async with before iterating")
        while not self._closing.is_set():
            if self._done.is_set() and self._queue.empty():
                if self._error is not None:
                    raise self._error
                raise StopAsyncIteration
            try:
                return await asyncio.wait_for(self._queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                await self.close()
                raise
        raise StopAsyncIteration

    async def subscribe(self, symbols):
        await asyncio.to_thread(self.client.subscribe, symbols)

    async def unsubscribe(self, symbols):
        await asyncio.to_thread(self.client.unsubscribe, symbols)

    async def close(self):
        self._closing.set()  # Unblock a producer waiting on a full async queue.
        await asyncio.to_thread(self.client.close)
        if self._thread is not None:
            await asyncio.to_thread(self._thread.join, 10)
            if self._thread.is_alive():
                raise RuntimeError("stream thread did not stop within 10 seconds")
