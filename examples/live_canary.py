"""Bounded live observation, not an upstream availability or coverage test."""

import argparse
import json
import threading
import time

from yliveticker import YLiveTicker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="*", default=["BTC-USD", "ETH-USD"])
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 300:
        parser.error("--seconds must be between 1 and 300")
    started = time.monotonic()
    first_tick = None

    def received(ws, tick):
        nonlocal first_tick
        if first_tick is None:
            first_tick = time.monotonic() - started

    client = YLiveTicker(ticker_names=args.symbols, symbols_per_connection=1,
                        max_connections=len(args.symbols), start=False, on_ticker=received)
    timer = threading.Timer(args.seconds, client.close)
    timer.start()
    try:
        client.run()
    finally:
        timer.cancel()
        client.close()
    print(json.dumps(dict(observed_seconds=time.monotonic() - started,
                         first_tick_seconds=first_tick, diagnostics=client.diagnostics,
                         note="A snapshot of an unofficial feed, not an availability promise."), indent=2))
    return 0 if first_tick is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
