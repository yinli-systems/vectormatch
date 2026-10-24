"""Local data-only closed receipt verification, not a deletion or source test."""
from pathlib import Path
import hashlib,json,base64,ast
HERE=Path(__file__).resolve().parent;BASE=HERE.parent
P=BASE/'owner-native-retirement-preparation-r1'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()
def row(p):return dict(bytes=p.stat().st_size,sha256=sha(p))
def load(p):return json.loads(p.read_text())
def save(n,v):
    with (HERE/n).open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')

original=load(HERE/'REGISTRATION.json')['inputs']
for name,r in original.items():assert row(Path(name))==r
save('PREPARATION_ASSUMPTION_FAILURE_R1.json',dict(reviewerOnly=True,reviewedSourceUnchanged=True,
    failure='AssertionError before native/archive/readback checks: reviewer initially resolved ambiguous guardExecutionSha256 to the historical top-level GUARDS_EXECUTION.json',
    cause='SOURCE_FROZEN guardExecutionSha256 actually pins guards-r3/EXECUTION.json; historical top-level first failed attempt is intentionally retained',
    resolution='Use the exact SHA-matching actual third execution; preserve original registration and failure, do not edit reviewed inputs'))
c=load(P/'CONFIG.json');f=load(P/'SOURCE_FROZEN.json')
for n,k in [('CONFIG.json','configSha256'),('remote_retire.py','remoteSourceSha256'),('run.py','wrapperSourceSha256'),('guards-r3/EXECUTION.json','guardExecutionSha256')]:assert sha(P/n)==f[k]
assert set(c['arms'])=={'1','2','3','4'} and len(c['allClosedProcessIdentities'])==len({r['pid']for r in c['allClosedProcessIdentities']})==20
for r in c['allClosedProcessIdentities']:
    assert type(r['pid'])is int and r['pid']>1 and type(r['startTicks'])is int and r['startTicks']>0 and len(r['commandSha256'])==64
    if 'arguments'in r:assert hashlib.sha256(b'\0'.join(x.encode()for x in r['arguments'])+b'\0').hexdigest()==r['commandSha256']
for n,h in c['oldSources'].items():assert sha(BASE/'cpu-owner-poll-cloud-preparation-r1'/n)==h
pushpath=BASE/'owner-poll-abab-private-push-r1/PUSH_VERIFIED.json';push=load(pushpath)
assert sha(pushpath)==c['privatePushReceiptSha256'] and push['commit']==c['privatePushCommit']
assert push['passed'] and push['pushCompleted'] and push['remoteCommitVerified'] and push['visibility']=='private' and push['allFourFullOriginalEvidenceArchivesPushed']
result=load(P/'backup-and-restore-execution-r1/stdout.json');execution=load(P/'backup-and-restore-execution-r1/EXECUTION.json')
assert execution['exitCode']==0 and not execution['timedOut'] and execution['stdoutSha256']==sha(P/'backup-and-restore-execution-r1/stdout.json')
assert result['passed'] and result['noOldLeafRemoved'] and result['protectedBefore']==result['protectedAfter'] and set(result['arms'])==set(c['arms'])
assert result['protectedBefore']['manifestSha256']==c['protectedOriginalManifestSha256']=='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753'
assert sum(r['files']for r in result['protectedBefore']['nativeTrees'])==57 and result['protectedBefore']['postgres']['files']==989
readback=load(P/'control-readback-r1/stdout.json');assert readback['passed'] and readback['readOnly']
assert set(readback['files'])=={'REGISTRATION.json','BACKUP_AND_RESTORE_COMPLETE.json'}|{'RESTORE_PROOF_%s.json'%n for n in range(1,5)}
for name,r in readback['files'].items():
    raw=base64.b64decode(r['rawBase64'],validate=True);assert raw==(P/'control-readback-r1/files'/name).read_bytes()
    assert len(raw)==r['bytes'] and hashlib.sha256(raw).hexdigest()==r['sha256'] and r['mode']==0o600
assert load(P/'control-readback-r1/files/REGISTRATION.json')==c
assert load(P/'control-readback-r1/files/BACKUP_AND_RESTORE_COMPLETE.json')==result
arms={}
for key,config in c['arms'].items():
    archive_root=Path(config['privateArchivePath']).resolve();job=archive_root/'actual-collection/collection/raw-files/job'
    assert sha(archive_root/'CLOSED.json')==config['privateClosedSha256']==push['arms'][key]['closedSha256']
    assert sha(archive_root/'INVENTORY.json')==config['privateInventorySha256']==push['arms'][key]['inventorySha256']
    for n,h in config['controls'].items():assert sha(job/n)==h
    archive=archive_root/'actual-collection/collection/pilot-after-clean-stop.tar.gz';assert sha(archive)==config['nativeArchiveSha256']
    after=load(job/'after-clean-stop.json');inv=after['archive']['inventory'];proof_path=P/('control-readback-r1/files/RESTORE_PROOF_'+key+'.json');proof=load(proof_path);restored=proof['restoredInventory']
    assert proof['passed'] and proof['noApplicationStarted'] and proof['backupSha256']==config['nativeArchiveSha256']
    assert proof['backup']=='/workspace/vectormatch-cpu-archives/owner-poll-native-retirement-20261024-r1/arm-'+key+'.native.tar.gz'
    assert proof['originalInventorySha256']==hashlib.sha256(json.dumps(inv,sort_keys=True).encode()).hexdigest()
    assert set(inv['files'])==set(restored['files']) and inv['directories']==restored['directories']
    for name,r in inv['files'].items():assert all(restored['files'][name][k]==r[k]for k in ['bytes','sha256','mode','uid','gid'])
    assert restored['allocatedBytes']<=inv['allocatedBytes']+64*1024**2 and inv['logicalBytes']==restored['logicalBytes']
    r=result['arms'][key]
    assert r['nativeLeaf']==config['nativeLeaf']=='/opt/vectormatch-cpu/preparation/cpu-owner-poll-cloud-abab-r1/arm-'+key+'/idle-arm'
    assert r['restoreReceiptSha256']==sha(proof_path) and r['fullArchiveReadbackPassed'] and r['sparseRestoreProofPassed']
    arms[key]=dict(files=len(inv['files']),directories=len(inv['directories']),logicalBytes=inv['logicalBytes'],originalAllocatedBytes=inv['allocatedBytes'],restoreAllocatedBytes=restored['allocatedBytes'],originalCompressedArchive=row(archive),restoreProof=row(proof_path))
for attempt in ['guards-r1','guards-r2','guards-r3']:
    name='GUARDS_EXECUTION.json'if attempt=='guards-r1'else'EXECUTION.json';e=load(P/attempt/name)
    assert e['exitCode']==(0 if attempt=='guards-r3'else 1)
    stderr='guards.stderr'if attempt=='guards-r1'else'stderr';assert e['stderrSha256']==sha(P/attempt/stderr)
assert load(P/'guards-r3/EXECUTION.json')['testSourceSha256']==sha(P/'test_retirement_guards.py')
assert len([n for n in ast.walk(ast.parse((P/'test_retirement_guards.py').read_text()))if isinstance(n,ast.FunctionDef)and n.name.startswith('test_')])==6
assert 'Ran 6 tests'in(P/'guards-r3/stderr').read_text() and (P/'guards-r3/stderr').read_text().rstrip().endswith('OK')
for name,r in original.items():assert row(Path(name))==r
save('READBACK_R2.json',dict(passed=True,allReviewedInputsUnchanged=True,originalReviewedInputs=original,
    fourRestoredInventoriesAndLocalCompressedBodiesVerified=arms,twentyUniqueRegisteredPids=20,sixPureGuardsReportedPass=True,
    twoHistoricalGuardFailuresRetained=True,backupRestoreGateSha256=sha(P/'control-readback-r1/files/BACKUP_AND_RESTORE_COMPLETE.json'),
    privatePushReceipt=row(pushpath),noLiveRemoteStateReadByReviewer=True,noOldLeafRetiredByRepresentedAttempt=True,
    noReviewedSourceImportedOrExecuted=True,noTestsJavaSshGitByReviewer=True))
print(json.dumps(dict(passed=True,arms=arms,readback=row(HERE/'READBACK_R2.json'))))
