"""Regressions for mixed-session, out-of-order quotes and dashboard presentation."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from yliveticker.collector_monitor import CollectorMonitor
from yliveticker.dashboard import build_dashboard
from yliveticker.instruments import dashboard_symbols, instrument
from yliveticker.observability import new_observation, quote_session, record_observation, symbol_status
from yliveticker.sinks.influxdb import InfluxDBSink


def test_friday_snapshot_cannot_replace_monday_overnight_freshness():
    now = datetime(2026, 10, 12, 7, 40, tzinfo=timezone.utc).timestamp()
    observation = new_observation()
    record_observation(observation, dict(timestamp=(now - 5) * 1000, marketHours=4), now - 3)
    record_observation(observation, dict(timestamp=(now - 214800) * 1000, marketHours=1), now - 1)
    state = symbol_status("AAPL", observation, {}, now=now)
    assert state["quote_age"] == 5
    assert state["receipt_age"] == 1
    assert state["received"] == 2
    assert state["session"] == "Overnight (Yahoo)"
    assert state["state"] == "Receiving older snapshots"
    assert state["schedule"] == "Outside regular hours (estimated)"
    assert observation["older_quote_count"] == 1
    record_observation(observation, dict(timestamp=now * 1000, marketHours=4), now)
    assert symbol_status("AAPL", observation, {}, now=now)["state"] == "Receiving"


def test_monitor_fallback_also_keeps_newest_quote():
    sink = MagicMock()
    sink.diagnostics = {}
    monitor = CollectorMonitor(sink, ["AAPL"])
    for stamp, session in ((3000, 4), (1000, 1), (2000, 2)):
        monitor.on_ticker(None, dict(id="AAPL", timestamp=stamp, marketHours=session))
    state = monitor.snapshot()["symbols"][0]
    assert state["received"] == 3
    assert state["session"] == "Overnight (Yahoo)"
    assert monitor._observations["AAPL"]["last_quote_time"] == 3
    assert sink.on_ticker.call_count == 3  # Historical messages still reach storage.


@pytest.mark.parametrize("code, expected", [(None, "Not reported"), (0, "Pre-market / unspecified"),
                         (1, "Regular (Yahoo)"), (2, "Post-market (Yahoo)"),
                         (3, "Extended (Yahoo)"), (4, "Overnight (Yahoo)"),
                         (99, "Unknown Yahoo code: 99")])
def test_session_labels_do_not_guess_unknown_values(code, expected):
    assert quote_session(code) == expected


def test_japan_holiday_uses_exchange_date_and_limited_calendar_coverage():
    # 10:00 JST on Sports Day: the weekday clock alone would say open.
    holiday = datetime(2026, 10, 12, 1, tzinfo=timezone.utc)
    toyota = instrument("7203.T")
    assert toyota.holiday(holiday) == "Sports Day"
    assert not toyota.expected_open(holiday)
    state = symbol_status("7203.T", {}, {}, now=holiday.timestamp())
    assert state["state"] == "Market holiday: Sports Day"
    assert state["schedule"] == "Holiday: Sports Day"
    assert toyota.expected_open(datetime(2026, 10, 13, 1, tzinfo=timezone.utc))
    assert toyota.holiday(datetime(2027, 10, 12, 1, tzinfo=timezone.utc)) is None
    assert instrument("0700.HK").holiday(holiday) is None


def test_regional_order_includes_silent_and_custom_symbols():
    symbols = ["AAPL", "BTC-USD", "D05.SI", "FPH.NZ", "SAP.DE", "7203.T", "CUSTOM"]
    expected = ["FPH.NZ", "7203.T", "D05.SI", "SAP.DE", "AAPL", "BTC-USD", "CUSTOM"]
    assert dashboard_symbols(symbols) == expected
    dashboard = build_dashboard(symbols)
    query = dashboard["templating"]["list"][0]["query"]
    assert [query.index('{_value: "' + s + '"}') for s in expected] == sorted(
        query.index('{_value: "' + s + '"}') for s in expected)
    assert all(v["sort"] == 0 for v in dashboard["templating"]["list"])
    table = next(p for p in dashboard["panels"] if p["id"] == 2)
    for label in ("Received since restart", "Written since restart", "Newest quote age", "Session", "Regular schedule"):
        assert label in table["transformations"][0]["options"]["indexByName"]


def test_status_and_tick_storage_preserve_reported_session():
    with patch("influxdb_client.InfluxDBClient"):
        sink = InfluxDBSink("url", "token", "org", "bucket")
        try:
            sink.write_batch([dict(id="AAPL", timestamp=1791790800000, price=337.8, marketHours=4)])
            point = sink.write_api.write.call_args.kwargs["record"][0]
            assert point._fields["market_hours"] == 4
            state = symbol_status("AAPL", {}, {})
            state["connection"] = "connected"
            sink.write_status([state])
            fields = sink.write_api.write.call_args.kwargs["record"][0]._fields
            assert fields["session"] == "Not observed"
            assert "schedule" in fields
        finally:
            sink.stop()
