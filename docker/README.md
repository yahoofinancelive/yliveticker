# Yahoo Finance → InfluxDB → Grafana

This local quickstart runs three services: a `yliveticker` collector, InfluxDB 2,
and Grafana with an automatically provisioned datasource and dashboard.
Docker Engine/Desktop with the Compose v2 plugin and an internet connection are
required; no host Python installation or manual datasource setup is needed.

From the repository root:

```bash
docker compose -f docker/docker-compose.yml up --build -d
```

Open [the live dashboard](http://localhost:3000/d/yliveticker-dashboard).
The first build downloads the images and Python dependencies. Once InfluxDB
finishes initialization, the collector subscribes to `BTC-USD`, `ETH-USD` and
`AAPL`. Allow a few seconds for the first ticks. Crypto usually updates outside
stock-market hours. Yahoo's unofficial feed can be delayed or unavailable.

The dashboard provides:

- Latest observed prices and the age of each symbol's last tick.
- A symbol selector and separate price charts for each selected symbol.
- **Cumulative session volume** (`dayVolume`), not interval/candle volume.
- Five-second refresh and UTC timestamps. Prices remain in each symbol's quote
  currency; they are not converted into a common currency.

## Choose symbols

On macOS/Linux, from the repository root:

```bash
TICKER_SYMBOLS="BTC-USD NVDA EURUSD=X" docker compose -f docker/docker-compose.yml up -d
```

On Windows or to keep the setting between runs, put this in `docker/.env`:

```dotenv
TICKER_SYMBOLS=BTC-USD NVDA EURUSD=X
```

Then run the original Compose command again. Previously stored symbols remain
available in the dashboard selector for one day; select just the symbols you
want to view. Closed markets naturally show older ticks or no ticks in range.

Live watchlists are deduplicated and pooled automatically, with at most 100
symbols per Yahoo connection. The default limit is four connections (400 unique
symbols); larger lists fail explicitly before subscribing. Set
`TICKER_MAX_CONNECTIONS=6` in `docker/.env` to allow up to 600 symbols. The host
collector accepts the same environment setting or `--max-connections 6`.
The 100-symbol boundary was observed in live tests of Yahoo's unofficial feed;
pooling cannot guarantee updates for an inactive instrument or closed market.

## Demo mode (synthetic data)

To check the pipeline without depending on Yahoo or market hours:

```bash
TICKER_DEMO=1 docker compose -f docker/docker-compose.yml up --build -d
```

Alternatively set `TICKER_DEMO=1` in `docker/.env`. The collector emits
**synthetic** prices under `DEMO-*` symbols and logs a demo-mode warning. This
uses the same sink, storage and dashboard as live mode. Set `TICKER_DEMO=0` and
run Compose again to return to Yahoo. Stored demo series remain visible until
they age out of the selected time range; select the live symbols explicitly.

## Logs, shutdown and data

Run these commands from the repository root:

```bash
# Startup status and collector errors
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs -f collector

# Stop; retain ticks and Grafana settings in named volumes
docker compose -f docker/docker-compose.yml down

# Delete all quickstart data and settings (destructive reset)
docker compose -f docker/docker-compose.yml down -v
```

SIGINT/SIGTERM stops the collector and flushes buffered ticks. The example uses
one-second batches. Compose allows 30 seconds for pooled connections to close
and the sink to flush before forcing termination. The existing sink logs write failures and does not replay
failed batches; this demo is not a durable market-data queue.

## Local settings

Both published ports bind to `127.0.0.1`. Grafana allows anonymous **viewing**;
log in with `admin` / `admin` to edit. InfluxDB is at
[localhost:8086](http://localhost:8086), with `admin` / `adminpassword`.
The included credentials are development defaults.

Before the first startup, optionally set these in `docker/.env`:

```dotenv
GRAFANA_PASSWORD=choose-a-local-admin-password
INFLUX_PASSWORD=choose-a-local-influx-password
INFLUX_TOKEN=choose-a-local-influx-token
```

The InfluxDB token is shared by the collector and provisioned Grafana datasource.
Initialization values only apply to a new InfluxDB volume; changing `.env`
after setup does not rotate its existing credentials. Likewise Grafana's admin
password environment setting initializes a new Grafana database. Preserve your
data and change existing credentials in the relevant service, or use the
explicit destructive reset above to initialize a fresh demo.

This stack intentionally stays on InfluxDB **2.x** because the sink and
queries use its API and Flux. Do not change the image to `influxdb:latest` or
InfluxDB 3. Grafana provisioning files are mounted read-only; commit dashboard
changes to `grafana/dashboards/dashboard.json` to keep them across restarts.

## Use a host Python collector

For development, run just the database and dashboard, then install the local
package and run the example from the repository root:

```bash
docker compose -f docker/docker-compose.yml up -d influxdb grafana
python -m pip install -e '.[influxdb]'
python examples/tsdb_example.py BTC-USD AAPL
```

If the full stack was already running, stop its collector first with
`docker compose -f docker/docker-compose.yml stop collector` to avoid duplicate
writers. The example also accepts `--demo`. Host-side configuration uses
`INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG` and `INFLUX_BUCKET`; pass any custom
credentials from `.env` to the host process yourself. The supplied dashboard
queries the default `ticker_data` bucket.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Empty charts | Check collector logs, choose a crypto symbol, and allow a few seconds. Try demo mode to isolate Yahoo availability. |
| Only old/demo symbols | Select the desired symbols, then refresh the dashboard or widen the time range. |
| InfluxDB unhealthy / unauthorized | Check token consistency and whether an existing volume was initialized with different credentials. |
| Port already in use | Stop the conflicting local service or change the host-side port in Compose. |
| Build or startup fails | Confirm Docker is running and `docker compose version` works; inspect `docker compose -f docker/docker-compose.yml logs`. |

## Integration check

CI starts the actual Compose stack with synthetic data and verifies InfluxDB
writes, Grafana provisioning, symbol discovery and every dashboard panel query.
To run the same check locally, after starting demo mode:

```bash
python tests/verify_grafana_integration.py
```

This check uses the Python standard library and the default local credentials.
Set `GRAFANA_PASSWORD` if you configured a different admin password. It does not
check Yahoo connectivity; synthetic data is deliberately independent of the
upstream feed.
