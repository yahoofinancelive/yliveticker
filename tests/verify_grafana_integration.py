"""Check the running demo stack through Grafana's actual datasource and panels.

Run manually or in the Compose smoke workflow; no third-party modules required.
"""

import base64
import argparse
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def grafana_request(path, payload=None, method=None):
    url = os.getenv("GRAFANA_URL", "http://localhost:3000") + path
    password = os.getenv("GRAFANA_PASSWORD", "admin")
    credentials = base64.b64encode(("admin:" + password).encode()).decode()
    request = Request(url, headers={
        "Authorization": "Basic " + credentials,
        "Content-Type": "application/json",
    }, data=None if payload is None else json.dumps(payload).encode(), method=method)
    try:
        with urlopen(request, timeout=10) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError("Grafana HTTP %s: %s" % (exc.code, exc.read().decode())) from exc


def verify_once():
    datasource = grafana_request("/api/datasources/uid/yliveticker-influxdb")
    assert datasource["type"] == "influxdb", "InfluxDB datasource is not provisioned"
    health = grafana_request("/api/datasources/uid/yliveticker-influxdb/health")
    assert health["status"] == "OK", health
    dashboard = grafana_request("/api/dashboards/uid/yliveticker-dashboard")["dashboard"]
    assert dashboard["refresh"] == "5s"
    assert dashboard["templating"]["list"][0]["includeAll"]
    assert dashboard["annotations"]["list"] == [], "No internal Grafana datasource is needed"
    home = grafana_request("/api/dashboards/home")
    assert (home.get("dashboard", {}).get("uid") == dashboard["uid"]
            or dashboard["uid"] in home.get("redirectUri", "")), "Ticker dashboard is not the home page"
    found = grafana_request("/api/search?query=yliveticker")
    assert any(item["uid"] == dashboard["uid"] for item in found), "Dashboard cannot be found by project name"

    queries = [("Symbols", dashboard["templating"]["list"][0]["query"])]
    for panel in dashboard["panels"]:
        for target in panel.get("targets", []):
            assert panel["datasource"]["uid"] == datasource["uid"], panel["title"]
            assert target["datasource"]["uid"] == datasource["uid"], panel["title"]
            queries.append((panel["title"], target["query"]))
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
        elif title == "Active feed (last 30 seconds)":
            values = [value for frame in frames for column in frame["data"]["values"] for value in column]
            assert 1 in values, values
        elif title == "Stored ticks (selected range)":
            assert any(value > 0 for frame in frames for column in frame["data"]["values"]
                       for value in column if isinstance(value, (int, float)))
        else:
            fields = [field for frame in frames for field in frame["schema"]["fields"]
                      if field["type"] == "number"]
            assert fields and all(field.get("labels", {}).get("id", "").startswith("DEMO-")
                                  for field in fields), (title, fields)
        print("PASS:", title)


def seed_legacy():
    """Simulate an older installation whose datasource has a generated UID."""
    deadline = time.monotonic() + 120
    while True:
        try:
            grafana_request("/api/health")
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)
    result = grafana_request("/api/datasources", {
        "name": "InfluxDB", "type": "influxdb", "access": "proxy",
        "url": "http://influxdb:8086", "isDefault": True,
        "jsonData": {"version": "Flux", "organization": "yliveticker", "defaultBucket": "ticker_data"},
        "secureJsonData": {"token": os.getenv("INFLUX_TOKEN", "my-super-secret-auth-token")},
    })
    legacy_uid = result["datasource"]["uid"]
    assert legacy_uid != "yliveticker-influxdb"
    path = Path(__file__).parents[1] / "docker/grafana/dashboards/dashboard.json"
    model = json.loads(path.read_text().replace("yliveticker-influxdb", legacy_uid))
    grafana_request("/api/dashboards/db", {"dashboard": model, "overwrite": True})
    grafana_request("/api/org/preferences", {"homeDashboardUID": model["uid"]}, method="PUT")
    print("PASS: created legacy Grafana database with generated datasource UID", legacy_uid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-legacy", action="store_true")
    if parser.parse_args().seed_legacy:
        seed_legacy()
        return
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
