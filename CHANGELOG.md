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
  opt-in clearly labeled synthetic mode, readiness checks and collector shutdown flushing.
- Default the Docker quickstart to live Yahoo quotes; check recent mode-specific
  InfluxDB writes for collector health and make the ticker dashboard the home page.
  Use an east-to-west default watchlist spanning thirteen equity markets, crypto,
  FX and commodities; reserve `SYNTH-*` names for deterministic CI data. Use a
  one-hour dashboard range so delayed exchange quotes remain discoverable.
  Preserve Yahoo quote currency in callbacks and InfluxDB, and show it in every
  price and volume chart legend with fallbacks for pre-upgrade stored ticks.
  Migrate Grafana databases with the legacy provisioned dashboard and datasource
  UIDs without deleting ticks. Pin InfluxDB 2.9.1 so volumes created by the old
  `influxdb:latest` remain schema-compatible.
- Update the README, configuration guide, screenshot and integration checks.
- Require Python 3.10+ and protobuf 3.20.3–7.x; regenerate bindings with protoc
  3.20.3 and test runtime majors independently. The old Python 3.7 claim was untested.
- Add runtime subscribe/unsubscribe and a bounded async iterator over the same pool.
- Fix QuestDB millisecond-to-nanosecond conversion and rollback failed PostgreSQL
  transactions before retry. Retain failed sink batches in bounded memory, expose
  counters, reject overflow explicitly and raise on failed shutdown flushes.
- Separate receipt freshness from delayed quote age; expose per-symbol observations,
  connection state and local-only run metrics. Do not infer upstream support from silence.
- Generate collector/dashboard metadata from one registry, include custom silent
  symbols, and apply Symbols selection to volume panels too.
- Rename pandas `volume` to `session_volume`, use UTC indices and bound retention
  to 100,000 points by default (`max_points=None` explicitly disables the bound).
- Document unofficial-feed limitations and evidence-led product direction; add a
  manual live observation workflow separate from deterministic merge checks.

The 100-symbol boundary was observed in live tests, rather than documented by
Yahoo. Closed markets and inactive instruments can still produce no ticks.
`on_ticker(ws, tick)`, `on_error(error)`, `on_close()` and the default blocking
constructor remain supported. Close callbacks refer to individual connections.

Version 0.5.5 is already published; these changes use a new version and must not
replace the existing tag or PyPI files.
