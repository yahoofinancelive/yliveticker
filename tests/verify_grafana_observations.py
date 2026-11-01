"""Check out-of-order heartbeats through real InfluxDB and Grafana, in a test stack.

Run after stopping the synthetic collector so its heartbeats cannot replace the fixture.
"""

import os
import time

from verify_grafana_integration import grafana_request
from yliveticker.collector_monitor import CollectorMonitor
from yliveticker.sinks.influxdb import InfluxDBSink


def main():
    if os.getenv("TICKER_SYNTHETIC") != "1" or os.getenv("COMPOSE_PROJECT_NAME") not in (
            "yliveticker-observations", "yliveticker-smoke"):
        raise SystemExit("This fixture may only write to the named synthetic test stacks")
    sink = InfluxDBSink(os.getenv("INFLUX_URL", "http://localhost:8086"),
                        os.getenv("INFLUX_TOKEN", "my-super-secret-auth-token"),
                        "yliveticker", "ticker_data", batch_size=1)
    try:
        monitor = CollectorMonitor(sink, ["NVDA"], synthetic=True)
        now = time.time()
        for stamp, session in ((now - 2, 4), (now - 214800, 1)):
            monitor.on_ticker(None, dict(id="SYNTH-NVDA", price=337.8, timestamp=int(stamp * 1000),
                                        currency="USD", marketHours=session))
        sink.write_status(monitor.snapshot()["symbols"])
        dashboard = grafana_request("/api/dashboards/uid/yliveticker-dashboard")["dashboard"]
        table = next(p for p in dashboard["panels"] if p["id"] == 2)
        query = table["targets"][0]["query"].replace("${symbol:regex}", "SYNTH-NVDA.*")
        stamp = int(time.time() * 1000)
        result = grafana_request("/api/ds/query", {
            "from": str(stamp - 3600000), "to": str(stamp), "queries": [{
                "refId": "A", "datasource": {"type": "influxdb", "uid": "yliveticker-influxdb"},
                "query": query, "intervalMs": 5000, "maxDataPoints": 1000,
            }],
        })["results"]["A"]
        assert not result.get("error"), result
        rows = []
        for frame in result.get("frames", []):
            fields = [f["name"] for f in frame["schema"]["fields"]]
            rows.extend(dict(zip(fields, row)) for row in zip(*frame["data"]["values"]))
        assert len(rows) == 1, rows
        row = rows[0]
        assert row["Session"] == "Overnight (Yahoo)", row
        assert row["Status"] == "Receiving older snapshots", row
        assert 0 <= row["Newest quote age"] < 30, row
        assert row["Received since restart"] == row["Written since restart"] == 2, row
        print("PASS: actual Grafana table preserves fresh overnight age after an old snapshot; counters are scoped to restart")
    finally:
        sink.stop()


if __name__ == "__main__":
    main()
