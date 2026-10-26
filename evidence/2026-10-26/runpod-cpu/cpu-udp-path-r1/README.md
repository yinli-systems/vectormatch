# Original CPU UDP and force evidence

See [the measured report](../../../../docs/CPU_UDP_PATH_RESULTS.md).

`ARCHIVE_MANIFEST.json` binds every selected original file to the complete private
draft attachment; `PRIVATE_ARCHIVE_VERIFIED.json` records the authenticated full
download and every nested original member verification. `UPLOAD_METADATA.json`
is the provider's immutable asset metadata. Bulk data is kept outside Git objects.

The four `UDP-*.json` files are the original aggregate-only comparison. Its gate
fails. `LEDGER_DIAGNOSTIC.json` is a separate instrumented 20,000-packet diagnostic,
with exact ingress/egress missing-observation partitions. Neither is trading
throughput. `FORCE_VERIFIED.json` binds all original write/force samples, three
files and an independent byte generator. The two `node*-PRE_STOP.json` files
record quiescence and final container network counters before shutdown.

`STOPPED.json` and both `node*-STOPPED.txt` files bind the observed stopped state
and zero-hourly-cost UI to the exact new Pod IDs. `EXISTING_CPU_PRESERVED.json`
is the subsequent read-only SSH identity check of the original prepaid CPU.

The private attachment also preserves refused preparation attempts and collection
errors. No failed attempt is presented as a second execution, successful point,
or permission to replace an original. No SSH private key, API key, runner token,
unrelated workload or live trading account data is included.
