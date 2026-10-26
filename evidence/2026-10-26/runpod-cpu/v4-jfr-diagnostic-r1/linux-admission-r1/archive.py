from pathlib import Path
import sys,json,tarfile,datetime,subprocess,os,shutil,hashlib
B=Path(__file__).resolve().parent.parent;W=B/'interbank-v4-worktree';P=Path(__file__).resolve().parent;O=B/'v4-jfr-linux-admission-r1';assert not O.exists()
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import tree,sha,verify
ci=json.loads((B/'v4-jfr-forced-correctness-r1/RESULT.json').read_text());meta=json.loads((B/'v4-jfr-linux-metadata-execution-r1/ROOT_REVIEW.json').read_text());campaign=json.loads((B/'v4-jfr-controller-preparation-r1/CAMPAIGN.json').read_text());assert ci['passed']and meta['passed']and campaign['passed']and len(campaign['points'])==2
assert ci['sourceCommit']==campaign['sourceCommit']=='35dd60457b17e55f420bb1b97b4deeb0c1f2726f'
O.mkdir();names=['production-ci-attempt-23-collection-r1', 'production-ci-evidence-collection-preparation-r21', 'production-cpu-ci-controller-preparation-r23', 'production-cpu-ci-environment-r23', 'production-cpu-ci-registration-r23', 'production-ci-attempt-23-dispatch-r1', 'v4-jfr-forced-correctness-preparation-r1', 'v4-jfr-forced-correctness-r1', 'v4-jfr-artifact-preparation-r1', 'v4-jfr-ci23-jdk-image-equivalence-r1', 'v4-jfr-linux-metadata-preparation-r1', 'v4-jfr-linux-metadata-execution-r1', 'v4-jfr-controller-preparation-r1', 'v4-jfr-campaign-preparation-r1', 'v4-jfr-point-closure-preparation-r1', 'v4-jfr-native-archive-preparation-r1', 'v4-jfr-native-private-proof-preparation-r1', 'v4-jfr-analysis-preparation-r1', 'v4-jfr-analysis-local-selftest-r1', 'v4-jfr-analysis-local-selftest-r2', 'v4-jfr-analysis-linux-qualification-preparation-r1', 'v4-jfr-analysis-linux-qualification-r1']
scopes={n:B/n for n in names};inv={n:tree(p)for n,p in scopes.items()};bundle=O/'v4-jfr-linux-admission-ci23-complete-original-scopes-r1.tar.gz'
with tarfile.open(bundle,'x:gz')as t:
 for n,p in scopes.items():t.add(p,arcname='original/'+n)
review=verify(bundle,inv)
def write(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
write(O/'ORIGINAL_SCOPE_INVENTORIES.json',inv)
repo='yinli-systems/vectormatch';release_id=423510304;tag='evidence-private-20261025';env={**os.environ,'GODEBUG':'http2client=0'}
def api(path):return json.loads(subprocess.check_output(['gh','api',path],env=env))
assert api('repos/'+repo)['private'];release=api(f'repos/{repo}/releases/{release_id}');assert release['draft']and release['tag_name']==tag and not any(a['name']==bundle.name for a in release['assets'])
write(O/'UPLOAD_REGISTRATION.json',dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),assetName=bundle.name,bytes=bundle.stat().st_size,sha256=sha(bundle),oneUploadOnly=True,releaseId=release_id,repository=repo,noNativeBenchmarkExecuted=True))
with(O/'upload.stdout').open('xb')as out,(O/'upload.stderr').open('xb')as err:x=subprocess.run(['gh','release','upload',tag,str(bundle),'--repo',repo],stdout=out,stderr=err,timeout=600,env=env)
write(O/'UPLOAD_EXECUTION.json',dict(exitCode=x.returncode));assert x.returncode==0,'Query original asset name;no overwrite/blind upload retry'
release=api(f'repos/{repo}/releases/{release_id}');matches=[a for a in release['assets']if a['name']==bundle.name];assert len(matches)==1;asset=matches[0];assert asset['state']=='uploaded'and asset['size']==bundle.stat().st_size and asset['digest']=='sha256:'+sha(bundle)
write(O/'ASSET_METADATA.json',asset);download=O/'authenticated-admission-download.tar.gz'
with download.open('xb')as out,(O/'download.stderr').open('xb')as err:x=subprocess.run(['gh','api',f'repos/{repo}/releases/assets/'+str(asset['id']),'-H','Accept: application/octet-stream'],stdout=out,stderr=err,timeout=600,env=env)
assert x.returncode==0 and download.stat().st_size==bundle.stat().st_size and sha(download)==sha(bundle);assert verify(download,inv)==review
with tarfile.open(download)as t:
 for point in campaign['points']:
  name=f"point-{point['factor']}-{point['rate']}-{point['arm']}";root=B/'v4-jfr-controller-preparation-r1'/name;freeze=json.loads((root/'SOURCE_FREEZE.json').read_text());assert freeze==json.load(t.extractfile('original/v4-jfr-controller-preparation-r1/'+name+'/SOURCE_FREEZE.json'))
  for n,pin in freeze['files'].items():
   body=t.extractfile('original/v4-jfr-controller-preparation-r1/'+name+'/inputs/'+n).read();assert body==(root/'inputs'/n).read_bytes()and len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256']
download.unlink()
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),private=True,repository=repo,releaseId=release_id,releaseTag=tag,assetId=asset['id'],assetName=asset['name'],assetApiUrl=asset['url'],bytes=asset['size'],sha256=sha(bundle),completeAuthenticatedDownloadVerified=True,everyOriginalMemberVerified=review,allTwoFrozenPointInputsVerified=True,sourceCommit=ci['sourceCommit'],artifactFingerprint=campaign['artifactFingerprint'],linuxJavaTests=461,linuxPythonTests=202,linuxFailuresErrorsSkips=0,actualLoadedOrigins=24,jdkEqualFiles=454,nestedCiOriginalFiles=json.loads((B/'production-ci-attempt-23-collection-r1/VERIFIED.json').read_text())['allOriginalCollectedFilesVerified'],nativeNotYetExecuted=True)
write(O/'RESULT.json',result)
A=W/'evidence/2026-10-26/runpod-cpu/v4-jfr-diagnostic-r1/linux-admission-r1';assert not A.exists();A.mkdir(parents=True)
for name,path in [('ASSET_MANIFEST.json',O/'RESULT.json'),('ASSET_METADATA.json',O/'ASSET_METADATA.json'),('ORIGINAL_SCOPE_INVENTORIES.json',O/'ORIGINAL_SCOPE_INVENTORIES.json'),('CI23_RESULT.json',B/'v4-jfr-forced-correctness-r1/RESULT.json'),('JAR_INPUTS.json',B/'v4-jfr-artifact-preparation-r1/JAR_INPUTS.json'),('LINUX_METADATA.json',B/'v4-jfr-linux-metadata-execution-r1/actual-linux-observation.json'),('CAMPAIGN.json',B/'v4-jfr-controller-preparation-r1/CAMPAIGN.json'),('archive.py',Path(__file__))]:shutil.copy2(path,A/name)
freezes=A/'frozen-points';freezes.mkdir()
for point in campaign['points']:
 name=f"point-{point['factor']}-{point['rate']}-{point['arm']}";shutil.copy2(B/'v4-jfr-controller-preparation-r1'/name/'SOURCE_FREEZE.json',freezes/(name+'.json'))
(A/'README.md').write_text('# Qualified owned-node JFR diagnostic\n\nExact source35dd6045 is qualified by fresh CPU CI23:461Java/202Python,zero failures/errors/skips,11realPostgreSQLtests,actualfailover and web checks. All271JARclasses equal actual CI compiled bodies;core and hot matching/service code are unchanged. All454JDKbodies and24actualLinuxorigins are bound. The actual Linux factory verified the event-allowlist file and explicit node-argument template.\n\nTwo30-input freezes precede business profiling:500/s qualification,then4000/s diagnostic. Both retain leader0,sync2,CONTINUE,CLOSEDreads,agent100us,owner1ms,batch4,50uscoalescing,cut1536,read32/page32/chunk6144. Parent and six original/cold node lifetimes each require their own selected-event JFR. Profiling overhead is present;these points are not uninstrumented capacity comparisons or optimization promotions. Forty control tests must pass on Linux at staging. The standalone reader was tested on actual LinuxJFR output and locally rejects wrongPID,wrongroot and truncation.\n\nThe full private attachment retains every original CI/source/JAR/input/helper/selftest body and complete inventories. No live native profile is claimed by admission. See docs/V4_OWNED_JFR_PROTOCOL.md.\n')

write(A/'INVENTORY.json',tree(A));write(A/'CLOSED.json',dict(passed=True,atUTC=result['atUTC'],inventorySha256=sha(A/'INVENTORY.json'),assetId=result['assetId'],assetBytes=result['bytes'],assetSha256=result['sha256'],nativeNotYetExecuted=True))
print(json.dumps({k:v for k,v in result.items()if k!='everyOriginalMemberVerified'}))
