# yliveticker → InfluxDB → Grafana

This local quickstart runs a `yliveticker` collector, InfluxDB 2, and Grafana,
plus a one-shot dashboard generator. The collector and generated dashboard use
the same instrument registry and `TICKER_SYMBOLS` setting.
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
recently persisted receipt and Grafana readiness. Delayed quote timestamps do
not fail this check. A timeout means no recent persisted receipt was observed;
it is not proof that Yahoo or the collector is broken.
It uses container health checks and works with older Compose v2 versions
without the `--wait` flag. Set `QUICKSTART_TIMEOUT=300` when a longer wait is needed.
The first build downloads images and Python dependencies.

Open **[Grafana at localhost:3000](http://localhost:3000)**. The ticker dashboard
is the home page and appears under **Dashboards → yliveticker**. You can also use
[its permanent URL](http://localhost:3000/d/yliveticker-dashboard).
The top of the dashboard identifies the active feed and distinguishes synthetic
prices from Yahoo quotes. Chart timestamps default to the viewing browser's
timezone; use Grafana's time picker to switch to UTC or another IANA timezone.
Each price and available-volume chart title identifies its country, while its
info bubble gives the instrument and regular session directly in UTC. Markets
that observe DST show both UTC schedules; `FPH.NZ` is explicitly identified as
**New Zealand**. The symbol selector contains exactly the configured watchlist,
even when no data has ever arrived. Historical symbols from another configuration
or synthetic run are not automatically mixed into the current watchlist. The default range is one hour so delayed quotes—such as
New Zealand—remain visible.

The older `main` Compose file starts only InfluxDB and Grafana, not a collector;
`TICKER_SYNTHETIC=1` has no effect there. Use the PR branch to try this quickstart.

The dashboard provides:

- Active feed and stored tick count, queried from InfluxDB.
- A rolling received-ticks-per-minute value and one-minute bar chart. These use
  collector receipt time rather than Yahoo's potentially delayed event time.
- A full-width, scrollable per-symbol table: receipt age, **newest quote age**,
  Yahoo-reported session, regular schedule, connection state and observational status.
  Freshness uses the greatest quote timestamp seen since restart, so a later-arriving
  old snapshot cannot replace a newer quote. **Received/Written since restart** count
  messages in the current collector run, not unique trades or points in the selected
  chart range. Charts retain historical data across restarts. Old heartbeats become unknown.
- A symbol selector and separate price charts for each selected symbol. Every
  configured ticker gets a panel, so closed or silent markets show **No data**
  instead of disappearing. Price and volume legends append the instrument's
  Yahoo quote-currency code (for example, `AAPL · USD` and `7203.T · JPY`).
  Tables and charts are ordered Asia-Pacific first, then Europe/Middle East/Africa,
  the Americas, and global assets; silent symbols keep their place.
- Positive **cumulative session volume** (`dayVolume`), not interval/candle
  volume. Yahoo's missing/unsupported volume arrives as zero for some assets;
  the quickstart treats it as unavailable and omits those volume panels.
- Five-second refresh and browser-local chart timestamps, with UTC selectable
  in Grafana's time picker. Prices remain in each symbol's quote currency; they
  are not converted into a common currency. A currency shown on a volume legend
  is context for the instrument; cumulative volume itself remains a unit count.

## Choose symbols

The default watchlist is geographically and asset-class diverse:

| Market | Yahoo symbol | Instrument | Regular session (local time) |
| --- | --- | --- | --- |
| Global | `BTC-USD` | Bitcoin | 24/7 |
| Global FX | `EURUSD=X` | EUR/USD | 24 hours, Sunday–Friday |
| COMEX | `GC=F` | Gold futures | Sun–Fri 17:00–16:00 CT; daily 16:00–17:00 break |
| New Zealand (NZX) | `FPH.NZ` | Fisher & Paykel Healthcare | 10:00–16:45 |
| Australia (ASX) | `BHP.AX` | BHP | 10:00–16:00 |
| Japan (Tokyo) | `7203.T` | Toyota | 09:00–11:30; 12:30–15:30 |
| Hong Kong | `0700.HK` | Tencent | 09:30–12:00; 13:00–16:00 |
| Singapore | `D05.SI` | DBS Group | 09:00–12:00; 13:00–17:00 |
| India | `RELIANCE.NS` | Reliance Industries | 09:15–15:30 |
| Dubai | `EMAAR.AE` | Emaar Properties | 10:00–15:00 |
| South Africa | `NPN.JO` | Naspers | 09:00–17:00 |
| Germany (Xetra) | `SAP.DE` | SAP | 09:00–17:30 |
| United Kingdom (London) | `HSBA.L` | HSBC | 08:00–16:30 |
| United States (New York) | `AAPL`, `NVDA` | Apple; NVIDIA (California issuer) | 09:30–16:00 ET |
| Canada (Toronto) | `SHOP.TO` | Shopify | 09:30–16:00 ET |
| Brazil (São Paulo) | `VALE3.SA` | Vale | 10:00–17:00 BRT |

These are real Yahoo instruments, not bundled sample records. Ordered from
Auckland westward, their regular sessions provide broad weekday coverage, but
they are not a guaranteed continuous feed: holidays, closed markets and Yahoo
availability still apply. A West Coast company still trades on the US market
schedule. Crypto has no scheduled daily closure; FX and futures have near-continuous
weekday sessions. None of this promises that Yahoo will send updates. Some exchanges are delayed by Yahoo, so their stored event
timestamps can trail wall-clock time even while the market is open. The table
shows regular full-day sessions; holidays, special/half-day sessions and daylight
saving changes can alter them.

The status table recognizes [JPX cash-market holidays for 2026](https://www.jpx.co.jp/english/corporate/about-jpx/calendar/index.html),
including Sports Day on October 12. Other markets and years still use estimated
weekday schedules; they are not covered by this holiday calendar.
US quotes can arrive outside regular hours: Yahoo also distributes overnight prices
through [Blue Ocean](https://unified.www.yahooinc.com/press/yahoo-finance-expands-global-coverage-with-new-uk-based-programming-and-24-5-market-data).
The table labels the newest quote's reported session, including observed Yahoo code
`4` as overnight. An unreported/zero session is not asserted to be pre-market.

On macOS/Linux, from the repository root:

```bash
TICKER_SYMBOLS="BTC-USD NVDA EURUSD=X" docker compose -f docker/docker-compose.yml up --build -d
```

On Windows or to keep the setting between runs, put this in `docker/.env`:

```dotenv
TICKER_SYMBOLS=BTC-USD NVDA EURUSD=X
```

Then run the original Compose command again. The one-shot generator rebuilds
price panels for exactly this watchlist, including custom symbols that have never
received a tick. Unknown metadata is labeled as unknown, not guessed. The volume
selector follows the visible Symbols selection. Closed markets naturally show older ticks or an empty **No data**
price chart.

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
a persisted receipt within the last 30 seconds; an unhealthy collector can mean the upstream
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
Switching modes regenerates the dashboard's configured symbol list. Old stored
series remain in InfluxDB but are not mixed into the new dashboard selection.

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
and the sink to attempt a flush before forcing termination. Failed batches are
retained in a bounded in-memory retry buffer; overflow rejects new records and
failed final flushes raise an explicit error. Crashes/forced stops lose memory;
retries can duplicate records. This is not a durable market-data queue.

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
InfluxDB 3. Grafana provisioning and the generated dashboard are mounted read-only in Grafana.
Edit `yliveticker/instruments.py`, `yliveticker/dashboard.py` and the packaged
`dashboard_template.json`, then regenerate the checked-in default with:

```bash
python -m yliveticker.dashboard --output docker/grafana/dashboards/dashboard.json
```

`INFLUX_PORT` and `GRAFANA_PORT` can override host ports for isolated test stacks.
Compose writes local measurements inside the collector; inspect them with
`docker compose -f docker/docker-compose.yml exec collector cat /tmp/yliveticker-status.json`.
No telemetry is sent. See [observations and limitations](../docs/PRODUCT_DIRECTION.md).

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
| Empty price chart | This is expected for a configured ticker with no quote in the selected range, including a sleeping/closed market. Check market hours, widen the range, then inspect collector logs if an open market remains silent. |
| Additional custom symbol missing from Symbols | Widen the time range. The default watchlist is always present, while non-default symbols are discovered from stored price ticks in the displayed range. |
| Tick-rate chart is empty after upgrade | The `ticker_ingest` receipt-time series starts when the upgraded collector starts; it is not reconstructed from older, potentially delayed event timestamps. |
| Volume panel is missing | Yahoo does not provide meaningful `dayVolume` for every instrument (commonly FX and some delayed quotes). Zero is treated as unavailable, so the dashboard omits that volume panel rather than implying zero trading. |
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
