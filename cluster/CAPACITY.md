# Cluster checkpoint capacity

New Cluster state machines use these limits:

| State | Maximum |
|---|---:|
| Accounts | 10,000 |
| Producers | 10,000 |
| Retained orders, including terminal orders | **100,000** |
| Cached command results, globally | 100,000 |
| Cached results per producer | 1,024 |
| Unacknowledged outbox events, default | 65,536 |
| Encoded Cluster checkpoint | 256 MiB |

Terminal orders and their client IDs are retained in this release. Once the retained-order limit is reached, a new order is rejected before allocating another order or reserving funds. Cancellation and existing-result queries can still be processed subject to their normal rules. Data compaction and retention lifecycle remain future work.

The previous core default of one million retained orders is unsuitable for this Cluster checkpoint limit: a valid 128-character client ID alone produces a 311-byte canonical order record. The Cluster therefore uses a smaller explicit core configuration rather than inheriting the standalone core default.

`ClusterCapacity` reserves a conservative serialized budget of 384 bytes/order, 1,024 bytes/cached command and result, 512 bytes/producer, 64 bytes/account, 256 bytes/outbox event, and 8 MiB of fixed headroom. With the defaults the budget is **171,725,824 bytes**, below 268,435,456 bytes. The core snapshot stores strings as UTF-16 code units; valid retained producer/client IDs have at most 128 code units. The current result reasons and event detail strings fit the remaining per-record allowance. Protocol/schema changes must update this accounting and its tests.

Increasing an outbox/cache/core configuration beyond the budget is rejected at service construction or checkpoint restoration. The one-million-event outbox supported by the standalone outbox class is deliberately rejected with the Cluster's default core limits.

Existing checkpoints that encode the older one-million-order core limit are rejected explicitly. The implementation does not silently rewrite their configuration or discard their data. Use a fresh development state directory or perform and verify an explicit migration. This change does not modify any already-running JVM; replaying older logs with changed capacity policies is also an upgrade operation requiring validation.

`ClusterCapacityTest` inserts 100,000 accepted orders and verifies that order 100,001 is rejected with unchanged retained-order count and correct available balance. It also checks the default budget, unsafe legacy/outbox configurations, and preservation of limits in the canonical core snapshot.
