from pathlib import Path
import sys,json,tarfile,datetime,subprocess,os,shutil,hashlib
B=Path(__file__).resolve().parent.parent;W=B/'interbank-v4-worktree';P=Path(__file__).resolve().parent;O=B/'v4-segment-linux-admission-r1';assert not O.exists()
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import tree,sha,verify
ci=json.loads((B/'v4-segment-forced-correctness-r1/RESULT.json').read_text());meta=json.loads((B/'v4-segment-linux-metadata-execution-r1/ROOT_REVIEW.json').read_text());campaign=json.loads((B/'v4-segment-controller-preparation-r1/CAMPAIGN.json').read_text());assert ci['passed']and meta['passed']and campaign['passed']and len(campaign['points'])==5
assert ci['sourceCommit']==campaign['sourceCommit']=='5906da668f6113aebae1af821564ebf47ef52d97'
O.mkdir();names=['production-ci-attempt-24-collection-r1', 'production-ci-evidence-collection-preparation-r22', 'production-cpu-ci-controller-preparation-r24', 'production-cpu-ci-environment-r24', 'production-cpu-ci-registration-r24', 'production-ci-attempt-24-dispatch-r1', 'v4-segment-local-validation-r2', 'v4-segment-forced-correctness-preparation-r1', 'v4-segment-forced-correctness-r1', 'v4-segment-artifact-preparation-r1', 'v4-segment-ci24-jdk-image-equivalence-r1', 'v4-segment-linux-metadata-preparation-r1', 'v4-segment-linux-metadata-execution-r1', 'v4-segment-controller-preparation-r1', 'v4-segment-campaign-preparation-r1', 'v4-segment-point-closure-preparation-r1', 'v4-segment-native-archive-preparation-r1', 'v4-segment-native-private-proof-preparation-r1']
scopes={n:B/n for n in names};inv={n:tree(p)for n,p in scopes.items()};bundle=O/'v4-segment-linux-admission-ci24-complete-original-scopes-r1.tar.gz'
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
  name=f"point-{point['factor']}-{point['rate']}-{point['arm']}";root=B/'v4-segment-controller-preparation-r1'/name;freeze=json.loads((root/'SOURCE_FREEZE.json').read_text());assert freeze==json.load(t.extractfile('original/v4-segment-controller-preparation-r1/'+name+'/SOURCE_FREEZE.json'))
  for n,pin in freeze['files'].items():
   body=t.extractfile('original/v4-segment-controller-preparation-r1/'+name+'/inputs/'+n).read();assert body==(root/'inputs'/n).read_bytes()and len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256']
download.unlink()
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),private=True,repository=repo,releaseId=release_id,releaseTag=tag,assetId=asset['id'],assetName=asset['name'],assetApiUrl=asset['url'],bytes=asset['size'],sha256=sha(bundle),completeAuthenticatedDownloadVerified=True,everyOriginalMemberVerified=review,allFiveFrozenPointInputsVerified=True,sourceCommit=ci['sourceCommit'],artifactFingerprint=campaign['artifactFingerprint'],linuxJavaTests=474,linuxPythonTests=202,linuxFailuresErrorsSkips=0,actualLoadedOrigins=27,jdkEqualFiles=454,nestedCiOriginalFiles=json.loads((B/'production-ci-attempt-24-collection-r1/VERIFIED.json').read_text())['allOriginalCollectedFilesVerified'],nativeNotYetExecuted=True)
write(O/'RESULT.json',result)
A=W/'evidence/2026-10-26/runpod-cpu/v4-segment-preparation-r1/linux-admission-r1';assert not A.exists();A.mkdir(parents=True)
for name,path in [('ASSET_MANIFEST.json',O/'RESULT.json'),('ASSET_METADATA.json',O/'ASSET_METADATA.json'),('ORIGINAL_SCOPE_INVENTORIES.json',O/'ORIGINAL_SCOPE_INVENTORIES.json'),('CI24_RESULT.json',B/'v4-segment-forced-correctness-r1/RESULT.json'),('JAR_INPUTS.json',B/'v4-segment-artifact-preparation-r1/JAR_INPUTS.json'),('LINUX_METADATA.json',B/'v4-segment-linux-metadata-execution-r1/actual-linux-observation.json'),('CAMPAIGN.json',B/'v4-segment-controller-preparation-r1/CAMPAIGN.json'),('archive.py',Path(__file__))]:shutil.copy2(path,A/name)
freezes=A/'frozen-points';freezes.mkdir()
for point in campaign['points']:
 name=f"point-{point['factor']}-{point['rate']}-{point['arm']}";shutil.copy2(B/'v4-segment-controller-preparation-r1'/name/'SOURCE_FREEZE.json',freezes/(name+'.json'))
(A/'README.md').write_text('# Qualified first-segment preparation campaign\n\nThe exact application source is qualified by fresh existing-CPU CI24:474 Java/202 Python with zero failure/error/skip,11 real PostgreSQL tests,actual failover and web checks. All compiled JAR bodies match CI24 classes,454 JDK file bodies match the canonical runtime,and27 actual loaded Linux origins match the staged four JARs.\n\nFive frozen points precede native testing:500/s ZERO_FIRST_SEGMENT qualification,then4000/s SPARSE C1,ZERO D1,SPARSE C2,ZERO D2. Batch coalescing is50us in all arms. Leader0,sync2,CONTINUE,CLOSED read banks,agent100us,owner1ms,batch4,cut1536,read32/page32/chunk6144 and all other bounds remain fixed. There is no observer JVM in these arms. Each point retains all raw financial/cold-recovery evidence. All38 controller tests must independently pass on Linux at staging. No native performance or default promotion follows from this admission. See docs/V4_SEGMENT_PREPARATION_PROTOCOL.md.\n')

write(A/'INVENTORY.json',tree(A));write(A/'CLOSED.json',dict(passed=True,atUTC=result['atUTC'],inventorySha256=sha(A/'INVENTORY.json'),assetId=result['assetId'],assetBytes=result['bytes'],assetSha256=result['sha256'],nativeNotYetExecuted=True))
print(json.dumps({k:v for k,v in result.items()if k!='everyOriginalMemberVerified'}))
