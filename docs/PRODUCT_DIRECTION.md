# Focus and evidence

yliveticker is an unofficial Yahoo WebSocket toolkit. We make **no promises**
about feed availability, accuracy, completeness, timeliness, coverage, continued
compatibility, or delivery. Yahoo can change or discontinue the endpoint.
Connection state and test results are observations, not assurances.

## Differentiation hypothesis

The useful focus is a small, inspectable **tick → storage → visualization** path:
bounded multi-connection watchlists, optional sinks, per-symbol observations,
and a reproducible Grafana quickstart. This complements yfinance's broader data
toolkit. Streaming, async support, and subscribe/unsubscribe alone are not unique
selling points; yfinance has those too. Do not position this as a better licensed
feed, complete market coverage, or a replacement for historical-data tooling.

## Client-side behavior and limits

- The connection pool and queues have explicit capacity bounds. Reconnects
  resubmit the current watchlist; there is no upstream acknowledgement or replay.
- Sink failures retain accepted batches in memory and back off exponentially.
  At capacity, new ticks are rejected explicitly and counted. Shutdown raises
  `SinkWriteError` if a final write fails. A crash or forced stop loses memory;
  retries can duplicate writes if a commit succeeded but its response was lost.
- `diagnostics` distinguishes transport receipts, callback errors, queue pressure,
  accepted/written/pending/rejected records and storage failures. Counters describe
  this process, not all upstream trades. Drivers differ in acknowledgement semantics
  (QuestDB TCP flush, for example, is not proof of durable server persistence).
- The dashboard separates receipt age from Yahoo quote age. Estimated regular
  hours exclude holidays and exceptional sessions. Silence means unknown—not
  necessarily closed, unsupported, or disconnected. Old heartbeats become unknown.
- pandas retains at most 100,000 points by default. `session_volume` is the last
  reported cumulative value, never represented as interval traded volume.

## Measure adoption without unsolicited telemetry

No analytics are sent by the package. The collector can write local JSON with
`--metrics-json PATH`; Compose writes `/tmp/yliveticker-status.json` inside the
collector. It includes mode, elapsed time, time to first successful write,
per-symbol receipt/write counts and errors. Synthetic runs must stay separate
from real-feed observations. Users may voluntarily share a redacted snapshot.

Useful measures to establish a baseline:

1. First successful live use: elapsed time to first real persisted tick; count
   attempted starts and failures too, with environment and observation date.
2. Quickstart completion: actual Grafana queries and browser rendering, not
   merely running containers. Separate synthetic pipeline checks from live runs.
3. Sustained sessions: duration, reconnects, per-symbol receipts, pending/rejected
   writes, and gaps observed during a clearly dated run.
4. Repeat usage: voluntary follow-up or downstream examples; downloads, clones
   and stars are discovery signals, not unique or retained users.

There are no agreed numeric growth targets yet. First establish denominators and
baseline observations, then choose targets with the maintainer. Do not invent
retention or active-user numbers from GitHub/PyPI traffic.

## Release evidence

Required deterministic checks cover supported Python/protobuf combinations,
local transport reconnects, bounded queues, delayed quotes, storage failures,
shutdown, generated metadata, and an empty-to-populated Grafana pipeline.
The manual live observation workflow is separate and is not a merge gate. Its
result is valid only for the tested environment, symbols and observation period.
Release after CI and human review; never interpret passing CI as feed coverage.
