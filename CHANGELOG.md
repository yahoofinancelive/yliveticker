# Changelog

## 0.5.6 (prepared for release)

- Automatically distribute watchlists across Yahoo WebSocket connections, with
  no more than 100 unique symbols per socket and four sockets by default.
  Deduplicate symbols in order and reject oversized watchlists before connecting;
  configure `symbols_per_connection` and `max_connections` to adjust the pool.
- Reconnect and resubscribe each bucket independently, including clean server
  closes. Keep application callbacks serialized through a bounded queue and
  expose per-connection activity through `diagnostics`.
- Add `start=False` and `run()` for controllable startup; make `close()` stop the
  entire pool. Fix the CLI's ability to stop a running client and expose pool flags.
- Add the Yahoo → InfluxDB 2 → Grafana Compose quickstart, provisioned dashboard,
  clearly labeled synthetic demo, readiness checks and collector shutdown flushing.
- Default the Docker quickstart to clearly labeled synthetic data; check recent
  InfluxDB writes for collector health and make the ticker dashboard the home page.
  Migrate Grafana databases with the legacy provisioned dashboard and datasource
  UIDs without deleting ticks.
- Update the README, configuration guide, screenshot and integration checks.
- Require `websocket-client>=1.6.0` and Python 3.7 or newer for the connection API.

The 100-symbol boundary was observed in live tests, rather than documented by
Yahoo. Closed markets and inactive instruments can still produce no ticks.
`on_ticker(ws, tick)`, `on_error(error)`, `on_close()` and the default blocking
constructor remain supported. Close callbacks refer to individual connections.

Version 0.5.5 is already published; these changes use a new version and must not
replace the existing tag or PyPI files.
