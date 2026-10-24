# Byte-identical local native archive copies

All66 completed/stopped local native `.rec` copies were verified against the original full-state inventories and original compressed archives.65 were converted in the serial batch;one was already converted by the pilot. Every replacement preserves the full logical size and SHA256;the batch independently rereads the original archive,inventory and full replacement after conversion.

The batch saved 4879548416 allocated bytes;the pilot saved 63963136 bytes. No logical bytes were removed. The complete original `.tar.gz` archives and manifests remain unchanged. These are local archival copies;this does not perform remote cleanup,Aeron retention,service compaction or a trading performance optimization.

`plan.json` pins both executed scripts and all66 paths;`progress.jsonl` retains each file outcome. `completion.json` is the final aggregate. No partial failure occurred.
