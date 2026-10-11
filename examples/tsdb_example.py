"""Stream Yahoo ticks into InfluxDB, or generate a synthetic test feed."""

import argparse
import json
import logging
import math
import os
import signal
import time

from influxdb_client import InfluxDBClient

from yliveticker import YLiveTicker
from yliveticker.sinks.influxdb import InfluxDBSink

logger = logging.getLogger(__name__)

DEFAULT_SYMBOLS = (
    "BTC-USD",    # Global crypto (keeps the quickstart active around the clock)
    "EURUSD=X",   # Global foreign exchange
    "GC=F",       # Gold futures
    "AAPL",       # United States
    "SHOP.TO",    # Canada
    "VALE3.SA",   # Brazil
    "SAP.DE",     # Germany
    "HSBA.L",     # United Kingdom
    "NPN.JO",     # South Africa
    "RELIANCE.NS",  # India
    "0700.HK",    # Hong Kong
    "7203.T",     # Japan
    "BHP.AX",     # Australia
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "symbols", nargs="*",
        default=os.getenv("TICKER_SYMBOLS", " ".join(DEFAULT_SYMBOLS)).split(),
        help="Yahoo symbols (default: TICKER_SYMBOLS or the global quickstart watchlist)",
    )
    parser.add_argument(
        "--synthetic", action="store_true",
        default=os.getenv("TICKER_SYNTHETIC", "0") == "1",
        help="Generate clearly labeled SYNTH-* test symbols instead of connecting to Yahoo",
    )
    parser.add_argument(
        "--max-connections", type=int, default=os.getenv("TICKER_MAX_CONNECTIONS", "4"),
        help="Maximum Yahoo connections (default: TICKER_MAX_CONNECTIONS or 4)",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Check that a configured symbol has a tick in InfluxDB within the last 30 seconds",
    )
    args = parser.parse_args(argv)
    if not args.symbols:
        parser.error("Provide at least one symbol or set TICKER_SYMBOLS")
    if args.max_connections < 1:
        parser.error("--max-connections must be positive")
    return args


def check_ticks(url, token, org, bucket, symbols, synthetic):
    """Verify storage, mode and freshness, without creating another collector."""
    ids = ["SYNTH-" + symbol if synthetic else symbol for symbol in symbols]
    query = (
        "from(bucket: " + json.dumps(bucket) + ")\n"
        "  |> range(start: -30s)\n"
        '  |> filter(fn: (r) => r._measurement == "ticker" and r._field == "price")\n'
        "  |> filter(fn: (r) => contains(value: r.id, set: " + json.dumps(ids) + "))\n"
        "  |> last()"
    )
    with InfluxDBClient(url=url, token=token, org=org, timeout=5000) as client:
        tables = client.query_api().query(query)
        if any(table.records for table in tables):
            logger.info("Recent %s ticks verified in InfluxDB bucket %s",
                        "synthetic" if synthetic else "live", bucket)
            return 0
    logger.error("No recent %s ticks in InfluxDB for %s; check collector logs",
                 "synthetic" if synthetic else "live", ", ".join(ids))
    return 1


def wait_for_influxdb(url, token, org, bucket, timeout=90):
    """Wait for initialization and verify access before starting the buffer thread."""
    deadline = time.monotonic() + timeout
    with InfluxDBClient(url=url, token=token, org=org, timeout=5000) as client:
        while True:
            try:
                if client.ping() and client.buckets_api().find_bucket_by_name(bucket):
                    return
            except Exception as exc:
                logger.debug("InfluxDB is not ready: %s", exc)
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "InfluxDB is not ready or the token cannot access the bucket; "
                    "check INFLUX_URL, INFLUX_TOKEN, INFLUX_ORG and INFLUX_BUCKET"
                )
            logger.info("Waiting for InfluxDB initialization...")
            time.sleep(2)


def stream_synthetic(sink, symbols):
    logger.warning("SYNTHETIC TEST FEED: not market data; symbols are prefixed SYNTH-")
    step = 0
    while True:
        timestamp = int(time.time() * 1000)
        for index, symbol in enumerate(symbols):
            base_price = (index + 1) * 100.0
            sink.on_ticker(None, {
                "id": "SYNTH-" + symbol,
                "price": base_price + math.sin(step / 10.0 + index) * base_price * 0.01,
                "dayVolume": 10000 + step * 100,
                "timestamp": timestamp,
            })
        step += 1
        time.sleep(1)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    url = os.getenv("INFLUX_URL", "http://localhost:8086")
    token = os.getenv("INFLUX_TOKEN", "my-super-secret-auth-token")
    org = os.getenv("INFLUX_ORG", "yliveticker")
    bucket = os.getenv("INFLUX_BUCKET", "ticker_data")

    if args.check:
        try:
            return check_ticks(url, token, org, bucket, args.symbols, args.synthetic)
        except Exception as exc:
            logger.error("InfluxDB tick check failed: %s", exc)
            return 1

    # The blocking client returns on Ctrl+C; treat Docker's SIGTERM the same way.
    def stop(signum, frame):
        raise KeyboardInterrupt

    previous_handler = signal.signal(signal.SIGTERM, stop)
    sink = None
    try:
        wait_for_influxdb(url, token, org, bucket)
        sink = InfluxDBSink(url=url, token=token, org=org, bucket=bucket, flush_interval=1.0)
        if args.synthetic:
            stream_synthetic(sink, args.symbols)
        else:
            logger.info("Streaming %s into %s; press Ctrl+C to stop", ", ".join(args.symbols), bucket)
            YLiveTicker(on_ticker=sink.on_ticker, ticker_names=args.symbols,
                        max_connections=args.max_connections)
    except KeyboardInterrupt:
        logger.info("Stopping collector and flushing buffered ticks...")
    finally:
        if sink is not None:
            sink.stop()
        signal.signal(signal.SIGTERM, previous_handler)


if __name__ == "__main__":
    raise SystemExit(main())
