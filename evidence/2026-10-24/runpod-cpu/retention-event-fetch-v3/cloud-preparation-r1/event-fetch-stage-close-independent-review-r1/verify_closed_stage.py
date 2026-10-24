"""Independent local byte/data review. No reviewed code imports, tests or remote access."""
from pathlib import Path,PurePosixPath
import ast,difflib,hashlib,json,stat,tarfile,zipfile,datetime,re
HERE=Path(__file__).resolve().parent;BASE=HERE.parent
ST=BASE/'cpu-event-fetch-stage-preparation-r1';CL=BASE/'cpu-event-fetch-close-preparation-r1'
ROOT=BASE/'event-fetch-root-release-freeze-r1';ACTUAL=BASE/'cpu-event-fetch-cloud-staging-r1'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def load(p):return json.loads(p.read_text())
def row(p):
    assert p.is_file() and not any(q.is_symlink() for q in [p]+list(p.parents)),str(p)
    return dict(bytes=p.stat().st_size,sha256=digest(p.read_bytes()),mode=stat.S_IMODE(p.stat().st_mode))
def save(n,v):
    with (HERE/n).open('x')as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')
def simple(p):return {k:row(p)[k]for k in('bytes','sha256')}

paths=sorted({p for root in(ST,CL,ROOT,ACTUAL)for p in root.rglob('*')if p.is_file()})
gate=load(ROOT/'ROOT_FREEZE.json');release=load(ROOT/'release/release.json');receipt=load(ACTUAL/'STAGE_SUCCESS.json')
prep=Path(gate['preparationDirectory']);frozen=load(prep/'LOCAL_PREPARATION_FROZEN.json')
paths+=sorted({prep/n for n in frozen['files']}|{Path(x['path'])for x in gate['artifacts'].values()}|{Path(gate['preparation']['path']),Path(gate['remoteHelper']['path'])})
before={str(p):row(p)for p in paths}
save('REGISTRATION.json',dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),inputs=before,
    reviewScope='Independent stage/launch/close source and closed stage bytes; no business/raw proof',noReviewedSourceImportsOrExecution=True))
assert row(ROOT/'ROOT_FREEZE.json')['sha256']=='52c82baef3b67647b09022dcff5063520d9b9343f6f3040c2b5d6521db7f828c'
assert row(ROOT/'release/release.json')['sha256']=='0ebad5d1ae1bd7900fc6dad7d78994d11ec3281f4077cfb7eba9b1bb3f506d59'
assert gate['rootVerified'] and gate['sourceUnitMetadataAndParserVerified'] and gate['firstCloudArmQualifiesNewArtifactFunctional'] and gate['newNativeBusinessQualifiedBeforeArm1'] is False
assert release['releaseReady'] is True and release['sourceCommit']==gate['sourceCommit']=='d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'
assert release['codeFingerprint']=='87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa'
assert gate['controllerSha256']==release['controllerSha256']=='eb84eed09cad46c5097c32d980a1629f7c7c7fec3759e904544f7ef9e91e3100'
assert row(prep/'LOCAL_PREPARATION_FROZEN.json')['sha256']==gate['preparation']['sha256']=='10a3f6e9144e1b6a54fef342e037d2de0987aee9dfddc6c7c5573f3e83ea56f6'
assert frozen['releaseReady'] is False and len(frozen['files'])==27
expected={n:row(prep/n)for n in frozen['files']}
for n,r in expected.items():assert r==frozen['files'][n]
expected['LOCAL_PREPARATION_FROZEN.json']=row(prep/'LOCAL_PREPARATION_FROZEN.json')
expected['release/release.json']=row(ROOT/'release/release.json')
expected['release/current-stopped-original-state.json']=row(ROOT/'release/current-stopped-original-state.json')
assert expected['release/current-stopped-original-state.json']['sha256']=='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753'
for remote,ref in gate['artifacts'].items():
    local=Path(ref['path']);r=row(local);assert r['sha256']==ref['sha256'] and simple(local)==release['artifacts'][remote]
    expected['release/lib/'+local.name]=r
for name,ref in gate['proofs'].items():
    p=Path(ref['path']);r=row(p);assert r['sha256']==ref['sha256']
    assert release['evidenceReferences'][name]==dict(path='/opt/vectormatch-cpu/preparation/cpu-event-fetch-cloud-abab-r1/release/proofs/'+name+'.json',**simple(p))
    expected['release/proofs/'+name+'.json']=r
assert len(expected)==39 and sum(r['bytes']for r in expected.values())<=32*1024**2
assert receipt['stagedFiles']==expected and set(receipt['localSourcePaths'])==set(expected)
assert receipt['rootVerifiedFreezeSha256']==row(ROOT/'ROOT_FREEZE.json')['sha256'] and receipt['releaseSha256']==row(ROOT/'release/release.json')['sha256']
assert (ACTUAL/'root-freeze.json').read_bytes()==(ROOT/'ROOT_FREEZE.json').read_bytes()
assert (ACTUAL/'release.json').read_bytes()==(ROOT/'release/release.json').read_bytes()
assert receipt['passed'] and receipt['readOnlyPreflightPassed'] and receipt['applicationStarted'] is False and receipt['resourceCreated'] is False
assert receipt['controllerSha256']==release['controllerSha256'] and receipt['remotePrep']=='/opt/vectormatch-cpu/preparation/cpu-event-fetch-cloud-abab-r1'
for n,r in expected.items():assert row(Path(receipt['localSourcePaths'][n]))==r
assert row(ACTUAL/'stage-bundle.tar.gz')['sha256']==receipt['stageBundleSha256']
seen=set()
with tarfile.open(ACTUAL/'stage-bundle.tar.gz','r:gz')as t:
    for m in t:
        path=PurePosixPath(m.name);assert m.isfile() and m.name in expected and m.name not in seen
        assert str(path)==m.name and not path.is_absolute()and'..'not in path.parts
        raw=t.extractfile(m).read();assert dict(bytes=len(raw),sha256=digest(raw),mode=m.mode)==expected[m.name];seen.add(m.name)
assert seen==set(expected)
assert load(ACTUAL/'stage.stdout.json')==dict(passed=True,files=expected)
final=load(ACTUAL/'final-source-readback.stdout.json')
assert final==dict(passed=True,allStagedInputsUnchangedAfterGuardsAndReadonlyPreflight=True,files=expected)
assert load(ACTUAL/'metadata-prerequisite.stdout')==dict(passed=True,metadataJvmStrictlyPidAbsent=True,jdkPinsMatch=True)
groups=[dict(cwd='.',modules=['test_event_delta'],scope='controller',tests=19),dict(cwd='long-parser',modules=['test_long_contract','test_phase_baseline','test_event_fetch'],scope='long-parser',tests=42)]
assert receipt['linuxGuardCommands']==gate['linuxGuardCommands']==frozen['linuxGuardCommands']==groups and receipt['linuxGuardTests']==61
for label,count in [('controller',19),('long-parser',42)]:
    text=(ACTUAL/('linux-'+label+'-guards.stderr')).read_text()
    assert re.search(r'Ran '+str(count)+r' tests in ',text) and text.rstrip().endswith('OK')
pre=load(ACTUAL/'read-only-preflight.stdout')
assert pre['passed'] and pre['noJavaStarted'] and pre['singleManualArmOnly'] and pre['eventFetchCount']==16
assert pre['arm']==1 and pre['ownerPollMaximumParkNs']==1000000 and pre['serverDriverMaximumParkNs']==100000
assert pre['minimumInitialFreeBytes']==2116076873 and pre['maximumAllocatedGrowthBytes']==773899593
assert pre['idle']['noUnownedJavaVmOrPostgres'] and pre['protectedOriginal']['passed']
assert pre['protectedOriginal']['manifestSha256']=='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753'
assert sum(x['files']for x in pre['protectedOriginal']['nativeTrees'])==57 and pre['protectedOriginal']['postgres']['files']==989
proof=load(ROOT/'release/proofs/rootEvidenceReview.json');policy=load(ROOT/'release/proofs/campaignQualificationPolicy.json')
assert proof['passed'] and proof['firstCloudArmQualifiesNewArtifactFunctional'] and proof['newNativeBusinessQualifiedBeforeArm1'] is False
assert proof['nativeOrPerformanceResultClaimed'] is False and policy['configurationOnly'] and policy['newNativeBusinessQualifiedBeforeArm1'] is False
assert proof['proofBindings']=={k:{x:r[x]for x in('bytes','sha256')}for k,r in release['evidenceReferences'].items()if k!='rootEvidenceReview'}
assert set(proof['prerequisiteReviewInputs'])=={'unitCompletion','unitRootReview','independentSourceReview'}
for key in ['controllerRootReview','parserRootReview','linuxMetadataIndependentReview']:
    ref=proof[key];assert row(Path(ref['path']))['sha256']==ref['sha256']
helpers=load(ST/'HELPERS_FROZEN.json')
for n,r in helpers['sources'].items():assert simple(ST/n)==r
close=load(CL/'SOURCE_FROZEN.json')
for n,r in close['sourceFiles'].items():assert simple(CL/n)==r
assert close['executedSourceSha256']=='67fcfe5bd15efb8bdc488d25b156534b34878ce6584e5cb2ec3cf95ebeb2b5f2'
assert close['actualRemoteExecutionPerformed'] is False and close['closedControllerGateScope']=='ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_CONTROLLER'
for directory,count,zipname in [(ST,29,'sources.zip'),(CL,18,'source.zip')]:
    registration=load(directory/'guards-r1/REGISTRATION.json');completion=load(directory/'guards-r1/COMPLETION.json')
    assert completion['exitCode']==0 and completion['allInputsUnchanged']
    for n,r in registration['sourceFiles'].items():assert simple(directory/n)==r
    with zipfile.ZipFile(directory/'guards-r1'/zipname)as z:
        for n,r in registration['sourceFiles'].items():assert digest(z.read(n))==r['sha256']
    assert completion['stderrSha256']==row(directory/'guards-r1/stderr')['sha256']
    text=(directory/'guards-r1/stderr').read_text();assert re.search(r'Ran '+str(count)+r' tests in ',text)and text.rstrip().endswith('OK')
for directory,oldname,newname,diffname in [(ST,'stage_owner_poll.py','stage_event_fetch.py','stage_event_fetch.py.diff'),(ST,'launch_owner_poll.py','launch_event_fetch.py','launch_event_fetch.py.diff'),(CL,'inspect_closed_owner_arm.py','inspect_closed_event_arm.py','SOURCE_DIFF.patch')]:
    diff=''.join(difflib.unified_diff((directory/'baseline'/oldname).read_text().splitlines(True),(directory/newname).read_text().splitlines(True),fromfile='baseline/'+oldname,tofile=newname))
    assert diff==(directory/diffname).read_text()
after={str(p):row(p)for p in paths};assert before==after
save('READBACK_COMPLETE.json',dict(passed=True,reviewedInputsUnchanged=True,inputsBefore=before,inputsAfter=after,
    stage39FullTarMembersVerified=True,stagedRows=expected,stageReceipt=simple(ACTUAL/'STAGE_SUCCESS.json'),
    rootFreeze=simple(ROOT/'ROOT_FREEZE.json'),readyRelease=simple(ROOT/'release/release.json'),
    pureStageLaunchGuards=29,pureCloseGuards=18,actualLinuxControllerGuards=19,actualLinuxParserGuards=42,
    metadataStrictPidAbsenceAndJdkPinsReported=True,readOnlyPreflight=pre,
    firstNewNativeBusinessArmNotYetQualified=True,actualCloseProbeExecuted=False,
    reviewDidNotImportOrExecuteReviewedSources=True,noTestsSshJavaRawOrGitByReviewer=True))
print(json.dumps(dict(passed=True,reviewedInputs=len(before),stagedFiles=len(expected),stageBundleBytes=(ACTUAL/'stage-bundle.tar.gz').stat().st_size)))
