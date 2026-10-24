"""Archive closed metadata and parser preparations only; never execute their code."""
from pathlib import Path
import datetime, hashlib, importlib.util, json, shutil
HERE=Path(__file__).resolve().parent
BASE=HERE.parent
WORKSPACE=BASE.parents[2]
TARGET=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/metadata-and-parser-r1'
LIB=BASE/'event-fetch-unit-proof-archive-r1/archive.py'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
    with p.open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
spec=importlib.util.spec_from_file_location('closed_unit_archive_copy_primitives',LIB)
lib=importlib.util.module_from_spec(spec);spec.loader.exec_module(lib)
trees={'local-metadata':'event-fetch-metadata-preparation-r1',
       'local-metadata-root-review':'event-fetch-metadata-root-review-r1',
       'linux-metadata':'event-fetch-linux-metadata-preparation-r1',
       'linux-metadata-root-review':'event-fetch-linux-metadata-root-review-r1',
       'linux-metadata-independent-review':'event-fetch-linux-metadata-independent-review-r1',
       'long-parser':'event-fetch-long-parser-preparation-r1',
       'parser-root-review':'event-fetch-parser-root-review-r1',
       'local-working-copy-sparsity':'local-evidence-sparse-preparation-r1'}
assert not TARGET.exists() and shutil.disk_usage(WORKSPACE).free>1024**3+128*1024**2
for name in ['event-fetch-metadata-root-review-r1','event-fetch-linux-metadata-root-review-r1','event-fetch-parser-root-review-r1']:
    assert json.loads((BASE/name/'ROOT_REVIEW.json').read_text())['passed']
assert json.loads((BASE/'event-fetch-linux-metadata-independent-review-r1/REVIEW.json').read_text())['passed']
pins={name:dict(source=str(BASE/source),**lib.snapshot(BASE/source)) for name,source in trees.items()}
save(HERE/'REGISTRATION.json',dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sources=pins,target=str(TARGET),copyLibrarySha256=sha(LIB),archiverSourceSha256=sha(Path(__file__)),scope='Closed copy and nested known-marker scan; no JVM/SSH/Git/test or benchmark execution'))
TARGET.mkdir(parents=True)
for name,source in trees.items():lib.copy_tree(BASE/source,TARGET/name,{k:v for k,v in pins[name].items() if k!='source'})
(TARGET/'archiver').mkdir()
shutil.copy2(Path(__file__),TARGET/'archiver/archive.py');shutil.copy2(LIB,TARGET/'archiver/copy-scan-library.py');shutil.copy2(HERE/'REGISTRATION.json',TARGET/'archiver/REGISTRATION.json')
save(TARGET/'SOURCE_COPY_BINDINGS.json',dict(passed=True,sources=pins,allCopiedBytesModesOwnersEmptyDirectoriesExact=True,noSourceModified=True))
(TARGET/'README.md').write_text('''# Event Fetch16/32 candidate: actual metadata and strict parser preparation

Source commit d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8 is on the private candidate branch. Actual four-JAR fingerprint is 87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa. The separate local-unit-validation-r1 archive contains the 47 distinct final Java tests, original source/artifact captures and complete installed four JARs.

One local metadata javac/java attempt and one actual Linux metadata JVM attempt are retained with every source, precompiled helper, input body/config, original stdout/stderr, command and process receipt. Linux PID67629/start4772830/full-NUL-argv SHA5e298a96c72bbda80ea17e2f1b78fcb25f0bc3c2ca053176d6a8277d818fcb00 was independently observed, normally reaped and strictly absent in a second read-only check. Seven runtime class origins use three distinct JARs; all four JAR bodies, including unloaded Agrona, are pinned. Local and Linux observations match in every field except the two explicit path containers. No cluster, driver, owner, native UDP/business session or CLI was started by metadata. Pure Plan derivation uses a temporary in-memory reference engine.

Both actual admitted Plans retain raw185514924B, allocated-growth757122377B, read8, cap4, chunk6144, owner1ms, driver100us,33792 arrivals@500/s over67.584s. Only selected page and selected event/logical RPC bounds differ: selected event RPC bound4225 vs2113. This is a prospective bound, not an observed RPC count, speedup, throughput or p99 result. Metadata selection is intent, not actual owner/driver consumption. JDK binaries remain hash-only; the same captured helper class, sources, release text and installed-JAR bodies are retained.

The new strict LONG parser requires explicit event_fetch_count16 or32, binds actual config/summary/Plan/coordinator/cycle selection, exact count/range/contiguous prefixes and full selected pages plus final partial. Physical callbacks, 13 CSV fields, earliest reply, four offers, eight credits,24 phases, force-before-ACK, UNKNOWN and strict scheduler gates remain. Original nine parser/test sources are byte-exact under baseline. Two standalone6763B maximum UTF8 replies and a163B Fetch32 request are explicitly SYNTHETIC codec fixtures, not JVM captures or benchmark results. The original41 and corrected42 pure guard runs and their full source ZIPs are preserved. The later correction only derives the inherited unused telemetry helper exposure from LONG instead of12.8s. A future collector must use a new event identity gate; imported common.load_config retains legacy provenance and is not that gate.

Root local/schema/ZIP reviews and an independent Linux source/execution review are included. The local working-copy sparse-checkout receipt records reversible omission of already committed historical evidence bodies from this materialized checkout; Git objects, commit/history, runtime, code and current owner/event evidence remain intact. The actual post-metadata cloud free-space observation was505161B below the existing single-arm reserve, so metadata PASS did not authorize launching an arm. Subsequent archival retirement and benchmark execution are separate receipts.

No native functional or performance comparison is established by this archive. No billion-scale, capacity ceiling, hard-real-time or zero-latency claim. Inventory includes complete copied bytes/modes/uid/gid and empty directories; marker scanning is bounded to named classes, not universal secret absence. Original generation-time pending flags remain unchanged and are qualified by later separate review receipts.
''')
for p in sorted(TARGET.rglob('*')):
    if p.is_file():lib.scan_file(p,p.relative_to(TARGET).as_posix())
assert not lib.HITS, 'Preserve marker review failure; do not push'
save(TARGET/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',dict(passed=True,namedMarkerClasses=sorted(lib.MARKERS),hits=lib.HITS,scannedObjects=len(lib.SCANNED),scannedBytes=sum(r['bytes'] for r in lib.SCANNED),scanned=lib.SCANNED,excludedSelfAndFinalInventoryClosure=True,notUniversalSecretAbsence=True))
for name,source in trees.items():assert lib.snapshot(BASE/source)=={k:v for k,v in pins[name].items() if k!='source'}
inventory=lib.snapshot(TARGET);total=sum(r['bytes'] for r in inventory['files'].values());assert total<=128*1024**2
save(TARGET/'INVENTORY.json',dict(schemaVersion=1,files=inventory['files'],directories=inventory['directories'],payloadFiles=len(inventory['files']),payloadBytes=total,excludedSelfAndClosure=['INVENTORY.json','CLOSED.json']))
save(TARGET/'CLOSED.json',dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=sha(TARGET/'INVENTORY.json'),payloadFiles=len(inventory['files']),payloadBytes=total,directories=len(inventory['directories']),allSourceBeforeAfterAndCopiesExact=True,actualLinuxMetadataPassed=True,metadataOnly=True,strictParserFinalGuards=42,nativeBenchmarkExecuted=False,performanceClaimed=False,knownMarkerReviewPassed=True))
print(json.dumps(dict(passed=True,files=len(inventory['files']),directories=len(inventory['directories']),payloadBytes=total,inventorySha256=sha(TARGET/'INVENTORY.json'),closedSha256=sha(TARGET/'CLOSED.json'),markerObjects=len(lib.SCANNED))))
