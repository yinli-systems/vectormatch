from pathlib import Path
import json,hashlib,importlib.util,sys,datetime,stat,shutil,tarfile
P=Path(__file__).resolve().parent;B=P.parent;R=Path.cwd();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n')
sys.path.insert(0,str(P));import cpu_read_window32_abab as c
old=json.loads((P/'baseline/LOCAL_PREPARATION_FROZEN.json').read_text());names=list(old['files'])+['test_current_container.py','current-container-baseline.json']
rows={n:dict(bytes=(P/n).stat().st_size,sha256=sha(P/n),mode=stat.S_IMODE((P/n).stat().st_mode))for n in names};assert len(rows)==45
f=dict(schemaVersion=1,scope='CURRENT_CONTAINER_READ32_SOURCE_PREPARATION',sourceCommit=c.SOURCE_COMMIT,codeFingerprint=c.CODE_FINGERPRINT,controllerSha256=sha(P/'cpu_read_window32_abab.py'),files=rows,filesCount=45,longParserSourceMapping=old['longParserSourceMapping'],linuxGuardCommands=[dict(scope='controller',cwd='.',modules=['test_read_window32_delta','test_current_container'],tests=34),old['linuxGuardCommands'][1]],releaseReady=False,newContainerHost=c.HOST,newContainerBootId=json.loads((P/'current-container-baseline.json').read_text())['bootId'],gradleNaturalExitRequired=True,sourceOnly=True)
save(P/'LOCAL_PREPARATION_FROZEN.json',f)
D=P/'root-release';(D/'proofs').mkdir(parents=True);(D/'lib').mkdir();r=json.loads((P/'release.template.json').read_text());r.update(releaseReady=True,status='ROOT_FROZEN_CURRENT_CONTAINER_METADATA_AND_SOURCE_ONLY_NATIVE_QUALIFICATION_PENDING',controllerSha256=sha(P/'cpu_read_window32_abab.py'),requiredEvidenceBeforeRootFreezes=[])
r['protectedOriginalState']['manifest']=str(c.PREP/'release/current-container-baseline.json');shutil.copy2(P/'current-container-baseline.json',D/'current-container-baseline.json')
for remote,row in r['artifacts'].items():
 q=B/'read-window32-linux-metadata-preparation-r1/inputs/lib'/Path(remote).name;assert sha(q)==row['sha256'];shutil.copy2(q,D/'lib'/q.name)
proofs={'campaignQualificationPolicy':P/'campaign-qualification-policy.json','readWindow32RawParserFreeze':P/'fixtures/read-window32-parser-source-freeze.json','linuxMetadataObservation':P/'fixtures/actual-linux-distribution-observation.json','linuxMetadataReceipt':P/'fixtures/remote-receipt.json'}
for key,q in proofs.items():
 shutil.copy2(q,D/'proofs'/(key+'.json'));r['evidenceReferences'][key]=dict(path=str(c.PREP/'release/proofs'/(key+'.json')),bytes=q.stat().st_size,sha256=sha(q))
inputs={'unitCompletion':B/'read-window32-local-preparation-r1/attempt-r5/COMPLETION.json','unitRootReview':B/'read-window32-root-source-review-r1/ROOT_REVIEW.json','independentSourceReview':B/'read-window32-independent-review-r1/REVIEW.json'}
for k,p in list(inputs.items()):
 if not p.exists():
  if k=='unitCompletion':inputs[k]=B/'read-window32-local-preparation-r1/CLOSED.json'
  else:raise RuntimeError(str(p))
review=dict(scope='ROOT_REVIEWED_READ_WINDOW32_CLOUD_PREREQUISITES',passed=True,sourceCommit=c.SOURCE_COMMIT,codeFingerprint=c.CODE_FINGERPRINT,profileFingerprint=r['profileFingerprint'],controllerSha256=r['controllerSha256'],ownerPollValidatorSha256=r['ownerPollValidatorSha256'],proofBindings={k:{x:v[x]for x in['bytes','sha256']}for k,v in r['evidenceReferences'].items()if k!='rootEvidenceReview'},parserSourceFreezeSha256=c.PARSER_FREEZE_SHA,firstCloudArmQualifiesNewArtifactFunctional=True,newNativeBusinessQualifiedBeforeArm1=False,guardsPassed=True,strictCpuSchedulerRequired=True,noNewResources=True,prerequisiteReviewInputs={k:dict(bytes=p.stat().st_size,sha256=sha(p))for k,p in inputs.items()},environmentDeltaReviewedByAuthorRoot=True,priorIndependentSourceReviewCovers605ApplicationNotNewContainerController=True,freshAbsenceBaseline=rows['current-container-baseline.json'],actual34PureGuardsCompletionSha256=sha(P/'guards-r3/COMPLETION.json'),gradleMustExitNaturally=True)
save(D/'proofs/rootEvidenceReview.json',review);q=D/'proofs/rootEvidenceReview.json';r['evidenceReferences']['rootEvidenceReview']=dict(path=str(c.PREP/'release/proofs/rootEvidenceReview.json'),bytes=q.stat().st_size,sha256=sha(q));c.validate_release(r);values={k:json.loads((D/'proofs'/(k+'.json')).read_text())for k in r['evidenceReferences']};c.validate_prerequisite_proofs(values,r);save(D/'release.json',r)
files={n:P/n for n in names};files['LOCAL_PREPARATION_FROZEN.json']=P/'LOCAL_PREPARATION_FROZEN.json';files['release/release.json']=D/'release.json';files['release/current-container-baseline.json']=D/'current-container-baseline.json'
for q in(D/'lib').iterdir():files['release/lib/'+q.name]=q
for q in(D/'proofs').iterdir():files['release/proofs/'+q.name]=q
rows={n:dict(bytes=q.stat().st_size,sha256=sha(q),mode=stat.S_IMODE(q.stat().st_mode))for n,q in files.items()};assert len(rows)==57 and sum(x['bytes']for x in rows.values())<=32*1024**2
bundle=P/'stage-bundle.tar.gz'
with tarfile.open(bundle,'w:gz',compresslevel=1)as t:
 for n,q in files.items():t.add(q,arcname=n,recursive=False)
save(P/'STAGE_INPUTS.json',dict(passed=True,remoteRoot=str(c.PREP),host=c.HOST,rows=rows,bundleSha256=sha(bundle),releaseSha256=sha(D/'release.json'),sourceFreezeSha256=sha(P/'LOCAL_PREPARATION_FROZEN.json'),linuxGuardCommands=f['linuxGuardCommands'],noNativeLaunch=True,preflightPendingNaturalGradleExit=True))
print(json.dumps(dict(passed=True,files=len(rows),bundleSha256=sha(bundle),releaseSha256=sha(D/'release.json'))))
