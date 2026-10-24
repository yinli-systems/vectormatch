The frozen analyzer passed its only actual derivation. All 18 original inputs and four method files remained byte-identical. It observed all 33792 arrivals, twelve closed cuts and ten cuts with3072takers/6144events. Global all-arrival p99 was554.293743ms.

At comparable cut ends2..10, released-not-dispatched was316,287,301,312,299,297,293,293,312; dispatched-awaiting-reply was0. Before the next cuts, released-not-fully-confirmed returned to2–4. Across cut-end2→10, 24576 replies completed in 49.144105930s (500.080316/s), with 24572 releases and exact backlog drift-4. The eight adjacent fully offered intervals range497.033–504.798confirmed/s.

Cut11 ends after the finite67.584s source window. Its end backlog3 versus cut10’s312 and interval10→11 input452.988/s reflect source exhaustion. That interval must be excluded when interpreting ongoing500/s drift; homogeneous command/event content does not make arrival exposure equivalent.

These are finite one-host observations for this fixed release/configuration, with no observed accumulation over those eight intervals. They do not identify a throughput limit, establish indefinite stability, guarantee real-time latency or demonstrate100million/s. Component p99s are not additive. Original strict raw and root proofs remain authoritative for correctness, scheduler validity and full archive closure.

The first configuration attempt used the output directory instead of its `/collection` child and failed before analyzer launch. Its original intent/observation/failure record remains intact. The corrected second configuration executed the unchanged analyzer once; no data was modified.
