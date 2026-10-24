import json,hashlib,datetime,stat,sys,subprocess
from pathlib import Path
ROOT=Path.cwd();OUT=Path(__file__).resolve().parent;BASE=ROOT/'runtime/cloud/cpu-20261024';PREP=BASE/'cpu-idle-cloud-preparation-r2';C=PREP/'candidate'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def check(p,expected):
 assert p.is_file() and not p.is_symlink() and sha(p)==expected,str(p)
 return load(p)
def ref(p):return {'path':str(p.resolve()),'sha256':sha(p)}
candidate=check(C/'CANDIDATE.json','12a557de375174f97f77dd419a7ee6a9434c6d70f4f002b4e432346379c85d78')
release=check(C/'release/release.json','337741666b8936fa7b2c5c3bd81958baf2d7e0d888fa09eaaab7c985911c5c48')
assert candidate['releaseReady'] is False and release['releaseReady'] is False
for name,row in candidate['files'].items():
 f=C/name;assert f.stat().st_size==row['bytes'] and sha(f)==row['sha256'],name
frozen_path=PREP/'LOCAL_PREPARATION_FROZEN.json';frozen=load(frozen_path)
for name,row in frozen['sourceFiles'].items():
 f=PREP/name;assert not f.is_symlink() and f.stat().st_size==row['bytes'] and sha(f)==row['sha256'] and stat.S_IMODE(f.stat().st_mode)==row['mode'],name
assert release['controllerSha256']==sha(PREP/'cpu_idle_abab.py')=='07016602e61a9d415fdf968ada64c1ad6d40172926fd64ef44ab7c9dd124f98c'
assert sha(PREP/'shutdown_warning.py')=='bb8725c5bc560cc9a72c80a5c5d445373edbd0da91f2cccf41eb3550569319a9'
bindings=release['rootReview']['evidenceBindings']
proof={name:check(Path(v['path']),v['sha256']) for name,v in bindings.items()}
assert proof['rootSourceReview']['passed'] and proof['rootSourceReview']['actualFrozenXmlTestcases']==168
assert proof['rootNativeReview']['rootReviewPassed'] and proof['rootNativeReview']['warningTotal']==2 and proof['rootNativeReview']['qualifiedScope']=='Functional/canonical/raw closure only; not a performance point'
assert proof['unitCompletion']['exitCode']==0 and proof['unitCompletion']['sourceUnchanged'] is True
assert proof['localPostCloseAudit']['readOnlyAuditPassed'] and proof['localPostCloseAudit']['localFunctionalOnly']
obs=proof['linuxObservation'];assert obs['codeFingerprint']==release['codeFingerprint']=='f78025f91f9e43ad634840b400ab04ed4ae422597c35800984e434dbd1844c8f'
assert obs['profileFingerprint']==release['profileFingerprint'] and obs['plans']['8']==release['derivedPlan']
assert release['derivedPlan']['maximumRawTraceBytes']==38033404 and release['derivedPlan']['maximumAllocatedGrowthBytes']==589327865
linux=BASE/'idle-linux-metadata-r1';r=load(linux/'remote-receipt.json');assert proof['linuxSuccess']['passed'] and proof['linuxSuccess']['remoteReceiptSha256']==sha(linux/'remote-receipt.json')
assert r['execution']['exitCode']==0 and r['execution']['metadataJvmExited'] and not r['execution']['processIdentityObservationGap']
for k in ['javaExecutableSha256','jdkReleaseSha256']:assert r['registration'][k]==r['execution'][k+'After']==release[k]
for name in ['core','cluster']:
 assert not subprocess.check_output(['git','diff','7aa3e98ccc77c4be89f9f4b98c98d688c18e5d23','HEAD','--',name],text=True)
assert load(PREP/'guards-r1/completion.json')['passed'] is True
release['releaseReady']=True;release['status']='ROOT_FROZEN_REQUIRES_ACTUAL_LINUX_GUARDS_AND_READONLY_PREFLIGHT'
release['rootReview']['rootFreezeCompleted']=True
with (OUT/'release.json').open('x') as f:json.dump(release,f,indent=2,sort_keys=True);f.write('\n')
gate={'schemaVersion':2,'scope':'ROOT_VERIFIED_IDLE_CPU_RELEASE','rootVerified':True,'sourceCompiledNativeAndFocusedProofVerified':True,'sourceCommit':release['sourceCommit'],'preparationSha256':sha(frozen_path),'controllerSha256':release['controllerSha256'],'protectedManifestSha256':release['protectedOriginalState']['manifestSha256'],'candidate':ref(C/'CANDIDATE.json'),'candidateRelease':ref(C/'release/release.json'),'readyRelease':ref(OUT/'release.json'),'sourceReview':{k:bindings['rootSourceReview'][k] for k in ['path','sha256']},'nativeProof':{k:bindings['rootNativeReview'][k] for k in ['path','sha256']},'focusedGuardProof':{k:bindings['unitCompletion'][k] for k in ['path','sha256']},'preparation':ref(frozen_path),'preparationDirectory':str(PREP.resolve()),'linuxMetadata':{'success':ref(linux/'SUCCESS.json'),'remoteReceipt':ref(linux/'remote-receipt.json'),'observation':ref(linux/'actual-linux-distribution-observation.json')},'remoteHelper':ref(BASE/'remote.py'),'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'classificationReviewScope':'Two terminal follower EOS WARN preserved after matching checkpoint by log order; can initiate election; no SIGTERM causality','cpuBenchmarkRunByThisReceipt':False,'newResourceCreated':False}
assert gate['remoteHelper']['sha256']=='0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73'
with (OUT/'ROOT_FREEZE.json').open('x') as f:json.dump(gate,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({'rootFreezeSha256':sha(OUT/'ROOT_FREEZE.json'),'readyReleaseSha256':sha(OUT/'release.json'),'preparationSha256':sha(frozen_path),'sourceCount':len(frozen['sourceFiles']),'code':release['codeFingerprint']}))
