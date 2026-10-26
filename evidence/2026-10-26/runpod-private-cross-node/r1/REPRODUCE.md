# Offline reproduction

These are synthetic, finite matching experiments, not funded venue trades or a
production SLA. All test Pods are stopped. Do not run the historical live-control
scripts against recycled endpoints. Their exact source, original parameters,
failures, provenance, disk-state archives and original CSVs are preserved for review.

Use an authenticated GitHub account with access to yinli-systems/vectormatch.
The four raw asset IDs are in PRIVATE_RAW_RELEASE_VERIFIED.json. For each ID:

```
gh api repos/yinli-systems/vectormatch/releases/assets/ASSET_ID \
  -H 'Accept: application/octet-stream' > collected/nodeN-closed-evidence.tar.gz
```

Copy the four nN-VERIFIED.json files from the evidence index's collection directory
into the same collected directory. The auditor verifies complete outer bytes,
every member SHA and the exact inventory before analyzing original rows; it does
not extract untrusted archive paths.

From a repository checkout containing the auditor:

```
python3 scripts/audit-private-cross-node.py \
  --collection /absolute/path/to/collected \
  --registration evidence/2026-10-26/runpod-private-cross-node/r1/CAPACITY_REGISTRATION.json \
  --pods evidence/2026-10-26/runpod-private-cross-node/r1/PODS.json \
  --output /absolute/path/to/fresh-audit.json
python3 -m unittest discover -s scripts/tests -p test_private_cross_node_audit.py
python3 -m unittest discover -s scripts/tests -p 'test_analyze_capacity*.py'
```

The controller attachment also preserves post_analysis.py for the separate
A/B/A/B audit and CPU/shaper/official recording-log observations. It uses the
same unmodified tested capacity-reference analyzer. Its historical P/R paths
must be adapted to the local evidence checkout; no live cloud action is needed.
The original controller's SSH interruption, first unavailable quote, failed
provider initialization, original margin refusal and final successful original
results remain. No failed arm was silently replaced.

CLOSED_MANIFEST.json inside each node archive lists all preserved regular files;
transient Aeron driver directories and all secrets are excluded. Full controller
member hashes are in CONTROLLER_MEMBERS.json. Remote experiment control scripts
are experimental tooling, not a production deployment or authenticated gateway.
