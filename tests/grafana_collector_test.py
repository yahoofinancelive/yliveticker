"""Exercise collector configuration, startup failures and shutdown flushing."""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

spec = importlib.util.spec_from_file_location(
    "tsdb_example", Path(__file__).parents[1] / "examples" / "tsdb_example.py",
)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def test_compose_and_collector_default_to_live(monkeypatch):
    monkeypatch.delenv("TICKER_SYNTHETIC", raising=False)
    args = collector.parse_args([])
    assert not args.synthetic
    assert args.symbols == list(collector.DEFAULT_SYMBOLS)
    compose = (Path(__file__).parents[1] / "docker" / "docker-compose.yml").read_text()
    assert "TICKER_SYNTHETIC: ${TICKER_SYNTHETIC:-0}" in compose
    assert "TICKER_SYMBOLS: ${TICKER_SYMBOLS:-}" in compose
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "grafana-quickstart.yml").read_text()
    assert "TICKER_SYMBOLS: BTC-USD" in workflow


def test_symbol_arguments_override_environment(monkeypatch):
    monkeypatch.setenv("TICKER_SYMBOLS", "BTC-USD ETH-USD")
    monkeypatch.setenv("TICKER_SYNTHETIC", "0")
    assert collector.parse_args([]).symbols == ["BTC-USD", "ETH-USD"]
    assert collector.parse_args(["AAPL"]).symbols == ["AAPL"]
    assert collector.parse_args(["--synthetic"]).synthetic
    monkeypatch.setenv("TICKER_SYNTHETIC", "1")
    assert collector.parse_args([]).synthetic


def test_collector_pool_limit_is_configurable(monkeypatch):
    monkeypatch.setenv("TICKER_MAX_CONNECTIONS", "6")
    assert collector.parse_args([]).max_connections == 6
    assert collector.parse_args(["--max-connections", "2"]).max_connections == 2
    with pytest.raises(SystemExit):
        collector.parse_args(["--max-connections", "0"])


def test_live_collector_passes_pool_limit_to_client(monkeypatch):
    monkeypatch.setenv("TICKER_SYNTHETIC", "0")
    with patch.object(collector, "wait_for_influxdb"), \
            patch.object(collector, "InfluxDBSink"), \
            patch.object(collector, "YLiveTicker") as client, \
            patch.object(collector.signal, "signal"):
        collector.main(["BTC-USD", "--max-connections", "6"])
    assert client.call_args.kwargs["max_connections"] == 6


def test_wait_checks_bucket_access_not_just_server_health():
    with patch.object(collector, "InfluxDBClient") as client_type, patch.object(collector.time, "sleep"):
        client = client_type.return_value.__enter__.return_value
        client.ping.return_value = True
        client.buckets_api.return_value.find_bucket_by_name.side_effect = [None, object()]
        collector.wait_for_influxdb("url", "token", "org", "bucket")
        assert client.buckets_api.return_value.find_bucket_by_name.call_count == 2


def test_readiness_timeout_reports_configuration_problem():
    with patch.object(collector, "InfluxDBClient") as client_type:
        client_type.return_value.__enter__.return_value.ping.return_value = False
        with pytest.raises(RuntimeError, match="INFLUX_TOKEN"):
            collector.wait_for_influxdb("url", "token", "org", "bucket", timeout=0)


@pytest.mark.parametrize("synthetic", [False, True])
@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_stop_flushes_sink_when_stream_ends(synthetic, failure, monkeypatch):
    monkeypatch.setenv("TICKER_SYNTHETIC", "0")
    sink = MagicMock()
    with patch.object(collector, "wait_for_influxdb"), \
            patch.object(collector, "InfluxDBSink", return_value=sink), \
            patch.object(collector, "YLiveTicker", side_effect=failure), \
            patch.object(collector, "stream_synthetic", side_effect=failure), \
            patch.object(collector.signal, "signal") as handler:
        args = ["--synthetic", "BTC-USD"] if synthetic else ["BTC-USD"]
        if failure is RuntimeError:
            with pytest.raises(RuntimeError):
                collector.main(args)
        else:
            collector.main(args)
        sink.stop.assert_called_once()
        # Restore the previous SIGTERM handler even after failure.
        assert handler.call_count == 2


def test_synthetic_feed_is_explicitly_labeled_and_uses_yahoo_tick_fields():
    sink = MagicMock()
    with patch.object(collector.time, "sleep", side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            collector.stream_synthetic(sink, ["BTC-USD"])
    tick = sink.on_ticker.call_args.args[1]
    assert tick["id"] == "SYNTH-BTC-USD"
    assert tick["currency"] == "USD"
    assert tick["price"] > 0
    assert tick["timestamp"] > 0
    assert tick["dayVolume"] >= 0


@pytest.mark.parametrize("synthetic, expected", [(True, "SYNTH-BTC-USD"), (False, "BTC-USD")])
def test_tick_check_requires_recent_records_in_the_configured_mode(synthetic, expected):
    with patch.object(collector, "InfluxDBClient") as client_type:
        query_api = client_type.return_value.__enter__.return_value.query_api.return_value
        query_api.query.return_value = []
        assert collector.check_ticks("url", "token", "org", "bucket", ["BTC-USD"], synthetic) == 1
        query = query_api.query.call_args.args[0]
        assert "range(start: -30s)" in query
        assert 'r._measurement == "ticker_ingest" and r._field == "count"' in query
        assert 'set: ["' + expected + '"]' in query
        table = MagicMock()
        table.records = [object()]
        query_api.query.return_value = [table]
        assert collector.check_ticks("url", "token", "org", "bucket", ["BTC-USD"], synthetic) == 0


def test_check_failure_exits_without_starting_a_collector():
    with patch.object(collector, "check_ticks", side_effect=RuntimeError("Unauthorized")), \
            patch.object(collector, "InfluxDBSink") as sink, \
            patch.object(collector, "YLiveTicker") as client:
        assert collector.main(["--check", "--synthetic"]) == 1
        sink.assert_not_called()
        client.assert_not_called()
