"""Archive closed explicit source/control scopes only. No business audit, tests, Java, SSH or Git."""
from pathlib import Path,PurePosixPath
import argparse,datetime,hashlib,importlib.util,io,json,shutil,stat,tarfile,zipfile
HERE=Path(__file__).resolve().parent;BASE=HERE.parent;WORKSPACE=BASE.parents[2]
PRIMITIVES=BASE/'event-fetch-unit-proof-archive-r1/archive.py'
LIMIT=128*1024**2;FLOOR=1024**3
spec=importlib.util.spec_from_file_location('closed_unit_archive_primitives',PRIMITIVES)
primitive=importlib.util.module_from_spec(spec);spec.loader.exec_module(primitive)

def require(value,message):
    if not value:raise AssertionError(message)
def save(path,value):primitive.save(path,value)
def load(path):return json.loads(path.read_text())
def pin(path):return dict(path=str(path),**primitive.row(path))

def scan_all(path,label,*,budget,depth=0,data=None):
    """Reuse known-marker streaming primitive; additionally recurse TAR inside ZIP and vice versa."""
    require(depth<=6,'Known-marker nested container depth6 cap')
    size=len(data)if data is not None else path.stat().st_size
    budget[0]+=size;require(budget[0]<=512*1024**2,'Bounded512MiB total scan object bytes')
    if data is None:
        with path.open('rb')as f:primitive.scan_stream(f,label)
    else:primitive.scan_stream(io.BytesIO(data),label)
    name=path.name if path is not None else label.rsplit('!',1)[-1]
    is_tar=name.endswith(('.tar.gz','.tgz','.tar'));is_zip=name.endswith(('.jar','.zip'))
    if not is_tar and not is_zip:return
    require(size<=LIMIT,'Bounded nested container bytes')
    raw=data if data is not None else path.read_bytes()
    if is_zip:
        with zipfile.ZipFile(io.BytesIO(raw))as z:
            seen=set();infos=z.infolist();require(len(infos)<=16384,'Finite nested ZIP members')
            for info in infos:
                primitive.safe_member(info.filename);require(info.filename not in seen,'Duplicate nested ZIP member');seen.add(info.filename)
                if info.is_dir():continue
                require(info.file_size<=32*1024**2,'Bounded32MiB nested ZIP payload')
                scan_all(None,label+'!'+info.filename,budget=budget,depth=depth+1,data=z.read(info))
    else:
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r|*')as t:
            seen=set()
            for member in t:
                primitive.safe_member(member.name);require(member.name not in seen,'Duplicate nested TAR member');seen.add(member.name)
                require(len(seen)<=16384,'Finite nested TAR members')
                if member.isdir():continue
                require(member.isfile()and member.size<=32*1024**2,'Bounded regular32MiB nested TAR payload')
                scan_all(None,label+'!'+member.name,budget=budget,depth=depth+1,data=t.extractfile(member).read())

def readme(kind):
    if kind=='retirement':return '''# Closed duplicate-native retirement evidence

This archive copies the completed source/control evidence for retiring only the four old synthetic owner-poll arm-N/idle-arm leaves. Both actual stages, initial six and final eight JSON/control readbacks, raw stdout/stderr, exact configuration/source, all reviews and private-push verification receipts are retained. Two pure test-preparation failures, the actual third six-guard PASS and the independent reviewer's wrong-top-level-guard-path assumption failure remain unchanged. No tests or source were rerun or edited during this archive.

Each of the four leaves had130files/16directories. Its real Linux full sparse restore reproduced complete payload SHA/size/mode/uid/gid/empty-directory closure from the original closed inventory; original allocation about150MB and restored allocation about180MB remain recorded, within the unchanged64MiB margin. Before/after original57 native andPG989 full protection receipts are equal. Twenty historical PIDs were strictly absent at the recorded gates. Root's explicit second stage removed exactly those four duplicate leaves and retained all wrapper controls and original compressed TARs.

The final readback rehashed eight compressed archive bodies: for each arm, its original /opt TAR and its /workspace backup have the same per-arm SHA (the four different arms have different SHAs). Immediate retirement reported2,715,795,456bytes free; subsequent read-only observation recorded2,715,791,360bytes. These are timestamped observations, not a current reserved-space promise. Same-host workspace copies do not independently establish storage durability.

The full original native/TAR evidence already exists in the private-pushed four sibling cloud-arm-N-r1 archives and is not duplicated here. EXTERNAL_ORIGINAL_ARCHIVE_REFERENCES.json pins all four CLOSED.json and INVENTORY.json bodies; see [arm1 CLOSED](../cloud-arm-1-r1/CLOSED.json), [arm2 CLOSED](../cloud-arm-2-r1/CLOSED.json), [arm3 CLOSED](../cloud-arm-3-r1/CLOSED.json), [arm4 CLOSED](../cloud-arm-4-r1/CLOSED.json) and each sibling INVENTORY.json.

Local archive only: no SSH/JVM/business/raw audit/test/Git action, new resources, other workload action or additional deletion. Original absolute historical paths and generation-time fields are retained. Full copy before/after SHA/bytes/mode/uid/gid/empty-directory closure and nested known-marker checks are recorded; known-marker review is bounded and is not universal secret detection.
'''
    return '''# Closed Event Fetch cloud preparation and source-stage evidence

This archive contains only the explicitly closed source/controller/root-release/stage/close-probe/collector preparation scopes, actual source-stage logs, independent/root reviews, local first-arm configuration creation and prior private metadata/parser push receipt. It contains no later launch directory, live execution register, actual new business/native run or cloud collection. The capture boundary is the copied receipts: actual stage was read-only and the local first-arm config receipt is dated2026-10-24T11:14:49.116049+00:00.

The source/controller is d923/code87a7, with owner fixed1ms/driver100us and manual pages16/32/16/32 overLONG33792@500. Root52c/ready0eb and actual stage bind39source/JAR/proof rows,19+42actual Linux pure guards, default read-only preflight, canonical JDK and metadata PID strict absence, protected57/PG989 baseline and finite disk reserve. The stage started no business. Stage/launch29 and close18pure guard captures, collector22 and parser42pure guards, original baselines, source ZIPs, patches, failed historical attempts and all root/independent receipts are preserved.

FirstNativeNotYetRun/pending/not-staged/sourceOnly fields describe their original generation time and are deliberately not rewritten. The root policy explicitly does not claim new native-business qualification before arm1; first16 must later qualify the new artifact by full actual raw/canonical/three-checkpoint/owner/archive and independent root review before32. An actual stage or a pure-guard PASS is not benchmark/native/performance proof. No later result is imported into this preparation archive.

Only closed explicit directory allowlists were copied. The source freeze, final ready release and actual configuration retain original absolute paths; preserving those byte pins does not claim the archived scripts can be executed as-is from their new location. All regular files, mode/uid/gid, empty directories and nested ZIP/JAR/TAR payloads are included and checked. No source/test/state rewriting, active-scope read, benchmark re-audit, SSH/JVM/test/Git action, resource creation or deletion occurred. Known-marker review names concrete marker classes and does not prove universal secret absence.
'''

def run(kind):
    plan=load(HERE/'COPY_PLAN.json');item=plan['archives'][kind];target=Path(item['target'])
    require(not target.exists(),'New archive only; preserve any earlier attempt')
    require(shutil.disk_usage(WORKSPACE).free>=FLOOR+LIMIT,'1GiB floor plus128MiB copy reserve')
    require(item['sourceBytes']<=LIMIT-16*1024**2,'Payload plus16MiB derived metadata reserve within128MiB')
    for name,scope in item['sourceTrees'].items():require(primitive.snapshot(Path(scope['source']))==scope['inventory'],'Closed source beforecopy differs: '+name)
    attempt=HERE/(kind+'-attempt-r1');attempt.mkdir()
    save(attempt/'REGISTRATION.json',dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),archiveKind=kind,copyPlanSha256=primitive.sha(HERE/'COPY_PLAN.json'),archiverSourceSha256=primitive.sha(Path(__file__)),primitivesSourceSha256=primitive.sha(PRIMITIVES),sourceTrees=list(item['sourceTrees']),sourceBytes=item['sourceBytes'],target=str(target),localFreeBytesBefore=shutil.disk_usage(WORKSPACE).free,noBusinessRawAuditTestsJavaSshGit=True))
    try:
        target.mkdir(parents=True)
        for name,scope in item['sourceTrees'].items():primitive.copy_tree(Path(scope['source']),target/name,scope['inventory'])
        save(target/'SOURCE_COPY_BINDINGS.json',dict(passed=True,sourceTrees=item['sourceTrees'],allShaBytesModesUidGidAndEmptyDirectoriesVerified=True,noExclusions=True))
        if kind=='retirement':
            refs={}
            for arm,scope in item['externalOriginalArchives'].items():
                for name,r in scope['files'].items():require(primitive.row(Path(r['path']))=={k:r[k]for k in('bytes','sha256','mode','uid','gid')},'External original reference drift')
                refs[arm]=scope
            save(target/'EXTERNAL_ORIGINAL_ARCHIVE_REFERENCES.json',dict(scope='References only; complete original native/TAR payloads retained in existing private sibling archives',originalsDuplicatedHere=False,arms=refs))
        with(target/'README.md').open('x')as f:f.write(readme(kind))
        archiver=target/'archiver';archiver.mkdir()
        for source,name in [(Path(__file__),'archive.py'),(PRIMITIVES,'snapshot_copy_marker_primitives.py'),(HERE/'COPY_PLAN.json','COPY_PLAN.json'),(HERE/'REGISTRATION.json','REGISTRATION.json'),(attempt/'REGISTRATION.json','ATTEMPT_REGISTRATION.json')]:shutil.copy2(source,archiver/name)
        original=primitive.snapshot(target);require(sum(r['bytes']for r in original['files'].values())<=LIMIT,'Archive pre-scan cap')
        primitive.SCANNED.clear();primitive.HITS.clear();budget=[0]
        for p in sorted(target.rglob('*')):
            if p.is_file():scan_all(p,str(p.relative_to(target)),budget=budget)
        save(target/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',dict(passed=not primitive.HITS,namedMarkerClasses=sorted(primitive.MARKERS),hits=primitive.HITS,scannedObjects=len(primitive.SCANNED),scannedObjectBytes=budget[0],allCopiedRawFileBytesAndNestedZipJarTarPayloadsScanned=True,maximumContainerDepth=6,maximumNestedMemberBytes=32*1024**2,boundedKnownMarkerReviewNotUniversalSecretAbsence=True,scanned=primitive.SCANNED))
        require(not primitive.HITS,'Known markers found; preserve exact archive for rootreview')
        after={}
        for name,scope in item['sourceTrees'].items():
            current=primitive.snapshot(Path(scope['source']));require(current==scope['inventory'],'Closed source aftercopy differs: '+name);after[name]=current
        save(target/'SOURCE_AFTER_COPY.json',dict(passed=True,sourceTrees=after,allOriginalSourcesUnchanged=True))
        inventory=primitive.snapshot(target);total=sum(r['bytes']for r in inventory['files'].values());require(total<=LIMIT,'128MiB final archive cap')
        save(target/'INVENTORY.json',dict(schemaVersion=1,excludedSelfAndClosure=['INVENTORY.json','CLOSED.json'],files=inventory['files'],directories=inventory['directories'],payloadFiles=len(inventory['files']),payloadBytes=total,fullModeUidGidAndEmptyDirectoryClosure=True))
        for name,r in inventory['files'].items():require(primitive.row(target/name)==r,'Final archived payload drift')
        save(target/'CLOSED.json',dict(schemaVersion=1,passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),archiveKind=kind,inventorySha256=primitive.sha(target/'INVENTORY.json'),payloadFiles=len(inventory['files']),directories=len(inventory['directories']),payloadBytes=total,sourceCopyBeforeAfterEqual=True,allCopiedShaBytesModeUidGidAndEmptyDirectoryClosureVerified=True,allExplicitClosedScopesIncludedWithoutExclusions=True,knownMarkerReviewPassed=True,noBusinessRawAuditTestsJavaSshGitExecuted=True,noActiveLaunchOrBusinessDirectoryRead=True,performanceClaimed=False,closureExcludes=['INVENTORY.json','CLOSED.json']))
        result=dict(passed=True,kind=kind,inventorySha256=primitive.sha(target/'INVENTORY.json'),closedSha256=primitive.sha(target/'CLOSED.json'),payloadFiles=len(inventory['files']),directories=len(inventory['directories']),payloadBytes=total,scannedObjects=len(primitive.SCANNED),freeBytesAfter=shutil.disk_usage(WORKSPACE).free)
        save(attempt/'COMPLETION.json',result);print(json.dumps(result))
    except BaseException as error:
        import traceback
        save(attempt/'FAILED.json',dict(passed=False,error=repr(error),traceback=traceback.format_exc(),allPartialArchiveAndSourcesRetained=True,noAutomaticRetry=True));raise

if __name__=='__main__':
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--archive',choices=['retirement','event-preparation'],required=True);run(p.parse_args().archive)
