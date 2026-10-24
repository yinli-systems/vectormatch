"""Root source/actual-unit/metadata/parser review and benchmark-only release freeze."""
from pathlib import Path
import ast, datetime, hashlib, importlib.util, json, re, shutil, stat, sys
HERE=Path(__file__).resolve().parent
BASE=HERE.parent
PREP=BASE/'cpu-event-fetch-cloud-preparation-r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')
def pin(p):return dict(path=str(p.resolve()),sha256=sha(p))
frozen=load(PREP/'LOCAL_PREPARATION_FROZEN.json')
assert sha(PREP/'LOCAL_PREPARATION_FROZEN.json')=='10a3f6e9144e1b6a54fef342e037d2de0987aee9dfddc6c7c5573f3e83ea56f6'
for name,row in frozen['files'].items():
    p=PREP/name;s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_size==row['bytes'] and stat.S_IMODE(s.st_mode)==row['mode'] and sha(p)==row['sha256']
old=ast.parse((PREP/'baseline/cpu_owner_poll_abab.py').read_text());new=ast.parse((PREP/'cpu_event_fetch_abab.py').read_text())
def definitions(tree):return {x.name:ast.dump(x,include_attributes=False) for x in tree.body if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
a,b=definitions(old),definitions(new);unchanged=sorted(n for n in a.keys()&b.keys() if a[n]==b[n]);delta=load(PREP/'SOURCE_DELTA.json')
assert unchanged==sorted(delta['unchangedFunctionOrClassNames']) and len(unchanged)==32
for name,count in [('guards-r1',19),('guards-parser-r1',42)]:
    done=load(PREP/name/'completion.json');text=(PREP/name/'stderr').read_text()
    assert done['exitCode']==0 and done['allInputsUnchanged'] and re.search(r'Ran '+str(count)+r' tests in ',text) and text.rstrip().endswith('OK')
for path in [BASE/'event-fetch-root-source-review-r1/ROOT_REVIEW.json',BASE/'event-fetch-independent-source-review-r1/REVIEW.json',BASE/'event-fetch-metadata-root-review-r1/ROOT_REVIEW.json',BASE/'event-fetch-linux-metadata-root-review-r1/ROOT_REVIEW.json',BASE/'event-fetch-linux-metadata-independent-review-r1/REVIEW.json',BASE/'event-fetch-parser-root-review-r1/ROOT_REVIEW.json']:
    assert load(path)['passed']
unit=BASE/'event-fetch-page-v3-worktree/runtime/event-fetch-local-validation/units-r1/completion.json'
assert sha(unit)=='6d03ee607f24203cadac9a9c81d4019294c99735cd3b8418d2a6926a84576ed3'
assert load(BASE/'event-fetch-root-source-review-r1/ROOT_REVIEW.json')['actualDistinctTests']==47
root_review=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='ROOT_EVENT_FETCH_CONTROLLER_AND_PREREQUISITE_SOURCE_REVIEW',sourceSha256=sha(PREP/'cpu_event_fetch_abab.py'),sourceFreezeSha256=sha(PREP/'LOCAL_PREPARATION_FROZEN.json'),unchangedDefinitions=unchanged,pureControllerGuards=19,pureParserGuards=42,fullChangedProductionFunctionsReviewed=True,selectedPages=[16,32,16,32],ownerPollCapFixedNs=1000000,driverCapFixedNs=100000,sameArtifactRequired=True,firstCloudArmMustQualifyNewNativeArtifact=True,previousArtifactCannotQualifyNewArtifact=True,strictCpuSchedulerAndFullRawGateRequired=True,normalExitOwnershipProtectionAndFiniteResourceBoundsPreserved=True,newNativeBusinessQualified=False,performanceClaimed=False)
save(HERE/'ROOT_REVIEW.json',root_review)
release_dir=HERE/'release';proof_dir=release_dir/'proofs';proof_dir.mkdir(parents=True)
sources={'campaignQualificationPolicy':PREP/'campaign-qualification-policy.json','eventFetchRawParserFreeze':BASE/'event-fetch-long-parser-preparation-r1/SOURCE_FROZEN.json','linuxMetadataObservation':BASE/'event-fetch-linux-metadata-preparation-r1/actual-linux-distribution-observation.json','linuxMetadataReceipt':BASE/'event-fetch-linux-metadata-preparation-r1/remote-receipt.json'}
for key,path in sources.items():shutil.copy2(path,proof_dir/(key+'.json'))
release=load(PREP/'release.template.json');bindings={key:dict(bytes=path.stat().st_size,sha256=sha(path)) for key,path in sources.items()}
unit_inputs={'unitCompletion':unit,'unitRootReview':BASE/'event-fetch-root-source-review-r1/ROOT_REVIEW.json','independentSourceReview':BASE/'event-fetch-independent-source-review-r1/REVIEW.json'}
proof=dict(scope='ROOT_REVIEWED_EVENT_FETCH_CLOUD_PREREQUISITES',passed=True,sourceCommit=release['sourceCommit'],codeFingerprint=release['codeFingerprint'],profileFingerprint=release['profileFingerprint'],controllerSha256=frozen['controllerSha256'],ownerPollValidatorSha256=release['ownerPollValidatorSha256'],prerequisiteReviewInputs={key:dict(bytes=path.stat().st_size,sha256=sha(path)) for key,path in unit_inputs.items()},proofBindings=bindings,parserSourceFreezeSha256=sha(sources['eventFetchRawParserFreeze']),firstCloudArmQualifiesNewArtifactFunctional=True,newNativeBusinessQualifiedBeforeArm1=False,guardsPassed=True,strictCpuSchedulerRequired=True,noNewResources=True,controllerRootReview=pin(HERE/'ROOT_REVIEW.json'),linuxMetadataIndependentReview=pin(BASE/'event-fetch-linux-metadata-independent-review-r1/REVIEW.json'),parserRootReview=pin(BASE/'event-fetch-parser-root-review-r1/ROOT_REVIEW.json'),nativeOrPerformanceResultClaimed=False)
save(proof_dir/'rootEvidenceReview.json',proof);sources['rootEvidenceReview']=proof_dir/'rootEvidenceReview.json'
release['controllerSha256']=frozen['controllerSha256'];release['releaseReady']=True;release['status']='ROOT_VERIFIED_BENCHMARK_SOURCE_READY_FIRST_NATIVE_QUALIFICATION_PENDING'
for key,path in sources.items():release['evidenceReferences'][key]=dict(path='/opt/vectormatch-cpu/preparation/cpu-event-fetch-cloud-abab-r1/release/proofs/'+key+'.json',bytes=path.stat().st_size,sha256=sha(path))
protected=BASE/'owner-cloud-root-release-freeze-r1/release/current-stopped-original-state.json';assert sha(protected)=='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753';shutil.copy2(protected,release_dir/protected.name)
sys.path.insert(0,str(PREP))
try:
    spec=importlib.util.spec_from_file_location('root_event_fetch_release_definition',PREP/'cpu_event_fetch_abab.py');controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller)
    controller.validate_release(release);controller.validate_prerequisite_proofs({k:load(p) for k,p in sources.items()},release)
finally:sys.path.pop(0)
save(release_dir/'release.json',release)
jars=BASE.parents[2]/'evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/local-unit-validation-r1/installed-jars'
artifacts={}
for remote,row in release['artifacts'].items():
    path=jars/Path(remote).name;assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'];artifacts[remote]=pin(path)
gate=dict(schemaVersion=2,scope='ROOT_VERIFIED_EVENT_FETCH_CPU_RELEASE',rootVerified=True,sourceUnitMetadataAndParserVerified=True,firstCloudArmQualifiesNewArtifactFunctional=True,newNativeBusinessQualifiedBeforeArm1=False,sourceCommit=release['sourceCommit'],controllerSha256=frozen['controllerSha256'],protectedManifestSha256=sha(protected),preparationDirectory=str(PREP.resolve()),preparation=pin(PREP/'LOCAL_PREPARATION_FROZEN.json'),readyRelease=pin(release_dir/'release.json'),protectedManifest=pin(release_dir/protected.name),artifacts=artifacts,proofs={k:pin(proof_dir/(k+'.json')) for k in sources},remoteHelper=pin(BASE/'remote.py'),linuxGuardCommands=frozen['linuxGuardCommands'],status='ROOT_VERIFIED_NOT_STAGED_NOT_LAUNCHED')
save(HERE/'ROOT_FREEZE.json',gate)
print(json.dumps(dict(passed=True,releaseSha256=sha(release_dir/'release.json'),rootFreezeSha256=sha(HERE/'ROOT_FREEZE.json'),newNativeBusinessQualified=False)))
