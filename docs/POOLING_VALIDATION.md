# Pooling validation for 0.5.6

Validation completed on 2026-10-10 UTC, with Python 3.12.

## Automated checks

- 52 tests passed, including the existing decoder, pandas, database sink and
  Grafana collector tests, plus pooling, deduplication, capacity errors,
  serialized callbacks, callback failures, backpressure and shutdown tests.
- A local WebSocket server forced one bucket to close normally. The real
  transport reconnected and resubscribed that bucket while the second remained
  connected. This passed with websocket-client 1.9.2 and the minimum 1.6.0.
- Compose configuration validated. Native InfluxDB 2.7.11 and Grafana 12.4.0
  passed the bundled synthetic integration check: datasource health, symbol
  discovery, latest price, tick age, price charts and session-volume queries.
  The rendered dashboard had no browser errors; SIGTERM flushed the collector
  and exited successfully. Docker containers could not run in this environment;
  the Compose smoke workflow remains the container-level check.
- Wheel and source distribution built successfully and passed `twine check`.

## Live Yahoo comparison

Both clients used the same shuffled watchlist of 280 symbols: 250 equities and
30 crypto pairs. The pool subscribed in buckets of 100, 100 and 80. A simultaneous
raw single-socket control subscribed to all 280 in one message.

| Observation | New pooled client | Single-socket control |
| --- | ---: | ---: |
| Connections | 3 | 1 |
| Symbols producing ticks | 25 | 3 |
| Ticks received | 124 | 12 |
| Ticks after the first 15 seconds | 113 | 9 |
| Connection/decode errors | 0 | 0 |

The control observed the feed for 60 seconds after subscribing. The pool was
stopped by a 65-second timer started before connection setup; total harness
runtime, including connection setup and shutdown, was approximately 75 seconds.
These are overlapping live observations, not an equal-duration throughput test.
The important result is that the pool delivered **112 ticks from symbols beyond
the first 100 positions**, whereas the control delivered none from those positions.

Pool callbacks ran on one caller thread. All workers stopped; the event queue
was empty, with no backpressure or shutdown discards in this run. Source
timestamps advanced during the observation, confirming continuing live updates.

Equity markets were closed and those subscriptions produced no ticks. Five
crypto symbols also remained silent in this observation; silence does not establish
that a symbol is invalid. Pooling recovers subscriptions beyond the observed
100-symbol boundary, but cannot guarantee upstream availability or durable replay.

Earlier boundary tests placed BTC/ETH at positions 100 and 101 on one socket:
only position 100 produced ticks. Unsubscribing one earlier symbol and explicitly
resubscribing position 101 enabled its updates. Sending smaller subscription
messages on the same socket did not recover subscriptions beyond 100.
