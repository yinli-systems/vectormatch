"""Copy and known-marker scan of one explicit CLOSED Event Fetch arm; never re-audit business."""
from pathlib import Path, PurePosixPath
import argparse, datetime, hashlib, importlib.util, io, json, shutil, stat, sys, tarfile, zipfile
from archive_contract import validate_identity, selected_page, render_readme
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
    page=validate_identity(plan);arm=plan['arm']
    review=load(trees['root-review']/'ROOT_REVIEW.json')
    collection=trees['actual-collection']
    success=load(collection/'SUCCESS.json');final=load(collection/'finalized/LOCAL_COLLECTION_COMPLETE.json');raw=load(collection/'raw/result.json')
    for report in (review,success,final,raw):
        require(report['passed'] is True and report['arm']==arm and report['eventFetchCount']==page
                and report['ownerPollMaximumParkNs']==1000000 and report['serverDriverMaximumParkNs']==100000,
                'Actual same arm/page/fixed owner and driver receipts required')
    require(review['sourceCommit']==raw['sourceCommit']==plan['sourceCommit']
            and review['independent4AnchorCodeFingerprint']==plan['codeFingerprint']
            and review['releaseSha256']==raw['releaseSha256']==final['frozenReleaseSha256']==plan['releaseSha256']
            and final['controllerSha256']==plan['controllerSha256'],'Exact same NEW source/release/artifact/controller')
    require(review['allFullOuterMembersVerified'] is True and review['allRawInputsUnchanged'] is True,
            'Independent full outer and original inputs closure')
    for report in (final,raw,review):
        require(report['allOriginalRawCanonicalAndThreeSnapshotsVerified'] is True
                and report['sameNewArtifactFunctionalQualified'] is True,'Actual qualified raw/canonical/three-checkpoint receipts')
    require(p.sha(trees['root-review']/'ROOT_REVIEW.json')==plan['rootReviewSha256'],'Exact actual root review SHA')
    require(p.sha(trees['root-review-preparation-r2']/'review_event_collected.py')==review['scriptSha256'],'Actual executed root helper retained')
    require(len(success['steps'])==5 and all(x['exitCode']==0 for x in success['steps']),'All five actual closed collection steps')
    require(raw['strictSchedulerTimingAdmission'] is True and raw['localFunctionalDiagnosticOptIn'] is False
            and p.sha(collection/'raw/result.json')==review['rawAuditSha256'],'Actual strict root-bound raw receipt')
    require(p.sha(trees['actual-config']/'collector-config.json')==p.sha(collection/'collection/collector-config.json'),'Exact actual config copy')
    gate=load(trees['closed-controller-gate']/'root-controller-closed.json')
    require(gate['arm']==arm and gate['eventFetchCount']==page and gate['executedSourceSha256']==plan['closeProbeSha256']
            and gate['controllerSha256']==plan['controllerSha256'] and gate['frozenReleaseSha256']==plan['releaseSha256'],
            'Actual same-arm closed-controller gate')
    probes=[];matching=[]
    for name,path in sorted(trees.items()):
        if not name.startswith('close-inspection-r'):continue
        output=path/'stdout.json';wire=p.sha(output)
        try:value=load(output);state=value.get('state','MISSING_STATE_PRESERVED')
        except (ValueError,UnicodeError):value={};state='NON_JSON_STDOUT_PRESERVED'
        probes.append(dict(scope=name,state=state,stdoutSha256=wire))
        if wire==gate['inspectionSha256']:
            require(value['state']=='CLOSED_PASS_CONTROL_PLANE' and value['allFourOwnedJvmsStrictlyPidAbsent'] is True
                    and value['controller']['observation']=='PID_ABSENT' and value['arm']==arm and value['eventFetchCount']==page,
                    'Gate must bind one actually present successful closed observation')
            matching.append(name)
    require(1<=len(probes)<=16 and matching,'All actual existing attempts preserved and one exact gate-bound closed proof required')
    return review,probes


def main():
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--config-sha256',required=True)
    args=parser.parse_args();config=args.config.absolute()
    require(config.is_relative_to(BASE) and config.name=='COPY_PLAN.json' and '..'not in config.parts
            and not any(x.is_symlink()for x in(config,*config.parents)),'Explicit canonical local current plan')
    require(p.sha(config)==args.config_sha256,'Explicit exact root-created plan SHA')
    plan=load(config);validate_identity(plan)
    freeze = load(HERE / 'SOURCE_FROZEN.json')
    for name, pin in freeze['sourceFiles'].items():
        require(p.row(HERE / name) == pin, 'Frozen new archiver/helper body changed')
    require(p.sha(HERE/'SOURCE_FROZEN.json')==plan['preparationSha256'],'Exact frozen R2 source closure')
    require(p.sha(PRIMITIVES) == plan['primitivesSha256'], 'Reviewed R2 primitives changed')
    target = Path(plan['target'])
    require(target==WORKSPACE/('evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-arm-%d-r1'%plan['arm'])
            and not any(x.is_symlink()for x in(target,*target.parents)),'Exact fresh current arm archive only')
    require(not target.exists(), 'Fresh immutable target only')
    trees = {name: Path(scope['source']) for name, scope in plan['sourceTrees'].items()}
    for name, source in trees.items():
        require(source.is_relative_to(BASE) and not any(x.is_symlink() for x in [source] + list(source.parents)), 'Explicit local regular scope')
        require(p.snapshot(source) == plan['sourceTrees'][name]['inventory'], 'Initial closed source pin: ' + name)
    singles={name:Path(row['source']) for name,row in plan['sourceFiles'].items()}
    for name,path in singles.items():
        safe(name);require(path.is_relative_to(BASE) and not any(x.is_symlink()for x in(path,*path.parents))
                           and p.row(path)==plan['sourceFiles'][name]['pin'],'Explicit source-only single file changed')
    source_bytes = sum(r['bytes'] for x in plan['sourceTrees'].values() for r in x['inventory']['files'].values())+sum(row['pin']['bytes']for row in plan['sourceFiles'].values())
    require(source_bytes + 32 * 1024**2 <= LIMIT, '512MiB copy cap with32MiB metadata reserve')
    require(shutil.disk_usage(WORKSPACE).free >= FLOOR + LIMIT, '1GiB floor plus512MiB archive reserve')
    review,probes = verify_receipts(trees, plan)
    for reference in plan['sharedArchives']:
        shared=Path(reference['path'])
        for name,expected in reference['receipts'].items():require(p.row(shared/name)==expected,'Immutable shared archive reference')
    attempt = config.parent/'archive-attempt-r1'
    attempt.mkdir()
    save(attempt / 'REGISTRATION.json', {'atUTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'archiverSourceSha256': p.sha(Path(__file__)), 'copyPlanSha256': p.sha(config),
         'sourceFreezeSha256': p.sha(HERE / 'SOURCE_FROZEN.json'), 'sourceBytes': source_bytes,
         'target': str(target), 'freeBytesBefore': shutil.disk_usage(WORKSPACE).free,
         'noSshJavaTestsBusinessRawAuditGit': True, 'rootReviewSha256': plan['rootReviewSha256']})
    try:
        target.mkdir(parents=True)
        for name, source in trees.items():
            p.copy_tree(source, target / name, plan['sourceTrees'][name]['inventory'])
        for name,path in singles.items():
            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
            require(p.row(destination)==plan['sourceFiles'][name]['pin'],'Exact source-only single copy')
        save(target / 'SOURCE_BEFORE_COPY.json', plan['sourceTrees'])
        save(target/'SOURCE_SINGLE_FILES_BEFORE_COPY.json',plan['sourceFiles'])
        portable = {}
        for original, pin in review['inputs'].items():
            source = Path(original)
            require(source.stat().st_size == pin['bytes'] and p.sha(source) == pin['sha256'], 'Root reviewed input hash drift')
            destinations = []
            for name, root in trees.items():
                if source.is_relative_to(root):
                    destinations.append(name + '/' + str(source.relative_to(root)))
            for name,path in singles.items():
                if source==path:destinations.append(name)
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
        save(target/'IMMUTABLE_SHARED_ARCHIVE_REFERENCES.json',plan['sharedArchives'])
        archiver = target / 'archiver'
        archiver.mkdir()
        for source, name in [(Path(__file__), 'archive.py'), (PRIMITIVES, 'owner_r2_snapshot_copy_marker_primitives.py'),
                             (config, 'COPY_PLAN.json'), (config.parent / 'REGISTRATION.json', 'REGISTRATION.json'),
                             (HERE / 'SOURCE_FROZEN.json', 'SOURCE_FROZEN.json'),
                             (attempt / 'REGISTRATION.json', 'ATTEMPT_REGISTRATION.json')]:
            shutil.copy2(source, archiver / name)
        # Preserve the exact prior helper/config/freeze provenance without importing their main.
        p.copy_tree(HERE,archiver/'preparation',p.snapshot(HERE))
        (target/'README.md').open('x').write(render_readme(plan,review,plan['sourceTrees']['actual-collection']['inventory'],probes))
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
        for name,path in singles.items():require(p.row(path)==plan['sourceFiles'][name]['pin'],'Source-only single aftercopy drift')
        save(target / 'SOURCE_AFTER_COPY.json', {'passed': True, 'allOriginalsUnchanged': True, 'sourceTrees': after,'sourceFiles':plan['sourceFiles']})
        inventory = p.snapshot(target)
        total = sum(x['bytes'] for x in inventory['files'].values())
        require(total <= LIMIT, '512MiB final archive cap')
        save(target / 'INVENTORY.json', {'schemaVersion': 1, 'files': inventory['files'], 'directories': inventory['directories'],
             'payloadFiles': len(inventory['files']), 'payloadBytes': total, 'fullModeUidGidAndEmptyDirectoryClosure': True,
             'excludedSelfAndClosure': ['INVENTORY.json', 'CLOSED.json']})
        for name, pin in inventory['files'].items():
            require(p.row(target / name) == pin, 'Final payload closure drift')
        result = {'schemaVersion': 1, 'passed': True, 'arm': plan['arm'], 'eventFetchCount': selected_page(plan['arm']),
                  'atUTC': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'inventorySha256': p.sha(target / 'INVENTORY.json'), 'payloadFiles': len(inventory['files']),
                  'directories': len(inventory['directories']), 'payloadBytes': total,
                  'allExplicitClosedScopesRetainedWithoutExclusions': True,
                  'allOriginalCollectionAndBothCompleteTarsRetained': True,
                  'sourceCopyBeforeAfterEqual': True, 'fullShaSizeModeUidGidEmptyDirectoryClosureVerified': True,
                  'rootActualReviewAndAllExistingProbeAttemptsRetained': True,'actualCloseProbeAttempts':len(probes), 'allKnownMarkerScansPassed': True,
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
