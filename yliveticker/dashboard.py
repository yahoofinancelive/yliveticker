"""Generate the provisioned dashboard from the collector's instrument registry."""

import argparse
import json
import os
from pathlib import Path

from .instruments import DEFAULT_SYMBOLS, dashboard_symbols, instrument


def _literal(value):
    return json.dumps(value, ensure_ascii=False)


def build_dashboard(symbols=DEFAULT_SYMBOLS, synthetic=False):
    symbols = dashboard_symbols(symbols)
    ids = ["SYNTH-" + s if synthetic else s for s in symbols]
    instruments = [instrument(s) for s in ids]
    dashboard = json.loads(Path(__file__).with_name("dashboard_template.json").read_text())

    def mapping(name, getter, fallback):
        return name + " = (id) =>\n  " + "\n  else ".join(
            "if id == " + _literal(i.symbol) + " then " + _literal(getter(i)) for i in instruments
        ) + "\n  else " + fallback + "\n\n"

    labels = mapping("symbolLabel", lambda i: i.label, "id")
    ordering = mapping("symbolOrder", lambda i: ids.index(i.symbol), "9999")
    metadata = labels + mapping("sessionInfo", lambda i: i.description(),
                                'id + " · Metadata unavailable"')
    currencies = mapping("defaultCurrency", lambda i: i.currency, '"N/A"')
    currencies += 'currencyLabel = (r) => if exists r.currency and r.currency != "" then r.currency else defaultCurrency(id: r.id)\n\n'
    selector = '  |> filter(fn: (r) => symbolLabel(id: r.id) =~ /^${symbol:regex}$/)\n'
    configured = '  |> filter(fn: (r) => contains(value: r.id, set: ' + _literal(ids) + '))\n'
    variables = dashboard["templating"]["list"]
    variables[0]["query"] = 'import "array"\n\n' + metadata + ordering + 'array.from(rows: [' + ", ".join(
        '{_value: ' + _literal(s) + '}' for s in ids) + '])\n' + (
        '  |> map(fn: (r) => ({_order: symbolOrder(id: r._value), _value: symbolLabel(id: r._value) + "|" + sessionInfo(id: r._value)}))\n'
        '  |> sort(columns: ["_order"])\n  |> keep(columns: ["_value"])')
    variables[1]["query"] = metadata + ordering + '''from(bucket: "ticker_data")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "ticker" and r._field == "volume_available")
''' + configured + selector + '''  |> group(columns: ["id"])
  |> last()
  |> filter(fn: (r) => r._value == 1)
  |> map(fn: (r) => ({_order: symbolOrder(id: r.id), _value: symbolLabel(id: r.id) + "|" + sessionInfo(id: r.id)}))
  |> group()
  |> sort(columns: ["_order"])
  |> keep(columns: ["_value"])'''
    for variable in variables:
        variable["definition"] = variable["query"]
        variable["sort"] = 0
    for panel in dashboard["panels"]:
        for target in panel.get("targets", []):
            query = target["query"]
            if panel["id"] in (3, 4):
                target["query"] = labels + currencies + query
                if panel["id"] == 4:
                    target["query"] = target["query"].replace(
                        '  |> filter(fn: (r) => r._field == "volume"',
                        selector + '  |> filter(fn: (r) => r._field == "volume"')
            elif panel["id"] != 2:
                query = query.replace('  |> group()', configured + selector + '  |> group()')
                if panel["id"] == 6:
                    query = query.replace('== "ticker" and r._field == "price"',
                                          '== "ticker_ingest" and r._field == "count"')
                    panel["description"] = "Recently persisted receipts, not quote timestamps. One active symbol does not establish coverage of the other symbols. See the per-symbol table."
                target["query"] = labels + query
        if panel["id"] == 5:
            panel["options"]["content"] = (
                "Ticks are stored in **InfluxDB** · bucket `ticker_data`. "
                "**Unofficial Yahoo WebSocket feed: no availability, completeness or timeliness promises.** "
                "Charts run east to west: **Asia-Pacific → Europe/Middle East/Africa → Americas → Global**. "
                "Select symbols above; chart info bubbles contain country, currency and UTC regular hours. "
                "Table counters reset on collector restart; charts retain stored history. "
                "Configured silent symbols stay visible. `SYNTH-*` is opt-in testing only. "
                "[Quickstart and limitations](https://github.com/yahoofinancelive/yliveticker/blob/main/docker/README.md).")
        if panel["id"] == 2:
            panel["description"] = (
                "Receipt age is time since any message arrived. Newest quote age uses the greatest Yahoo timestamp "
                "seen in this collector run; older snapshots never move it backward. Session belongs to that newest quote, "
                "not necessarily the last arriving message. Yahoo can send overnight quotes while regular markets are closed. "
                "All configured symbols appear, including never-seen symbols. Status is observational; regular hours are estimates, "
                "not proof of Yahoo support. Verified JPX cash-market holidays cover 2026 only; other calendars are not covered. "
                "A stale heartbeat means collector/storage status is unknown. Received/Written count messages since restart, "
                "not unique trades or the selected chart range. Charts retain data from previous runs. No availability promises.")
            rows = [('{id: ' + _literal(s) + ', _time: time(v: 0), state: "Not observed", '
                     'receipt_age: -1.0, quote_age: -1.0, received: 0, written: 0, connection: "Unknown", '
                     'session: "Not observed", schedule: "Unknown"}') for s in ids]
            panel["targets"][0]["query"] = 'import "date"\nimport "array"\n\n' + labels + ordering + (
                'defaults = array.from(rows: [' + ', '.join(rows) + '])\n'
                'observed = from(bucket: "ticker_data")\n'
                '  |> range(start: -1m)\n'
                '  |> filter(fn: (r) => r._measurement == "ticker_status")\n' + configured +
                '  |> group(columns: ["id", "_field"])\n'
                '  |> last()\n'
                '  |> map(fn: (r) => ({r with _value: string(v: r._value)}))\n'
                '  |> group(columns: ["id"])\n'
                '  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")\n'
                '  |> map(fn: (r) => ({id: r.id, _time: r._time, state: r.state, connection: r.connection, session: if exists r.session then r.session else "Not reported", schedule: if exists r.schedule then r.schedule else "Unknown", receipt_age: float(v: r.receipt_age), quote_age: float(v: r.quote_age), received: int(v: r.received), written: int(v: r.written)}))\n'
                'union(tables: [defaults, observed])\n'
                '  |> group(columns: ["id"])\n'
                '  |> sort(columns: ["_time"])\n'
                '  |> tail(n: 1)\n' + selector +
                '  |> map(fn: (r) => ({_order: symbolOrder(id: r.id), Symbol: symbolLabel(id: r.id), Status: if r._time < date.sub(d: 20s, from: now()) then "Collector/storage status unknown" else r.state, Connection: if r._time < date.sub(d: 20s, from: now()) then "Unknown" else r.connection, Session: r.session, "Regular schedule": r.schedule, "Receipt age": if r.receipt_age < 0.0 then -1.0 else r.receipt_age + float(v: int(v: now()) - int(v: r._time)) / 1000000000.0, "Newest quote age": if r.quote_age < 0.0 then -1.0 else r.quote_age + float(v: int(v: now()) - int(v: r._time)) / 1000000000.0, "Received since restart": r.received, "Written since restart": r.written}))\n'
                '  |> group()\n  |> sort(columns: ["_order"])\n  |> drop(columns: ["_order"])')
            panel["transformations"] = [{"id": "organize", "options": {"indexByName": {
                "Symbol": 0, "Status": 1, "Session": 2, "Regular schedule": 3, "Receipt age": 4,
                "Newest quote age": 5, "Received since restart": 6, "Written since restart": 7, "Connection": 8}}}]
            panel["fieldConfig"] = {"defaults": {}, "overrides": [
                {"matcher": {"id": "byName", "options": name}, "properties": [
                    {"id": "unit", "value": "s"}, {"id": "decimals", "value": 1},
                    {"id": "mappings", "value": [{"type": "value", "options": {"-1": {"text": "Not observed"}}}]}]}
                for name in ("Receipt age", "Newest quote age")]}
            panel["fieldConfig"]["overrides"].extend(
                {"matcher": {"id": "byName", "options": name}, "properties": [
                    {"id": "custom.width", "value": width}]}
                for name, width in (("Symbol", 230), ("Status", 230), ("Session", 160), ("Regular schedule", 260),
                                    ("Receipt age", 110), ("Newest quote age", 145),
                                    ("Received since restart", 180), ("Written since restart", 175), ("Connection", 110)))
    return dashboard


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("symbols", nargs="*")
    args = parser.parse_args()
    symbols = args.symbols or os.getenv("TICKER_SYMBOLS") or DEFAULT_SYMBOLS
    content = json.dumps(build_dashboard(symbols, os.getenv("TICKER_SYNTHETIC") == "1"), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if args.output.read_text() != content:
            raise SystemExit("Dashboard is stale: regenerate with python -m yliveticker.dashboard --output " + str(args.output))
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)


if __name__ == "__main__":
    main()
