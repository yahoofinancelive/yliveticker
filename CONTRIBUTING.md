# Contributing

Bug reports, downstream examples and focused contributions are welcome.
Include Python/package versions, symbols, observation time and redacted logs.
Never share tokens or database credentials. Silence from an unofficial feed is
not by itself evidence that a symbol is unsupported.

```bash
python -m pip install -e '.[all]' pytest requests flake8
python -m pytest tests --doctest-modules
python -m yliveticker.dashboard --check --output docker/grafana/dashboards/dashboard.json
```

Dashboard source: `yliveticker/dashboard.py`, `dashboard_template.json` and
`instruments.py`. Regenerate the checked-in dashboard after changes. Both the
collector and Compose generator read `TICKER_SYMBOLS`; do not maintain another
watchlist or currency map. Instrument hours are approximate, not holiday calendars.

Bindings are generated with **protoc 3.20.3** from the repository root:

```bash
protoc --python_out=. yliveticker/yaticker.proto
```

Do not regenerate using a newer compiler without updating the minimum runtime
and compatibility matrix. Test the smallest supported Python too.

CI tests the local protocol transport and database mocks, plus real InfluxDB and
Grafana with explicitly synthetic data. The existing Python Playwright smoke test
opens an empty dashboard, starts the collector, verifies automatic updates, silent
symbols, filtering and legends. Run it only against an isolated test stack.
It is intentionally not part of ordinary pytest discovery.

For a bounded real-feed observation (network access required):

```bash
python examples/live_canary.py --seconds 30
```

The result is a dated observation, not a feed availability promise. See
[product direction](docs/PRODUCT_DIRECTION.md) for limits and measurements.
