"""Copy and known-marker scan of one explicit CLOSED Event Fetch arm; never re-audit business."""
from pathlib import Path, PurePosixPath
import datetime, hashlib, importlib.util, io, json, shutil, stat, sys, tarfile, zipfile
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
WORKSPACE = BASE.parents[2]
PRIMITIVES = BASE / 'owner-cloud-arm-archive-preparation-r2/archive_arm.py'
spec = importlib.util.spec_from_file_location('closed_owner_archive_primitives', PRIMITIVES)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
# Current task explicitly includes every regular file, including historical caches if any.
p.EXCLUDED_PARTS = set()
LIMIT = 512 * 1024**2
FLOOR = 1024**3
MAX_CONTAINER = 128 * 1024**2
MAX_SCANNED = 16 * 1024**3
SCANNED = []
HITS = []
MEMBERS = []
TOTAL = 0

def require(ok, message):
    if not ok:
        raise AssertionError(message)

def load(path):
    return json.loads(path.read_text())

def save(path, value):
    p.save(path, value)

def raw_scan(stream, label, expected_size=None):
    """Bounded-memory named-marker scan, complete SHA, with overlap across block boundaries."""
    global TOTAL
    h = hashlib.sha256()
    size = 0
    tail = b''
    hits = set()
    for block in iter(lambda: stream.read(1024**2), b''):
        size += len(block)
        TOTAL += len(block)
        require(TOTAL <= MAX_SCANNED, '16GiB finite total logical scan cap')
        h.update(block)
        candidate = tail + block
        if any(prefix in candidate for prefix in (b'-----BEGIN ', b'gh', b'AKIA', b'ASIA', b'xox', b'AIza', b'sk-')):
            for match in p.PATTERN.finditer(candidate):
                hits.add(match.lastgroup)
        tail = candidate[-256:]
    if expected_size is not None:
        require(size == expected_size, 'Complete stream bytes: ' + label)
    if hits:
        HITS.append({'path': label, 'knownMarkerClasses': sorted(hits)})
    SCANNED.append({'path': label, 'bytes': size, 'sha256': h.hexdigest()})

def kind(name):
    if name.endswith(('.tar.gz', '.tgz', '.tar')):
        return 'tar'
    if name.endswith(('.jar', '.zip')):
        return 'zip'
    return None

def recurse(stream, label, name, expected_size, depth=0):
    """Containers alone are bounded in memory; native .rec leaves are always streamed."""
    require(depth <= 6, 'Container depth6 cap')
    selected = kind(name)
    if selected is None:
        raw_scan(stream, label, expected_size)
        return
    require(expected_size <= MAX_CONTAINER, '128MiB compressed container cap')
    data = stream.read(MAX_CONTAINER + 1)
    require(len(data) == expected_size, 'Complete bounded container bytes')
    raw_scan(io.BytesIO(data), label, expected_size)
    walk_container(io.BytesIO(data), label, selected, depth)

def safe(name):
    require(name and '\\' not in name, 'Explicit safe POSIX member name')
    return p.safe_member(name)

def walk_container(stream, label, selected, depth):
    seen = set()
    if selected == 'tar':
        with tarfile.open(fileobj=stream, mode='r|*') as archive:
            for member in archive:
                safe(member.name)
                require(member.name not in seen, 'Duplicate TAR member')
                seen.add(member.name)
                require(len(seen) <= 16384, 'Finite TAR member count')
                meta = {'path': label + '!' + member.name, 'container': label,
                        'type': 'directory' if member.isdir() else 'regular',
                        'bytes': member.size, 'mode': member.mode, 'uid': member.uid, 'gid': member.gid}
                require(member.isdir() or member.isfile(), 'No link/special TAR member')
                MEMBERS.append(meta)
                if member.isdir():
                    continue
                source = archive.extractfile(member)
                require(source is not None, 'Regular TAR member stream')
                recurse(source, meta['path'], member.name, member.size, depth + 1)
    else:
        with zipfile.ZipFile(stream) as archive:
            require(len(archive.infolist()) <= 16384, 'Finite ZIP member count')
            for info in archive.infolist():
                safe(info.filename)
                require(info.filename not in seen, 'Duplicate ZIP member')
                seen.add(info.filename)
                mode = (info.external_attr >> 16) & 0xffff
                require(stat.S_IFMT(mode) in (0, stat.S_IFDIR, stat.S_IFREG), 'No link/special ZIP member')
                meta = {'path': label + '!' + info.filename, 'container': label,
                        'type': 'directory' if info.is_dir() else 'regular',
                        'bytes': info.file_size, 'storedUnixMode': mode,
                        'uidGidNotCapturedByZip': True}
                MEMBERS.append(meta)
                if info.is_dir():
                    continue
                require(info.file_size <= 256 * 1024**2, '256MiB ZIP entry bound')
                with archive.open(info) as source:
                    recurse(source, meta['path'], info.filename, info.file_size, depth + 1)

def scan_file(path, label):
    # Scan the actual compressed bytes as well as every expanded child; no extraction.
    with path.open('rb') as source:
        raw_scan(source, label, path.stat().st_size)
    selected = kind(path.name)
    if selected:
        require(path.stat().st_size <= MAX_CONTAINER, '128MiB top-level container bound')
        with path.open('rb') as source:
            walk_container(source, label, selected, 0)

def verify_receipts(trees, plan):
    review = load(trees['root-review'] / 'ROOT_REVIEW.json')
    collection = trees['actual-collection']
    success = load(collection / 'SUCCESS.json')
    final = load(collection / 'finalized/LOCAL_COLLECTION_COMPLETE.json')
    raw = load(collection / 'raw/result.json')
    require(review['passed'] is True and review['arm'] == 1 and review['eventFetchCount'] == 16,
            'Exact closed first16 root review')
    require(review['sourceCommit'] == plan['sourceCommit'] and review['independent4AnchorCodeFingerprint'] == plan['codeFingerprint']
            and review['releaseSha256'] == plan['releaseSha256'], 'Exact new artifact source/release/FP')
    require(review['allFullOuterMembersVerified'] is True and review['allRawInputsUnchanged'] is True
            and review['allOriginalRawCanonicalAndThreeSnapshotsVerified'] is True
            and review['sameNewArtifactFunctionalQualified'] is True, 'Root complete actual qualification receipt')
    require(review['ownerPollMaximumParkNs'] == 1000000 and review['serverDriverMaximumParkNs'] == 100000,
            'Fixed owner1ms/driver100us')
    require(p.sha(trees['root-review'] / 'ROOT_REVIEW.json') == plan['rootReviewSha256'], 'Pinned actual root receipt')
    require(p.sha(trees['root-review-preparation-r2'] / 'review_event_collected.py') == review['scriptSha256'],
            'Executed root helper body retained')
    require(success['passed'] is True and len(success['steps']) == 5 and all(x['exitCode'] == 0 for x in success['steps']),
            'Five closed collection steps')
    require(final['passed'] is True and final['eventFetchCount'] == 16 and final['frozenReleaseSha256'] == plan['releaseSha256']
            and final['controllerSha256'] == plan['controllerSha256'], 'Actual completed collection identity')
    require(raw['passed'] is True and raw['strictSchedulerTimingAdmission'] is True
            and raw['localFunctionalDiagnosticOptIn'] is False and p.sha(collection / 'raw/result.json') == review['rawAuditSha256'],
            'Strict root-bound raw audit receipt, no execution')
    require(p.sha(trees['actual-config'] / 'collector-config.json') == p.sha(collection / 'collection/collector-config.json'),
            'Actual config-copy binding')
    active = load(trees['close-inspection-r1'] / 'stdout.json')
    closed = load(trees['close-inspection-r2'] / 'stdout.json')
    gate = load(trees['closed-controller-gate'] / 'root-controller-closed.json')
    require(active['state'] == 'CONTROLLER_RUNNING' and active['closedGate'] is False and len(active['controlPlaneInputs']) == 1,
            'Historical ACTIVE single-register probe preserved')
    require(closed['state'] == 'CLOSED_PASS_CONTROL_PLANE' and closed['allFourOwnedJvmsStrictlyPidAbsent'] is True
            and closed['controller']['observation'] == 'PID_ABSENT', 'Actual closed control plane receipt')
    require(gate['inspectionSha256'] == p.sha(trees['close-inspection-r2'] / 'stdout.json')
            and gate['executedSourceSha256'] == plan['closeProbeSha256'], 'Exact executed close source/gate binding')
    return review

def main():
    plan = load(HERE / 'COPY_PLAN.json')
    freeze = load(HERE / 'SOURCE_FROZEN.json')
    for name, pin in freeze['sourceFiles'].items():
        require(p.row(HERE / name) == pin, 'Frozen new archiver/helper body changed')
    require(p.sha(PRIMITIVES) == plan['primitivesSha256'], 'Reviewed R2 primitives changed')
    target = Path(plan['target'])
    require(not target.exists(), 'Fresh immutable target only')
    trees = {name: Path(scope['source']) for name, scope in plan['sourceTrees'].items()}
    for name, source in trees.items():
        require(source.is_relative_to(BASE) and not any(x.is_symlink() for x in [source] + list(source.parents)), 'Explicit local regular scope')
        require(p.snapshot(source) == plan['sourceTrees'][name]['inventory'], 'Initial closed source pin: ' + name)
    source_bytes = sum(r['bytes'] for x in plan['sourceTrees'].values() for r in x['inventory']['files'].values())
    require(source_bytes + 32 * 1024**2 <= LIMIT, '512MiB copy cap with32MiB metadata reserve')
    require(shutil.disk_usage(WORKSPACE).free >= FLOOR + LIMIT, '1GiB floor plus512MiB archive reserve')
    review = verify_receipts(trees, plan)
    shared = Path(plan['sharedPreparation']['path'])
    for name, expected in plan['sharedPreparation']['receipts'].items():
        require(p.row(shared / name) == expected, 'Immutable shared deployment archive reference')
    attempt = HERE / 'attempt-r1'
    attempt.mkdir()
    save(attempt / 'REGISTRATION.json', {'atUTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'archiverSourceSha256': p.sha(Path(__file__)), 'copyPlanSha256': p.sha(HERE / 'COPY_PLAN.json'),
         'sourceFreezeSha256': p.sha(HERE / 'SOURCE_FROZEN.json'), 'sourceBytes': source_bytes,
         'target': str(target), 'freeBytesBefore': shutil.disk_usage(WORKSPACE).free,
         'noSshJavaTestsBusinessRawAuditGit': True, 'rootReviewSha256': plan['rootReviewSha256']})
    try:
        target.mkdir(parents=True)
        for name, source in trees.items():
            p.copy_tree(source, target / name, plan['sourceTrees'][name]['inventory'])
        save(target / 'SOURCE_BEFORE_COPY.json', plan['sourceTrees'])
        portable = {}
        for original, pin in review['inputs'].items():
            source = Path(original)
            require(source.stat().st_size == pin['bytes'] and p.sha(source) == pin['sha256'], 'Root reviewed input hash drift')
            destinations = []
            for name, root in trees.items():
                if source.is_relative_to(root):
                    destinations.append(name + '/' + str(source.relative_to(root)))
            if not destinations:
                old_base = BASE / 'cpu-event-fetch-cloud-staging-r1'
                require(source.is_relative_to(old_base), 'Every external root input explicitly mapped')
                destination = '../cloud-preparation-r1/cpu-event-fetch-cloud-staging-r1/' + str(source.relative_to(old_base))
                require((target / destination).stat().st_size == pin['bytes'] and p.sha(target / destination) == pin['sha256'], 'Shared staged receipt byte binding')
                destinations = [destination]
            portable[original] = dict(pin, archivedAt=destinations)
        save(target / 'ROOT_REVIEW_INPUT_PORTABLE_BINDINGS.json', {'passed': True, 'inputs': portable,
             'mappingOnlyNoBusinessReaudit': True, 'originalAbsolutePathsUnchanged': True})
        save(target / 'SHARED_DEPLOYMENT_REFERENCES.json', plan['sharedPreparation'])
        archiver = target / 'archiver'
        archiver.mkdir()
        for source, name in [(Path(__file__), 'archive.py'), (PRIMITIVES, 'owner_r2_snapshot_copy_marker_primitives.py'),
                             (HERE / 'COPY_PLAN.json', 'COPY_PLAN.json'), (HERE / 'REGISTRATION.json', 'REGISTRATION.json'),
                             (HERE / 'SOURCE_FROZEN.json', 'SOURCE_FROZEN.json'),
                             (attempt / 'REGISTRATION.json', 'ATTEMPT_REGISTRATION.json')]:
            shutil.copy2(source, archiver / name)
        # Preserve the exact prior helper/config/freeze provenance without importing their main.
        p.copy_tree(HERE / 'baseline', archiver / 'baseline', p.snapshot(HERE / 'baseline'))
        metrics = review['arms'][0]
        (target / 'README.md').open('x').write(f'''# Closed Event Fetch first16 arm evidence

One finite one-host loopback LONG lineage:33792 scheduled arrivals at500/s over67.584s,12maintenance cycles/24read phases. Source{plan['sourceCommit']}, actual code{plan['codeFingerprint']}, controller{plan['controllerSha256']}, release{plan['releaseSha256']}. Selectedevent page16, fixedowner maximum park1000000ns/server anddriver100000ns, read8/businesscap4/chunk6144/leader0term0/sync2. Configured maximum park is not actual OS sleep duration or a hard realtime guarantee.

The independent root receipt reports nearest-rank all-arrival scheduled-to-replyp99 {metrics['allArrivalP99Ns']}ns, accepted inside arrivalwindow{metrics['acceptedWithinArrivalWindow']}, windowgoodput{metrics['arrivalWindowGoodputPerSecond']}/s, summed maintenance-cycle wall{metrics['maintenanceCycleWallNs']}ns, offeredhighwater{metrics['offeredHighWater']}, retainedWARNpairs{metrics['retainedPostCheckpointEosWarningPairs']}. These are copied facts from the exact root/raw receipts, not a new calculation. One arm does not establish sustainedcapacity, a16/32speedup, a platform upperbound, zero latency or100M scale; it does not authorize/start the nextarm. Three checkpointlog matches are not independent binary snapshot-record decoding.

Entire251-file original collection tree is copied without exclusions: both complete compressed TARs, every original tape/CSV/writer payload/reference, every auditor and its sources/config/receipt/failure, full original staged39rows/JAR/proofs inside the outerTAR, materialized actual4JARs, strictfull native/raw/finalizer receipts. Root verified193outerfiles/24directories/1367606404logicalbytes and73rawinputs. RemoteTAR owner/mode/emptydir facts remain in original manifests; copied localfilesystem UID/GID is recorded separately and is not substituted for remote ownership.

All actual launch/config/outer collection/rootexecution records, the ACTIVE first probe reading onlyoneexecutionregister, CLOSED secondprobe and exactrootclosedgate are retained. The first roothelper preparation failed before anycandidatefile write/rawread because of generated AST whitespaceTrueand; only its available diagnostic exists and no missinginvalidsource is invented. R2 fullsource/helper/freeze/prepare/diff and subsequent actualPASS are retained. Historical generation-time pending/firstNativeNotYetRun fields remain unchanged. Actual qualification of this new artifact comes from the fullclosed first16 raw/canonical/threecheckpoint/owner/archive receipts plus independent root review, not an oldartifact's native proof.

Shared deployment preparations are referenced by siblingcloud-preparation-r1 exactINVENTORY/CLOSED; all39actual stagedsource/JAR/proof bytes are nevertheless retained in this arm's fullouterTAR. ROOT_REVIEW_INPUT_PORTABLE_BINDINGS maps every original rootinput to its copiedbody or exactsharedreceipt. Original absolute paths are preserved, not silently made runnable in relocation.

Archiveonly: fullbefore/after sourceSHA/size/mode/uid/gid/emptydir closure and every copiedfile plus recursiveTAR/ZIP/JAR/tape knownmarker scan. Large native.rec members are streamed with boundedmemory; no native sparse/full extraction. No collector/auditor/business/test/JVM/Gradle/SSH/network/Git action, signals/resources/deletion. Named-marker review is bounded and does not establish universal secretabsence. INVENTORY excludes onlyitself andCLOSED; CLOSED bindsit.
''')
        for path in sorted(target.rglob('*')):
            if path.is_file():
                scan_file(path, str(path.relative_to(target)))
        save(target / 'KNOWN_CREDENTIAL_MARKER_REVIEW.json', {'passed': not HITS, 'namedMarkerClasses': sorted(p.MARKERS),
             'hits': HITS, 'scannedObjects': len(SCANNED), 'scannedBytesIncludingNested': TOTAL,
             'allCopiedRawBytesAndRecursiveTarZipJarMembersScanned': True, 'largeNativeMembersStreamed': True,
             'maximumDepth': 6, 'maximumCompressedContainerBytes': MAX_CONTAINER,
             'maximumTotalScanBytes': MAX_SCANNED, 'noExtraction': True,
             'boundedKnownMarkerReviewNotUniversalSecretAbsence': True, 'scanned': SCANNED, 'containerMembers': MEMBERS})
        require(not HITS, 'Known marker hits preserved, no closure')
        after = {}
        for name, source in trees.items():
            current = p.snapshot(source)
            require(current == plan['sourceTrees'][name]['inventory'], 'Closed original aftercopy drift: ' + name)
            after[name] = current
        save(target / 'SOURCE_AFTER_COPY.json', {'passed': True, 'allOriginalsUnchanged': True, 'sourceTrees': after})
        inventory = p.snapshot(target)
        total = sum(x['bytes'] for x in inventory['files'].values())
        require(total <= LIMIT, '512MiB final archive cap')
        save(target / 'INVENTORY.json', {'schemaVersion': 1, 'files': inventory['files'], 'directories': inventory['directories'],
             'payloadFiles': len(inventory['files']), 'payloadBytes': total, 'fullModeUidGidAndEmptyDirectoryClosure': True,
             'excludedSelfAndClosure': ['INVENTORY.json', 'CLOSED.json']})
        for name, pin in inventory['files'].items():
            require(p.row(target / name) == pin, 'Final payload closure drift')
        result = {'schemaVersion': 1, 'passed': True, 'arm': 1, 'eventFetchCount': 16,
                  'atUTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'inventorySha256': p.sha(target / 'INVENTORY.json'), 'payloadFiles': len(inventory['files']),
                  'directories': len(inventory['directories']), 'payloadBytes': total,
                  'allExplicitClosedScopesRetainedWithoutExclusions': True,
                  'allOriginalCollectionAndBothCompleteTarsRetained': True,
                  'sourceCopyBeforeAfterEqual': True, 'fullShaSizeModeUidGidEmptyDirectoryClosureVerified': True,
                  'rootActualReviewAndBothProbeAttemptsRetained': True, 'allKnownMarkerScansPassed': True,
                  'noBusinessAuditTestsJavaSshGitExecuted': True, 'noSparseExtraction': True,
                  'noCapacityOrSpeedupClaimed': True, 'closureExcludes': ['INVENTORY.json', 'CLOSED.json']}
        save(target / 'CLOSED.json', result)
        result = dict(result, closedSha256=p.sha(target / 'CLOSED.json'), scannedObjects=len(SCANNED),
                      scannedBytesIncludingNested=TOTAL, freeBytesAfter=shutil.disk_usage(WORKSPACE).free)
        save(attempt / 'COMPLETION.json', result)
        print(json.dumps(result))
    except BaseException as error:
        import traceback
        save(attempt / 'FAILED.json', {'passed': False, 'error': repr(error), 'traceback': traceback.format_exc(),
                                     'partialArchiveAndSourcesPreserved': True, 'noAutomaticRetry': True})
        raise

if __name__ == '__main__':
    main()
