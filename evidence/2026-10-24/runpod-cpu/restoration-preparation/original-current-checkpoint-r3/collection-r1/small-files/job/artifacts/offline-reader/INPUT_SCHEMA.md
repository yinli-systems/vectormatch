# Stopped current original checkpoint reader R3

This is a bounded, offline preparation. It never starts Aeron, an Archive, SQL, a node, or a business command. It does not recover or alter native state. No actual new checkpoint has been decoded by this preparation.

The producer must generate a NEW snapshot in the existing original recovered cluster, stop every owned process cleanly, and only then read the native metadata/recordings. The manifest root contains exact copied stop receipt, three exact copied `recording.log` files, and three bounded service recording prefixes. Every path is relative to the manifest directory and contains no `..`, absolute component, or symlink. Existing reader sources are untouched.

The producer must read and hash the ENTIRE selected native recording, verify that all bytes beyond the retained prefix are zero, and bind its full SHA/length below. This reader independently hashes only retained prefixes and metadata copies; it expressly does not claim to reread whole native recordings. Parent lifecycle retains full stopped native archive/inventory as separate evidence.

The Python module validates the entire input before creating output. It copies each recording log to an output-owned disposable directory. Aeron's `RecordingLog(..., false)` opens its file for READ+WRITE even when false; Java receives ONLY the disposable copy and verifies its before/after bytes. Original/native files never go through that constructor.

Schema (all displayed keys mandatory, unknown keys rejected):

```json
{
  "schemaVersion": 1,
  "scope": "STOPPED_CURRENT_ORIGINAL_CHECKPOINT",
  "allOwnedStopped": true,
  "sourceRevision": "e1db2e755a834234efb60b7a1ed291b31ce33c16",
  "expected": {
    "canonicalEngineSha256": "ea7b98a23a30b5ddde84db4520e3e915fd07a73900e2c3aa41ee28c8614b5b65",
    "commandSeq": 4609,
    "eventSeq": 6214,
    "marketSeq": 6194,
    "exportedSeq": 6214,
    "pendingEvents": 0,
    "outboxCapacity": 65536
  },
  "stopReceipt": {"path": "owned-stop.json", "bytes": 1, "sha256": "ACTUAL_64_LOWERCASE_HEX"},
  "nodes": [
    {
      "node": 0,
      "preflightMaxSnapshotEntryIndex": "ACTUAL_INTEGER_BEFORE_NEW_SNAPSHOT",
      "recordingLog": {"path": "node0/recording.log", "bytes": "ACTUAL_INTEGER", "sha256": "ACTUAL_64_LOWERCASE_HEX"},
      "selected": {
        "recordingId": "ACTUAL_INTEGER",
        "leadershipTermId": "ACTUAL_INTEGER",
        "termBaseLogPosition": "ACTUAL_INTEGER",
        "logPosition": "ACTUAL_INTEGER",
        "timestamp": "ACTUAL_INTEGER",
        "serviceEntryIndex": "ACTUAL_INTEGER",
        "consensusRecordingId": "ACTUAL_INTEGER",
        "consensusEntryIndex": "ACTUAL_INTEGER"
      },
      "recording": {
        "filename": "ACTUAL_RECORDING_ID-0.rec",
        "bytes": "ACTUAL_FULL_RECORDING_INTEGER_BYTES",
        "sha256": "ACTUAL_FULL_RECORDING_64_LOWERCASE_HEX",
        "prefix": {"path": "node0/recording-prefix.bin", "bytes": "ACTUAL_INTEGER_64_TO_16777216", "sha256": "ACTUAL_64_LOWERCASE_HEX"},
        "zeroTailBeyondPrefixVerified": true
      }
    },
    "EXACT_SAME_KEYS_FOR_NODE_1",
    "EXACT_SAME_KEYS_FOR_NODE_2"
  ]
}
```

The example deliberately supplies no invented current recording ID, term, position, snapshot timestamp, or full recording hash. Strings marked ACTUAL_INTEGER are placeholders and must be JSON integers in the real manifest.

`preflightMaxSnapshotEntryIndex` is the maximum actual valid snapshot entry index before requesting this new snapshot, including service 0 and consensus -1 snapshots (or -1 if none). Both selected entries must be strictly newer. Java independently selects the latest valid service-0 snapshot and exactly one valid consensus-(-1) snapshot with identical term/base/position/timestamp; it rejects newer unpaired service or consensus snapshots. Across all three nodes term/base/position/timestamp must match. Recording IDs need not match between nodes.

`owned-stop.json` must contain `allOwnedStopped: true`, `errors: []`, `forcedKill: false`, and 3 to 16 `stops` records with `stopped: true`, including roles `node-0`, `node-1`, and `node-2`. Other existing receipt fields are preserved and accepted.

Frames are limited to 16 MiB, bounded unfragmented DATA frames, at most 1,024 client session records, and at most 8 MiB application allocation. Framework markers must carry the dynamically selected term/log position; transport CRC and nested application digest/roundtrip must verify. All three engine and combined checkpoint byte arrays must be exactly equal, and the engine SHA/frontiers must match the fixed observed R2 state above.

## Owner-supervised integration (Python 3.8+ stdlib)

Place `read-current-checkpoints.py`, `PREPARATION.json`, `original-current-checkpoint-reader-r3.jar`, and exact four `lib/*.jar` siblings in the caller-owned preparation directory. Import the module by exact path. No wildcard classpath, shell, environment Java selection, or nested Java launch is required.

```python
plan = reader.prepare_inputs(manifest_path, NEW_output_dir, explicit_absolute_java_path)
child_results = []
for node in plan['nodes']:
    # Caller launches node['argv'] DIRECTLY and owns PID/startTicks/argv SHA/pidfd,
    # bounds logs/time, observes exit, and stops only this exact owned process if needed.
    child_results.append({'node': node['node'], 'exitCode': actual_exit_code})
receipt = reader.finish_outputs(plan, child_results)
```

Both functions start and stop zero processes. `plan['nodes'][i]['argv']` is the exact validated direct JVM command. `finish_outputs` requires three ordered successful caller-owned exit results, revalidates all inputs/frozen artifacts, compares every state file, and writes the new `receipt.json`. Preserve failed attempt outputs; no automatic retries or overwrites.

A local-only convenience CLI exists with three explicit arguments: manifest, NEW output, absolute Java. It uses bounded `subprocess.run` and must NOT be used inside a cloud lifecycle with a separate PID ownership supervisor.
