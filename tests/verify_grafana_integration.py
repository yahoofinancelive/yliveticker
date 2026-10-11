"""Check the running demo stack through Grafana's actual datasource and panels.

Run manually or in the Compose smoke workflow; no third-party modules required.
"""

import base64
import json
import os
import time
from urllib.request import Request, urlopen


def grafana_request(path, payload=None):
    url = os.getenv("GRAFANA_URL", "http://localhost:3000") + path
    password = os.getenv("GRAFANA_PASSWORD", "admin")
    credentials = base64.b64encode(("admin:" + password).encode()).decode()
    request = Request(url, headers={
        "Authorization": "Basic " + credentials,
        "Content-Type": "application/json",
    }, data=None if payload is None else json.dumps(payload).encode())
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def verify_once():
    datasource = grafana_request("/api/datasources/uid/yliveticker-influxdb")
    assert datasource["type"] == "influxdb", "InfluxDB datasource is not provisioned"
    health = grafana_request("/api/datasources/uid/yliveticker-influxdb/health")
    assert health["status"] == "OK", health
    dashboard = grafana_request("/api/dashboards/uid/yliveticker-dashboard")["dashboard"]
    assert dashboard["refresh"] == "5s"

    queries = [("Symbols", dashboard["templating"]["list"][0]["query"])]
    queries.extend((panel["title"], target["query"])
                   for panel in dashboard["panels"] for target in panel.get("targets", []))
    for title, query in queries:
        # Check the stored panel queries, including Flux compilation via Grafana.
        query = query.replace("${symbol:regex}", "DEMO-.*")
        now = int(time.time() * 1000)
        result = grafana_request("/api/ds/query", {
            "from": str(now - 900000), "to": str(now),
            "queries": [{
                "refId": "A", "datasource": {"type": "influxdb", "uid": datasource["uid"]},
                "query": query, "intervalMs": 5000, "maxDataPoints": 1000,
            }],
        })["results"]["A"]
        assert not result.get("error"), (title, result)
        frames = result.get("frames", [])
        assert frames and any(any(values) for frame in frames for values in frame["data"]["values"]), (
            title, "No data returned; run the collector with TICKER_DEMO=1",
        )
        if title == "Symbols":
            values = [value for frame in frames for column in frame["data"]["values"] for value in column]
            assert any(isinstance(value, str) and value.startswith("DEMO-") for value in values), values
        else:
            fields = [field for frame in frames for field in frame["schema"]["fields"]
                      if field["type"] == "number"]
            assert fields and all(field.get("labels", {}).get("id", "").startswith("DEMO-")
                                  for field in fields), (title, fields)
        print("PASS:", title)


def main():
    deadline = time.monotonic() + 120
    while True:
        try:
            verify_once()
            print("SUCCESS: collector → InfluxDB → Grafana panels verified with synthetic data")
            return
        except Exception as exc:
            if time.monotonic() >= deadline:
                raise
            print("Waiting for quickstart:", exc)
            time.sleep(2)


if __name__ == "__main__":
    main()
