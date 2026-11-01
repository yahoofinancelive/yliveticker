"""Check the running quickstart through Grafana's actual datasource and panels.

Run manually or in the Compose smoke workflow; no third-party modules required.
"""

import base64
import argparse
import json
import os
import time
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
    response = grafana_request("/api/dashboards/uid/yliveticker-dashboard")
    dashboard = response["dashboard"]
    assert dashboard["title"] == "yliveticker · Yahoo Finance", dashboard["title"]
    assert response["meta"]["provisioned"], "Ticker dashboard is not file-provisioned"
    assert dashboard["refresh"] == "5s"
    assert dashboard["timezone"] == "browser"
    assert dashboard["time"]["from"] == "now-1h", "Default range must include delayed exchanges"
    assert dashboard["templating"]["list"][0]["includeAll"]
    symbol_variable = dashboard["templating"]["list"][0]
    volume_variable = dashboard["templating"]["list"][1]
    assert '{_value: "SYNTH-NVDA"}' in symbol_variable["query"]
    assert "SYNTH-NVDA · Synthetic test · United States" in symbol_variable["query"]
    assert "14:30–21:00 UTC" in symbol_variable["query"]
    assert "13:30–20:00 UTC" in symbol_variable["query"]
    assert "${symbol:regex}" in volume_variable["query"]
    assert symbol_variable["regex"] == volume_variable["regex"]
    assert "| Yahoo symbol | Market / instrument |" not in dashboard["panels"][0]["options"]["content"]
    assert not any(panel.get("title") == "Latest price" for panel in dashboard["panels"])
    assert not any(panel.get("id") == 1 for panel in dashboard["panels"])
    price_panel = next(panel for panel in dashboard["panels"] if panel["id"] == 3)
    volume_panel = next(panel for panel in dashboard["panels"] if panel["id"] == 4)
    age_panel = next(panel for panel in dashboard["panels"] if panel["id"] == 2)
    assert "${symbol:text}" in price_panel["description"]
    assert "${volume_symbol:text}" in volume_panel["description"]
    assert price_panel["title"] == "${symbol:raw}: price"
    assert volume_panel["title"].startswith("${volume_symbol:raw}:")
    assert price_panel["fieldConfig"]["defaults"]["displayName"].endswith(
        "${__field.labels.id} · ${__field.labels.currency}"
    )
    assert volume_panel["fieldConfig"]["defaults"]["displayName"].endswith(
        "${__field.labels.id} · ${__field.labels.currency}"
    )
    assert age_panel["type"] == "table"
    assert age_panel["gridPos"] == {"h": 8, "w": 24, "x": 0, "y": 15}
    assert "sort(columns: [\"_order\"])" in age_panel["targets"][0]["query"]
    assert dashboard["annotations"]["list"] == [], "No internal Grafana datasource is needed"
    home = grafana_request("/api/dashboards/home")
    assert (home.get("dashboard", {}).get("uid") == dashboard["uid"]
            or dashboard["uid"] in home.get("redirectUri", "")), "Ticker dashboard is not the home page"
    found = grafana_request("/api/search?query=yliveticker")
    assert any(item["uid"] == dashboard["uid"] for item in found), "Dashboard cannot be found by project name"

    queries = [(variable["label"], variable["query"])
               for variable in dashboard["templating"]["list"]]
    for panel in dashboard["panels"]:
        for target in panel.get("targets", []):
            assert panel["datasource"]["uid"] == datasource["uid"], panel["title"]
            assert target["datasource"]["uid"] == datasource["uid"], panel["title"]
            queries.append((panel["title"], target["query"]))
    for title, query in queries:
        # Check the stored panel queries, including Flux compilation via Grafana.
        query = query.replace("${symbol:regex}", "SYNTH-.*")
        query = query.replace("${volume_symbol:regex}", "SYNTH-.*")
        now = int(time.time() * 1000)
        result = grafana_request("/api/ds/query", {
            "from": str(now - 3600000), "to": str(now),
            "queries": [{
                "refId": "A", "datasource": {"type": "influxdb", "uid": datasource["uid"]},
                "query": query, "intervalMs": 5000, "maxDataPoints": 1000,
            }],
        })["results"]["A"]
        assert not result.get("error"), (title, result)
        frames = result.get("frames", [])
        assert frames and any(any(values) for frame in frames for values in frame["data"]["values"]), (
            title, "No data returned; run the collector with TICKER_SYNTHETIC=1",
        )
        if title in ("Symbols", "Volume symbols"):
            values = [value for frame in frames for column in frame["data"]["values"] for value in column]
            assert any(isinstance(value, str) and value.startswith("SYNTH-") for value in values), values
        elif title == "Active feed (last 30 seconds)":
            values = [value for frame in frames for column in frame["data"]["values"] for value in column]
            assert 1 in values, values
        elif title == "Stored ticks (selected range)":
            assert any(value > 0 for frame in frames for column in frame["data"]["values"]
                       for value in column if isinstance(value, (int, float)))
        elif title in ("Received ticks/min (last 60s)", "Received ticks per minute"):
            assert any(value > 0 for frame in frames for column in frame["data"]["values"]
                       for value in column if isinstance(value, (int, float))), (title, frames)
        elif title == "Time since last tick":
            values = [value for frame in frames for column in frame["data"]["values"]
                      for value in column]
            assert any(isinstance(value, str) and value.startswith("SYNTH-") for value in values)
            assert any(isinstance(value, (int, float)) and value >= 0 for value in values)
        else:
            fields = [field for frame in frames for field in frame["schema"]["fields"]
                      if field["type"] == "number"]
            assert fields and all(field.get("labels", {}).get("id", "").startswith("SYNTH-")
                                  for field in fields), (title, fields)
            assert all(field.get("labels", {}).get("currency") not in (None, "", "N/A")
                       for field in fields), (title, fields)
            assert any(field.get("labels", {}).get("id") == "SYNTH-BTC-USD"
                       and field.get("labels", {}).get("currency") == "USD"
                       for field in fields), (title, fields)
        print("PASS:", title)

    # A silent selected symbol must not leak another ticker's available volume.
    query = volume_variable["query"].replace("${symbol:regex}", "SYNTH-NVDA.*")
    now = int(time.time() * 1000)
    result = grafana_request("/api/ds/query", {
        "from": str(now - 3600000), "to": str(now), "queries": [{
            "refId": "A", "datasource": {"type": "influxdb", "uid": datasource["uid"]},
            "query": query, "intervalMs": 5000, "maxDataPoints": 1000,
        }],
    })["results"]["A"]
    assert not result.get("error"), result
    values = [value for frame in result.get("frames", []) for column in frame["data"]["values"] for value in column]
    assert not any(isinstance(v, str) and "SYNTH-BTC-USD" in v for v in values), values
    print("PASS: volume variable respects the selected silent symbol")


def verify_legacy():
    """Confirm CI started the exact dashboard/provisioning layout being upgraded."""
    deadline = time.monotonic() + 120
    while True:
        try:
            grafana_request("/api/health")
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)
    datasources = grafana_request("/api/datasources")
    legacy = next(item for item in datasources if item["name"] == "InfluxDB")
    legacy_uid = legacy["uid"]
    assert legacy_uid != "yliveticker-influxdb"
    response = grafana_request("/api/dashboards/uid/yliveticker-dashboard")
    dashboard = response["dashboard"]
    assert dashboard["title"] == "Yahoo Finance Live Ticker"
    assert [panel["title"] for panel in dashboard["panels"]] == ["Price", "Volume"]
    assert all(panel["datasource"]["uid"] == "InfluxDB" for panel in dashboard["panels"])
    assert response["meta"]["provisioned"], "Legacy dashboard must carry provisioning metadata"
    print("PASS: exact legacy provisioned dashboard and generated datasource are present", legacy_uid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-legacy", action="store_true")
    if parser.parse_args().verify_legacy:
        verify_legacy()
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
