"""Stream Yahoo ticks into InfluxDB, or generate explicitly labeled demo data."""

import argparse
import logging
import math
import os
import signal
import time

from influxdb_client import InfluxDBClient

from yliveticker import YLiveTicker
from yliveticker.sinks.influxdb import InfluxDBSink

logger = logging.getLogger(__name__)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "symbols", nargs="*",
        default=os.getenv("TICKER_SYMBOLS", "BTC-USD ETH-USD AAPL").split(),
        help="Yahoo symbols (default: TICKER_SYMBOLS or BTC-USD ETH-USD AAPL)",
    )
    parser.add_argument(
        "--demo", action="store_true", default=os.getenv("TICKER_DEMO", "0") == "1",
        help="Generate synthetic DEMO-* symbols instead of connecting to Yahoo",
    )
    parser.add_argument(
        "--max-connections", type=int, default=os.getenv("TICKER_MAX_CONNECTIONS", "4"),
        help="Maximum Yahoo connections (default: TICKER_MAX_CONNECTIONS or 4)",
    )
    args = parser.parse_args(argv)
    if not args.symbols:
        parser.error("Provide at least one symbol or set TICKER_SYMBOLS")
    if args.max_connections < 1:
        parser.error("--max-connections must be positive")
    return args


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


def stream_demo(sink, symbols):
    logger.warning("DEMO MODE: synthetic data only; symbols are prefixed DEMO-")
    step = 0
    while True:
        timestamp = int(time.time() * 1000)
        for index, symbol in enumerate(symbols):
            base_price = (index + 1) * 100.0
            sink.on_ticker(None, {
                "id": "DEMO-" + symbol,
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

    # The blocking client returns on Ctrl+C; treat Docker's SIGTERM the same way.
    def stop(signum, frame):
        raise KeyboardInterrupt

    previous_handler = signal.signal(signal.SIGTERM, stop)
    sink = None
    try:
        wait_for_influxdb(url, token, org, bucket)
        sink = InfluxDBSink(url=url, token=token, org=org, bucket=bucket, flush_interval=1.0)
        if args.demo:
            stream_demo(sink, args.symbols)
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
    main()
