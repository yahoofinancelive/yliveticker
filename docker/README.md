# yliveticker → InfluxDB → Grafana

This local quickstart runs three services: a `yliveticker` collector, InfluxDB 2,
and Grafana with an automatically provisioned datasource and dashboard.
Docker Engine/Desktop with the Compose v2 plugin and an internet connection are
required; no host Python installation or manual datasource setup is needed.

From the repository root, on the `feat/pooling-and-grafana` branch until
[PR #22](https://github.com/yahoofinancelive/yliveticker/pull/22) merges:

```bash
docker compose -f docker/docker-compose.yml up --build -d
sh docker/wait-for-stack.sh
```

**Default mode is the live Yahoo feed.** The collector uses a global watchlist
through `yliveticker`, writes received ticks to **InfluxDB 2, bucket
`ticker_data`**, and Grafana queries that bucket. The readiness script waits for a
recent live tick in storage and Grafana readiness; a timeout reports a startup or
upstream-feed failure.
It uses container health checks and works with older Compose v2 versions
without the `--wait` flag. Set `QUICKSTART_TIMEOUT=300` when a longer wait is needed.
The first build downloads images and Python dependencies.

Open **[Grafana at localhost:3000](http://localhost:3000)**. The ticker dashboard
is the home page and appears under **Dashboards → yliveticker**. You can also use
[its permanent URL](http://localhost:3000/d/yliveticker-dashboard).
The top of the dashboard identifies the active feed, distinguishes synthetic
prices from Yahoo quotes, and shows the stored tick count. The symbol selector
uses the displayed time range; the feed status and tick count update even before
symbol discovery completes.

The older `main` Compose file starts only InfluxDB and Grafana, not a collector;
`TICKER_SYNTHETIC=1` has no effect there. Use the PR branch to try this quickstart.

The dashboard provides:

- Active feed and stored tick count, queried from InfluxDB.
- Latest observed prices and the age of each symbol's last tick.
- A symbol selector and separate price charts for each selected symbol.
- **Cumulative session volume** (`dayVolume`), not interval/candle volume.
- Five-second refresh and UTC timestamps. Prices remain in each symbol's quote
  currency; they are not converted into a common currency.

## Choose symbols

The default watchlist is geographically and asset-class diverse:

| Market | Yahoo symbol | Instrument |
| --- | --- | --- |
| Global | `BTC-USD`, `EURUSD=X`, `GC=F` | Bitcoin, EUR/USD, gold futures |
| United States | `AAPL` | Apple |
| Canada | `SHOP.TO` | Shopify |
| Brazil | `VALE3.SA` | Vale |
| Germany | `SAP.DE` | SAP |
| United Kingdom | `HSBA.L` | HSBC |
| South Africa | `NPN.JO` | Naspers |
| India | `RELIANCE.NS` | Reliance Industries |
| Hong Kong | `0700.HK` | Tencent |
| Japan | `7203.T` | Toyota |
| Australia | `BHP.AX` | BHP |

These are real Yahoo instruments, not bundled sample records. Only instruments
whose markets are active will produce new ticks; `BTC-USD` keeps the readiness
check useful around the clock.

On macOS/Linux, from the repository root:

```bash
TICKER_SYMBOLS="BTC-USD NVDA EURUSD=X" docker compose -f docker/docker-compose.yml up -d
```

On Windows or to keep the setting between runs, put this in `docker/.env`:

```dotenv
TICKER_SYMBOLS=BTC-USD NVDA EURUSD=X
```

Then run the original Compose command again. Previously stored symbols remain
available when they have ticks in the selected time range; select just the symbols
you want to view. Closed markets naturally show older ticks or no ticks in range.

Live watchlists are deduplicated and pooled automatically, with at most 100
symbols per Yahoo connection. The default limit is four connections (400 unique
symbols); larger lists fail explicitly before subscribing. Set
`TICKER_MAX_CONNECTIONS=6` in `docker/.env` to allow up to 600 symbols. The host
collector accepts the same environment setting or `--max-connections 6`.
The 100-symbol boundary was observed in live tests of Yahoo's unofficial feed;
pooling cannot guarantee updates for an inactive instrument or closed market.

## Live feed and synthetic pipeline test

The plain command connects to Yahoo. Yahoo's unofficial feed can be delayed or
unavailable, and closed markets can be silent. Crypto usually updates outside
stock-market hours. The collector is healthy only while a configured symbol has
a tick within the last 30 seconds; an unhealthy collector can mean the upstream
feed is silent, even if the process is running.

To test the complete pipeline deterministically without relying on Yahoo or
market hours, explicitly enable the synthetic test feed:

```bash
TICKER_SYNTHETIC=1 docker compose -f docker/docker-compose.yml up --build -d
sh docker/wait-for-stack.sh
```

The collector logs **SYNTHETIC TEST FEED** and emits non-market test prices under
`SYNTH-*` symbols. Both modes use the same InfluxDB sink and bucket. Grafana's volume
stores dashboard settings; market ticks are stored in the InfluxDB volume.

Put `TICKER_SYNTHETIC=0` or `TICKER_SYNTHETIC=1` in `docker/.env` to keep your choice between
commands. A prefix such as `TICKER_SYNTHETIC=0` applies to just that invocation;
running a plain command afterwards uses `.env` or the default live mode.
Stored series remain visible within the selected time range. Select live or
`SYNTH-*` symbols explicitly when switching modes.

## Upgrade an existing quickstart

Pull the current PR branch, rerun `up --build -d`, then run
`sh docker/wait-for-stack.sh`.
Provisioning replaces the old Grafana `InfluxDB` datasource with a stable UID,
replaces the legacy Price/Volume dashboard under the same permanent URL, and
keeps stored InfluxDB ticks. This fixes blank legacy charts, the panel editor's
`e.replace is not a function` error, and existing Grafana databases that fail
with `Datasource provisioning error: data source not found`. Dashboard files
live under `/etc/grafana/dashboards` separately
from Grafana's database and are polled every 30 seconds, including on macOS.
**No volume deletion is required for this upgrade.**

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
and the sink to flush before forcing termination. The existing sink logs write
failures and does not replay failed batches; this quickstart is not a durable market-data queue.

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
explicit destructive reset above to initialize a fresh quickstart.

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
writers. The example also accepts `--synthetic`. Host-side configuration uses
`INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG` and `INFLUX_BUCKET`; pass any custom
credentials from `.env` to the host process yourself. The supplied dashboard
queries the default `ticker_data` bucket.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Empty charts | Confirm this branch has a `collector` service: `docker compose -f docker/docker-compose.yml config --services`. Check `ps` and collector logs. The synthetic test feed should show `SYNTH-*` ticks; allow the first build to finish. |
| Dashboard hard to find | Open `http://localhost:3000/d/yliveticker-dashboard` or **Dashboards → yliveticker**. Existing personal home preferences can override the configured home page. |
| Old Price/Volume page, `-- Grafana --`, or `e.replace is not a function` | Pull this branch and rerun `up --build -d`, then the readiness script. The upgrade replaces the legacy dashboard without requiring `down -v`. |
| Grafana exits with “data source not found” | Pull this branch and rebuild. Its provisioning migrates the earlier generated datasource UID. Keep your volumes. |
| `up -d` stops after creating collector/Grafana | Check `docker compose -f docker/docker-compose.yml ps -a` and the InfluxDB logs. This branch uses InfluxDB 2.9.1 so volumes previously opened by the old `influxdb:latest` remain compatible. |
| Readiness check times out | Inspect `ps`, `logs influxdb grafana collector`, and the collector health check below. Do not assume a running container has written data. |
| Only old/synthetic symbols | Select the desired symbols, then refresh the dashboard or widen the time range. |
| InfluxDB unhealthy / unauthorized | Check token consistency and whether an existing volume was initialized with different credentials. |
| Port already in use | Stop the conflicting local service or change the host-side port in Compose. |
| `unknown flag: --wait` | Omit `--wait` and `--wait-timeout`: run `up --build -d`, followed by `sh docker/wait-for-stack.sh`. |
| Build or startup fails | Confirm Docker is running and `docker compose version` works; inspect `docker compose -f docker/docker-compose.yml logs`. |

## Integration check

CI seeds the exact old file-provisioned Price/Volume dashboard and datasource,
then starts the actual Compose stack with synthetic data and verifies the upgrade,
recent InfluxDB writes, home page,
project-name search, symbol discovery and every dashboard panel query. It also
checks a fresh browser opened before the first tick arrives.
To run the same check locally, after starting the synthetic test feed:

```bash
docker compose -f docker/docker-compose.yml exec collector python examples/tsdb_example.py --check
python tests/verify_grafana_integration.py
```

This check uses the Python standard library and the default local credentials.
Set `GRAFANA_PASSWORD` if you configured a different admin password. It does not
check Yahoo connectivity; synthetic data is deliberately independent of the
upstream feed.
