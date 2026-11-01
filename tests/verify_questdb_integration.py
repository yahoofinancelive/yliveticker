"""Verify the QuestDB timestamp regression against an explicitly configured server."""
import os
import time
from datetime import datetime, timezone

import requests
from yliveticker.sinks.questdb import QuestDBSink


def verify():
    host = os.getenv("QUESTDB_HOST", "localhost")
    port = int(os.getenv("QUESTDB_TCP_PORT", "9009"))
    http_port = int(os.getenv("QUESTDB_HTTP_PORT", "9000"))
    table = "verify_ticks_" + str(time.time_ns())
    msg = dict(id="QUEST_TICKER", price=789.01, dayVolume=20000, timestamp=1600000000123)
    deadline = time.monotonic() + 30
    while True:
        try:
            requests.get("http://{}:{}/exec".format(host, http_port),
                         params={"query": "select 1"}, timeout=2).raise_for_status()
            break
        except requests.RequestException:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.25)
    sink = QuestDBSink(host=host, port=port, table_name=table, batch_size=1)
    try:
        sink.on_ticker(None, msg)
        sink.stop()
        deadline = time.monotonic() + 20
        while True:
            response = requests.get("http://{}:{}/exec".format(host, http_port),
                                    params={"query": "select * from " + table}, timeout=5)
            data = response.json()
            if response.ok and data.get("dataset"):
                columns = [c["name"] for c in data["columns"]]
                row = dict(zip(columns, data["dataset"][0]))
                timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
                assert timestamp == datetime.fromtimestamp(msg["timestamp"] / 1000, timezone.utc), row
                assert row["id"] == msg["id"] and row["price"] == msg["price"], row
                print("PASS: QuestDB persisted the exact 2020 timestamp (not 1970)")
                return
            if time.monotonic() >= deadline:
                raise AssertionError(data)
            time.sleep(.25)
    finally:
        sink.stop()


if __name__ == "__main__":
    verify()
