"""Verify PostgreSQL rollback/retry against an explicitly configured server."""
import os
import time
from datetime import datetime, timezone
from unittest.mock import patch

from yliveticker.sinks.timescaledb import TimescaleDBSink


def verify():
    dsn = os.getenv("TIMESCALE_DSN", "dbname=yliveticker user=yliveticker password=yliveticker host=localhost")
    table = "verify_ticks_" + str(time.time_ns())
    sink = TimescaleDBSink(dsn=dsn, table_name=table, batch_size=1, retry_interval=60)
    msg = dict(id="TEST_TICKER", price=456.78, dayVolume=10000, timestamp=1600000000123)

    def aborted_transaction(cur, sql, values):
        cur.execute("SELECT 1 / 0")  # A real failed transaction, not a mock exception.

    try:
        with patch("yliveticker.sinks.timescaledb.execute_values", side_effect=aborted_transaction):
            sink.on_ticker(None, msg)
        assert sink.diagnostics["pending"] == 1
        assert sink.diagnostics["write_failures"] == 1
        sink._retry_at = 0
        assert sink.flush()
        assert sink.diagnostics["written"] == 1
        with sink.conn.cursor() as cursor:
            cursor.execute("SELECT time, symbol, price, volume FROM " + table)
            row = cursor.fetchone()
        assert row == (datetime.fromtimestamp(msg["timestamp"] / 1000, timezone.utc),
                       msg["id"], msg["price"], float(msg["dayVolume"])), row
        print("PASS: PostgreSQL recovered from an aborted transaction and persisted the retried batch")
    finally:
        sink.stop()


if __name__ == "__main__":
    verify()
