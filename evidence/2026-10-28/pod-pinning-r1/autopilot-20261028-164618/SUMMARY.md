# Pod B autopilot summary (20261028-164618 UTC)

All runs: three replicas plus load source on one host (loopback), MATCHING mode, every original frame,
outcome, matching replay and final canonical state verified by the audit. Latency is measured from each
order's planned arrival time (includes any source queueing); offer-to-reply is closest to a round trip.

## Vendor reference points (not like-for-like)

- AWS 2025 (Adaptive): Aeron Cluster Premium round trip: 98 µs ([source](https://aws.amazon.com/blogs/industries/aeron-on-aws-2025-performance-benchmark-results/))
- Google Cloud 2024 (Adaptive): Aeron open-source transport round trip: 57 µs ([source](https://weareadaptive.com/2024/02/21/aeron-google-cloud-performance-testing/))

Caveats: vendor figures are vendor-reported round trips across separate hosts, without a matching engine;
our durability mode for those tests is assumed to be Aeron's default (no per-write force), not verified.
Our runs are single-host, include matching and reply, and are bounded to 180,000 originals per run.
Errors and stage failures are listed in AUTOPILOT.log and SUMMARY.json.
