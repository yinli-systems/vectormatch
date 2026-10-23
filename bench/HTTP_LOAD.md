# HTTP arrival-rate generator

Start the local workbench, then run:

```sh
source scripts/env.sh
gradle :bench:httpLoad --args='--url http://127.0.0.1:8000 --rate 50 --seconds 5 --out reports/local/http-smoke'
```

`--rate` schedules **new orders per second**, independently of response speed.
For each accepted residual order, the generator submits one dependent cancel.
Cancels require the order ID, so they are explicitly a dependent stage, not a
second fixed-arrival stream. A healthy 250-order run ordinarily sends 500 HTTP
requests. No request with an invented or stale order ID is generated.

The workload uses account 1, BUY GTC at price 1, quantity 1. It is an order
acceptance/reservation/cancellation test, not a representative matching workload.
The actual trade count from non-replayed order results is reported and may be
zero. The generator pauses synthetic flow and leaves it paused. Concurrent manual
trading can still change results, so avoid using the UI during controlled runs.

Only loopback local-workbench URLs are accepted. This measures HTTP, the writer,
and the local forced journal. It does **not** measure Aeron quorum replication or
production cross-region latency. Client and server run on the same machine, so
they compete for its CPU and memory.

## Bounds and sequencing

- Defaults: 50 placements/second for 5 seconds, 64 producer lanes.
- Bounds: 1–1000 placements/second, 1–60 seconds, 5000 planned placements total,
  and `--max-in-flight` between 1 and 128.
- Each lane has a unique producer ID and processes one order/cancel pair at a
  time. Sequence numbers remain ordered per producer despite concurrent HTTP.
- No available lane: retain the planned arrival as scheduled-but-not-sent.
  Arrivals more than 250 ms late are also retained without sending a catch-up
  burst. Offered load therefore remains visible when the generator saturates.
- Request timeout is 5 seconds; drain is bounded to 12 seconds. Unknown outcomes
  retire their lane. There are no automatic retries and no replacement keys.
- Each invocation consumes at most the configured number of new producer IDs;
  the core's producer high-water marks are intentionally retained. Long repeated
  experiments must account for the engine's producer/order caps.

## Artifacts and interpretation

- `summary.json`: offered/sent/not-sent accounting, HTTP and business outcomes,
  actual trade count, latency distributions, environment and measurement scope.
- `requests.jsonl`: original route/payload, producer/sequence, monotonic planned,
  sent and completed times relative to the run start, HTTP status and outcome.
- `scheduled-not-sent.json`: every arrival dropped by generator limits, with its
  original scheduled time and reason.
- `unresolved.json`: unknown request identities and unsuccessful cancels. Query
  or retry the **same producer, sequence and payload** when reconciling. A timeout
  does not prove an order was rejected. A failed cancel can leave an open order.
- `initial-state.json`, `final-state.json`: server observations. If the final
  fetch fails, its error is saved without discarding completed measurements.
- Ten `.hlog` files: order/cancel scheduled, sent and dispatch latency, plus
  accepted-only scheduled/sent latency. All units are microseconds, with run
  timestamps. `scheduled` includes client dispatch delay. `sent` starts just
  before `HttpClient.sendAsync`, so it includes client transport queues/network,
  server processing and the response. Cancel scheduled time is when its order
  response made it eligible, not an independent arrival slot.

Read accepted latency together with rejected, unknown and not-sent counts.
Successful fast rejections do not establish sustainable useful throughput.
The report's counting invariant is `ordersSent + scheduledNotSentOrders ==
plannedOrders`. HTTP 5xx and transport failures are conservatively unknown;
known HTTP 4xx and explicit business rejection results have separate counters.
