"""Fault injection for client-side behavior; no assertions about Yahoo uptime."""

import asyncio
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yliveticker import AsyncYLiveTicker, YLiveTicker, YTimeSeries
from yliveticker.dashboard import build_dashboard
from yliveticker.instruments import DEFAULT_SYMBOLS, instrument
from yliveticker.observability import symbol_status
from yliveticker.sinks.base import BaseTSDBSink, SinkWriteError


class MemorySink(BaseTSDBSink):
    def __init__(self, **kwargs):
        self.fail = False
        self.writes = []
        super().__init__(flush_interval=60, retry_interval=60, **kwargs)

    def write_batch(self, batch):
        if self.fail:
            raise OSError("storage unavailable")
        self.writes.extend(batch)


def test_outage_retains_batch_bounds_memory_and_retries_on_stop():
    sink = MemorySink(batch_size=2, max_buffer_size=3)
    sink.fail = True
    for i in range(3):
        sink.on_ticker(None, {"id": "A", "price": i})
    assert sink.diagnostics["pending"] == 3
    assert sink.diagnostics["write_failures"] == 1
    with pytest.raises(BufferError):
        sink.on_ticker(None, {"id": "A"})
    assert sink.diagnostics["rejected"] == 1
    sink.fail = False
    sink.stop()
    assert [tick["price"] for tick in sink.writes] == [0, 1, 2]
    assert sink.diagnostics["written_by_symbol"] == {"A": 3}
    assert sink.diagnostics["pending"] == 0
    assert sink.diagnostics["first_write_seconds"] >= 0
    assert not sink._flush_thread.is_alive()


def test_shutdown_failure_is_explicit_and_preserves_pending_records():
    sink = MemorySink(batch_size=1)
    sink.fail = True
    sink.on_ticker(None, {"id": "A"})
    with pytest.raises(SinkWriteError, match="1 ticks remain"):
        sink.stop()
    assert sink.diagnostics["pending"] == 1
    assert not sink._flush_thread.is_alive()


def test_periodic_retry_recovers_without_new_ticks():
    recovered = threading.Event()

    class RecoveringSink(BaseTSDBSink):
        def write_batch(self, batch):
            if not recovered.is_set():
                raise OSError("offline")

    sink = RecoveringSink(batch_size=1, flush_interval=.02, retry_interval=.02)
    try:
        sink.on_ticker(None, {"id": "A"})
        recovered.set()
        deadline = time.monotonic() + 2
        while sink.diagnostics["pending"] and time.monotonic() < deadline:
            time.sleep(.01)
        assert sink.diagnostics["written"] == 1
    finally:
        sink.stop()


def test_questdb_uses_nanoseconds():
    from yliveticker.sinks.questdb import QuestDBSink
    with patch("yliveticker.sinks.questdb.qdb.Sender") as sender, \
            patch("yliveticker.sinks.questdb.qdb.TimestampNanos") as timestamp:
        sink = QuestDBSink()
        try:
            sink.write_batch([dict(id="A", price=1, dayVolume=10, timestamp=1600000000123)])
            timestamp.assert_called_once_with(1600000000123000000)
            sender.from_conf.return_value.__enter__.return_value.flush.assert_called_once()
        finally:
            sink.stop()


def test_timescale_rollback_allows_retry():
    from yliveticker.sinks.timescaledb import TimescaleDBSink
    with patch("yliveticker.sinks.timescaledb.psycopg2.connect") as connect, \
            patch("yliveticker.sinks.timescaledb.execute_values") as execute:
        connect.return_value.closed = False
        sink = TimescaleDBSink("mock", batch_size=1, retry_interval=60)
        execute.side_effect = [RuntimeError("transaction aborted"), None]
        sink.on_ticker(None, dict(id="A", price=1, dayVolume=2, timestamp=1600000000123))
        connect.return_value.rollback.assert_called_once()
        assert sink.diagnostics["pending"] == 1
        sink.stop()
        assert execute.call_count == 2
        assert sink.diagnostics["written"] == 1


def test_timestream_chunks_and_preserves_milliseconds():
    from yliveticker.sinks.timestream import TimestreamSink
    with patch("yliveticker.sinks.timestream.boto3.client") as client:
        sink = TimestreamSink("database", "table", region_name="us-east-1")
        try:
            sink.write_batch([dict(id="A", price=1, dayVolume=10, timestamp=1600000000123)] * 101)
            writes = client.return_value.write_records.call_args_list
            assert [len(call.kwargs["Records"]) for call in writes] == [100, 1]
            assert writes[0].kwargs["Records"][0]["Time"] == "1600000000123"
            assert writes[0].kwargs["Records"][0]["TimeUnit"] == "MILLISECONDS"
            assert client.call_args.kwargs["config"].read_timeout == 5
        finally:
            sink.stop()


def test_delayed_quote_is_active_and_silence_is_not_unsupported():
    now = datetime(2026, 10, 12, 1, tzinfo=timezone.utc).timestamp()
    state = symbol_status("FPH.NZ", dict(last_received_time=now - 2,
                          last_quote_time=now - 1200, received_count=3), {}, now)
    assert state["state"] == "Receiving delayed quotes"
    assert state["receipt_age"] == 2 and state["quote_age"] == 1200
    assert symbol_status("NVDA", {}, {}, now)["state"] == "Outside regular hours (estimated)"
    assert symbol_status("NOT-A-KNOWN-SYMBOL", {}, {}, now)["state"] == "Silent / support unknown"
    assert symbol_status("BTC-USD", {}, {"last_error": "failed"}, now)["state"] == "Storage write failed"


def test_registry_utc_and_daylight_saving():
    assert instrument("FPH.NZ").currency == "NZD"
    assert "00:00–02:30 and 03:30–06:30 UTC" in instrument("7203.T").description()
    assert "14:30–21:00 UTC" in instrument("NVDA").description()
    assert "13:30–20:00 UTC" in instrument("NVDA").description()
    assert "previous UTC day" in instrument("FPH.NZ").description()
    assert instrument("NVDA").expected_open(datetime(2026, 7, 15, 14, tzinfo=timezone.utc))
    assert not instrument("NVDA").expected_open(datetime(2026, 1, 15, 14, tzinfo=timezone.utc))


def test_generated_dashboard_matches_and_filters_volume_selection():
    root = Path(__file__).parents[1]
    assert json.loads((root / "docker/grafana/dashboards/dashboard.json").read_text()) == build_dashboard()
    dashboard = build_dashboard(["FPH.NZ", "CUSTOM"])
    symbols, volume = dashboard["templating"]["list"]
    assert '{_value: "CUSTOM"}' in symbols["query"]
    assert '{_value: "NVDA"}' not in symbols["query"]
    assert "Unknown market" in symbols["query"]
    assert "${symbol:regex}" in volume["query"]
    feed = next(p for p in dashboard["panels"] if p["id"] == 6)
    assert 'r._measurement == "ticker_ingest"' in feed["targets"][0]["query"]
    assert len(DEFAULT_SYMBOLS) == 17


def test_retention_snapshot_and_session_volume_semantics():
    series = YTimeSeries(max_points=3)
    for i, volume in enumerate([1000, 1100, 5, 0]):
        series.on_ticker(None, dict(id="A", price=i, timestamp=1600000000000 + i * 1000, dayVolume=volume))
    assert len(series.data) == 3 and series.evicted_points == 1
    result = series.get_ohlcv("1s")["A"]
    assert "volume" not in result
    assert result["session_volume"].iloc[:2].tolist() == [1100, 5]
    assert result["session_volume"].isna().iloc[2]
    assert str(result.index.tz) == "UTC"


class Socket:
    def __init__(self, url, **callbacks):
        self.callbacks, self.sent = callbacks, []
        self.closed = threading.Event()

    def send(self, message):
        self.sent.append(json.loads(message))

    def close(self, **options):
        self.closed.set()

    def run_forever(self, **options):
        self.callbacks["on_open"](self)
        self.closed.wait(5)


def test_dynamic_subscriptions_reuse_capacity_and_resubscribe_current_state():
    with patch("yliveticker.websocket.WebSocketApp", Socket):
        client = YLiveTicker(ticker_names=["A", "B"], symbols_per_connection=1, max_connections=3, start=False)
        for ws in client.connections:
            client.on_open(ws)
        client.unsubscribe("A")
        client.subscribe(["C", "D", "C"])
        assert client.connection_symbols == (("C",), ("B",), ("D",))
        assert client.connections[0].sent == [{"subscribe": ["A"]}, {"unsubscribe": ["A"]}, {"subscribe": ["C"]}]
        assert client.connections[1].sent == [{"subscribe": ["B"]}]
        with pytest.raises(ValueError):
            client.subscribe(["E", "F"])
        assert client.ticker_names == ["B", "C", "D"]
        client.on_open(client.ws)
        assert client.ws.sent[-1] == {"subscribe": ["C"]}
        client.close()
        with pytest.raises(RuntimeError):
            client.subscribe("E")


def test_dynamic_subscription_starts_new_worker():
    with patch("yliveticker.websocket.WebSocketApp", Socket):
        client = YLiveTicker(ticker_names=["A"], symbols_per_connection=1, start=False)
        thread = threading.Thread(target=client.run)
        thread.start()
        try:
            deadline = time.monotonic() + 2
            while not client.ws.sent and time.monotonic() < deadline:
                time.sleep(.01)
            client.subscribe("B")
            deadline = time.monotonic() + 2
            while not client.connections[1].sent and time.monotonic() < deadline:
                time.sleep(.01)
            assert client.connections[1].sent == [{"subscribe": ["B"]}]
        finally:
            client.close()
            thread.join(3)
        assert not thread.is_alive()


def test_failed_subscription_send_preserves_complete_desired_state():
    with patch("yliveticker.websocket.WebSocketApp", Socket):
        client = YLiveTicker(ticker_names=["A"], symbols_per_connection=2, start=False)
        client.on_open(client.ws)
        with patch.object(client.ws, "send", side_effect=OSError("disconnected")):
            with pytest.raises(OSError):
                client.subscribe(["B", "C"])
        assert client.connection_symbols == (("A", "B"), ("C",))
        assert len(client.connections) == 2
        client.on_open(client.connections[1])
        assert client.connections[1].sent == [{"subscribe": ["C"]}]
        client.close()


def test_async_iteration_and_full_queue_shutdown():
    from yliveticker.yaticker_pb2 import yaticker
    import base64

    class EmittingSocket(Socket):
        def run_forever(self, **options):
            self.callbacks["on_open"](self)
            for i in range(100):
                self.callbacks["on_message"](self, base64.b64encode(
                    yaticker(id="A", price=i, time=1600000000000).SerializeToString()).decode())

    async def run():
        async with AsyncYLiveTicker(["A"], queue_size=1, reconnect=0) as feed:
            tick = await feed.__anext__()
            assert tick["id"] == "A"
            await asyncio.sleep(.2)
            assert feed.diagnostics["async_queue_depth"] <= 1
        assert not feed._thread.is_alive()

    with patch("yliveticker.websocket.WebSocketApp", EmittingSocket):
        asyncio.run(asyncio.wait_for(run(), 5))


def test_async_cancellation_closes_transport():
    async def run():
        async with AsyncYLiveTicker(["A"], reconnect=0) as feed:
            task = asyncio.create_task(feed.__anext__())
            await asyncio.sleep(.02)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not feed._thread.is_alive()
    with patch("yliveticker.websocket.WebSocketApp", Socket):
        asyncio.run(asyncio.wait_for(run(), 5))
