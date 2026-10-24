import json,hashlib,stat,shutil,sys,importlib.util,datetime
from pathlib import Path
sys.dont_write_bytecode=True
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';P=B/'cpu-long-cuts-cloud-preparation-r1';S=B/'cpu-long-cuts-stage-preparation-r1';O=B/'long-cloud-root-release-freeze-r1';PREP='/opt/vectormatch-cpu/preparation/cpu-long-cuts-cloud-r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def js(p):return json.loads(p.read_text())
def need(v,m):
 if not v:raise AssertionError(m)
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def ref(p):return {'path':str(p),'sha256':sha(p)}
fp=P/'LOCAL_PREPARATION_FROZEN.json';need(sha(fp)=='f4025d2ce6c6ca7d94ebe612f561890192c87deb57fc91169f3ebd0f0b1c6107','final preparation pin');f=js(fp)
need(sha(P/'cpu_long_cuts.py')=='1d4103af9dde51d190dad2eec80117622563a2736ac41121131db56db5a23447','controller pin')
for n,row in f['files'].items():
 p=P/n;mode=int(row['mode'],8)if isinstance(row['mode'],str)else row['mode'];s=p.lstat();need(stat.S_ISREG(s.st_mode)and s.st_nlink==1 and s.st_size==row['bytes']and sha(p)==row['sha256']and stat.S_IMODE(s.st_mode)==mode,'source '+n)
need(sha(S/'HELPERS_FROZEN.json')=='d4b8a9c58c35f44b96b2f194b995a7e45b15ebc5189f8eac10863ca1faa70617'and sha(S/'stage_long_cuts.py')=='d300bac7a0ba6323c14e6650a10ef42ad8ca499f7bf6b0e74b0516602dd0dcf1','stage helper pins')
need(sha(B/'cpu-long-cuts-peer-review-r2/REVIEW.json')=='22f9eadaff86b1e32941808e14ff89cbe015e27587c0c2d9499e333001e548c7','corrected peer review')
need(sha(B/'long-cuts-root-native-review-r1/ROOT_REVIEW.json')=='55b3bf21ea23dca8a34bb7a1c2baaf7235cce2ddbf6ec38100fe5a0edc0dd49d','root native proof')
sourceReview=B/'long-cuts-root-source-review-r1/ROOT_REVIEW.json';need(sha(sourceReview)=='a9561e676b19892a58590b16fc51b6e63962261aede70858fa0d48b0d8bd23db','root source/artifact proof')
proof_sources={'longRawAudit':B/'long-native-audit-preparation-r1/LOCAL_FUNCTIONAL_AUDIT_COMPLETE.json','longRawParserFreeze':B/'long-native-audit-preparation-r1/SOURCE_FROZEN.json','linuxMetadataObservation':P/'metadata-preparation/actual-linux-distribution-observation.json','linuxMetadataReceipt':P/'metadata-preparation/remote-receipt.json'}
expected={'longRawAudit':'d62912c9eccad0f6b070658d39626b587c5c017543f456ed9043ac710c5da21b','longRawParserFreeze':'1fdec3e1bd4253e6eb11f32bc8bae5fbab53cd5531ffb8dec75c0cfb31e8c7b3','linuxMetadataObservation':'78bb2a6a46acfadde6888184caf507da934c2d22b1a532116c7d94a488795c27','linuxMetadataReceipt':'f136046368c57d2998b50854e2b46e5dba3ebfbc639b66ef7cd87476d5824b5f'}
for k,p in proof_sources.items():need(sha(p)==expected[k],'proof '+k)
need(not O.exists(),'exclusive new freeze');O.mkdir(mode=0o700);(O/'release/proofs').mkdir(parents=True);(O/'release/lib').mkdir()
shutil.copy2(Path(__file__),O/'freeze-source.py')
save(O/'REGISTRATION.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Root local ready release and immutable proof binding; no SSH/Java/resource/benchmark started','preparationSha256':sha(fp),'sourceCommit':'bcf49c10b77a14708b53d3fc6c115a6a3b834408','controllerSha256':sha(P/'cpu_long_cuts.py'),'preserveFalseTemplate':True})
release=js(P/'release.template.json');need(release['releaseReady']is False,'template remainsfalse');release['releaseReady']=True;release['status']='ROOT_REVIEWED_SINGLE_CPU_LONG_CUTS_FINITE_OBSERVATION'
release['javaExecutableSha256']='9cad3f2620d3ef2ed10b26f922af7e773d54fdaa05f615d6d6df014f3fec4155';release['jdkReleaseSha256']='f83f6dcc966043c93cd498ac8e7ee7c310852074970d62c702e4ad2710002898';release['controllerSha256']=sha(P/'cpu_long_cuts.py')
proofrefs={}
for k,p in proof_sources.items():
 target=O/'release/proofs'/ (k+'.json');shutil.copy2(p,target);need(sha(target)==expected[k],'copiedproof');proofrefs[k]=ref(target);release['evidenceReferences'][k]={'path':PREP+'/release/proofs/'+k+'.json','bytes':target.stat().st_size,'sha256':sha(target)}
review={'scope':'ROOT_REVIEWED_LONG_NATIVE_CLOUD_PREREQUISITES','passed':True,'sourceCommit':release['sourceCommit'],'codeFingerprint':release['codeFingerprint'],'profileFingerprint':release['profileFingerprint'],'controllerSha256':release['controllerSha256'],'sourceReviewSha256':sha(sourceReview),'nativeReviewSha256':sha(B/'long-cuts-root-native-review-r1/ROOT_REVIEW.json'),'proofBindings':{k:{'bytes':release['evidenceReferences'][k]['bytes'],'sha256':release['evidenceReferences'][k]['sha256']}for k in proof_sources},'guardsPassed':True,'strictCpuSchedulerRequired':True,'noNewResources':True}
reviewpath=O/'release/proofs/rootEvidenceReview.json';save(reviewpath,review);proofrefs['rootEvidenceReview']=ref(reviewpath);release['evidenceReferences']['rootEvidenceReview']={'path':PREP+'/release/proofs/rootEvidenceReview.json','bytes':reviewpath.stat().st_size,'sha256':sha(reviewpath)}
artifacts={};jarroot=B/'retention-long-cuts-v3-worktree/runtime/long-cuts-local-validation/native-r1/input-state/lib'
for remote,row in release['artifacts'].items():
 source=jarroot/Path(remote).name;need(source.stat().st_size==row['bytes']and sha(source)==row['sha256'],'actualjar');target=O/'release/lib'/source.name;shutil.copy2(source,target);need(sha(target)==row['sha256'],'copyactualjar');artifacts[remote]=ref(target)
protected=B/'cpu-idle-cloud-preparation-r2/candidate/release/current-stopped-original-state.json';need(sha(protected)=='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753','original protected');protectedtarget=O/'release/current-stopped-original-state.json';shutil.copy2(protected,protectedtarget)
releasepath=O/'release/release.json';save(releasepath,release)
gate=js(S/'ROOT_FREEZE.template.json');gate.update(rootVerified=True,sourceCompiledNativeAndFocusedProofVerified=True,preparationDirectory=str(P),preparation=ref(fp),controllerSha256=release['controllerSha256'],readyRelease=ref(releasepath),artifacts=artifacts,proofs=proofrefs,linuxGuardCommands=f['linuxGuardCommands'],status='ROOT_FROZEN_NO_CLOUD_STAGE_OR_BENCHMARK_STARTED',protectedManifest=ref(protectedtarget))
gatepath=O/'ROOT_FREEZE.json';save(gatepath,gate)
sys.path.insert(0,str(S));import stage_long_cuts as stage
checked=stage.validate_inputs(gatepath,sha(gatepath))
need(len(checked['rows'])==39,'actual expected27source +freeze/release/protected/4jars/5proof=39')
save(O/'ROOT_FREEZE_COMPLETE.json',{'passed':True,'rootFreezeSha256':sha(gatepath),'readyReleaseSha256':sha(releasepath),'rootEvidenceReviewSha256':sha(reviewpath),'preparationSha256':sha(fp),'controllerSha256':release['controllerSha256'],'sourceStageRows':len(checked['rows']),'sourceLogicalBytes':sum(r['bytes']for r in checked['rows'].values()),'linuxGuardTestsRequired':sum(g['tests']for g in f['linuxGuardCommands']),'localSemanticAndGuardSourceBindingsPassed':True,'applicationStarted':False,'remoteStageExecuted':False,'originalTemplateStillFalse':js(P/'release.template.json')['releaseReady']is False})
print(json.dumps(js(O/'ROOT_FREEZE_COMPLETE.json')))
