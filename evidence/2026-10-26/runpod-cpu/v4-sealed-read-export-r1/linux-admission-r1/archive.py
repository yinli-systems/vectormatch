from pathlib import Path
import sys,json,tarfile,datetime,subprocess,os,shutil,hashlib
B=Path(__file__).resolve().parent.parent;W=B/'interbank-v4-worktree';P=Path(__file__).resolve().parent;O=B/'v4-sealed-linux-admission-r1';assert not O.exists()
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import tree,sha,verify
ci=json.loads((B/'v4-sealed-corrected-forced-correctness-r1/RESULT.json').read_text());meta=json.loads((B/'v4-sealed-corrected-linux-metadata-execution-r1/ROOT_REVIEW.json').read_text());campaign=json.loads((B/'v4-sealed-controller-preparation-r2/CAMPAIGN.json').read_text());assert ci['passed']and meta['passed']and campaign['passed']and len(campaign['points'])==5
assert ci['sourceCommit']==campaign['sourceCommit']=='78a420cefb5cc11e18b2f6f32ee2421073424d25'
O.mkdir();names=['production-ci-attempt-26-collection-r1', 'production-ci-evidence-collection-preparation-r24', 'production-cpu-ci-controller-preparation-r26', 'production-cpu-ci-environment-r26', 'production-cpu-ci-registration-r26', 'production-ci-attempt-26-dispatch-r1', 'v4-sealed-corrected-forced-correctness-preparation-r1', 'v4-sealed-corrected-forced-correctness-r1', 'v4-sealed-corrected-artifact-preparation-r1', 'v4-sealed-corrected-linux-metadata-preparation-r1', 'v4-sealed-corrected-linux-metadata-execution-r1', 'v4-sealed-corrected-ci-native-collection-preparation-r1', 'v4-sealed-corrected-ci-native-collection-r1', 'v4-sealed-controller-preparation-r2', 'v4-sealed-campaign-preparation-r2', 'v4-sealed-point-closure-preparation-r1', 'v4-sealed-native-archive-preparation-r1', 'v4-sealed-native-private-proof-preparation-r1', 'v4-sealed-corrected-source-private-git-proof-r1']
scopes={n:B/n for n in names};inv={n:tree(p)for n,p in scopes.items()};bundle=O/'v4-sealed-linux-admission-ci26-complete-original-scopes-r1.tar.gz'
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
  name=f"point-{point['factor']}-{point['rate']}-{point['arm']}";root=B/'v4-sealed-controller-preparation-r2'/name;freeze=json.loads((root/'SOURCE_FREEZE.json').read_text());assert freeze==json.load(t.extractfile('original/v4-sealed-controller-preparation-r2/'+name+'/SOURCE_FREEZE.json'))
  for n,pin in freeze['files'].items():
   body=t.extractfile('original/v4-sealed-controller-preparation-r2/'+name+'/inputs/'+n).read();assert body==(root/'inputs'/n).read_bytes()and len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256']
download.unlink()
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),private=True,repository=repo,releaseId=release_id,releaseTag=tag,assetId=asset['id'],assetName=asset['name'],assetApiUrl=asset['url'],bytes=asset['size'],sha256=sha(bundle),completeAuthenticatedDownloadVerified=True,everyOriginalMemberVerified=review,allFiveFrozenPointInputsVerified=True,sourceCommit=ci['sourceCommit'],artifactFingerprint=campaign['artifactFingerprint'],linuxJavaTests=544,linuxPythonTests=207,linuxFailuresErrorsSkips=0,actualLoadedOrigins=58,jdkEqualFiles=454,nestedCiOriginalFiles=json.loads((B/'production-ci-attempt-26-collection-r1/VERIFIED.json').read_text())['allOriginalCollectedFilesVerified'],nativeNotYetExecuted=True)
write(O/'RESULT.json',result)
A=W/'evidence/2026-10-26/runpod-cpu/v4-sealed-read-export-r1/linux-admission-r1';assert not A.exists();A.mkdir(parents=True)
for name,path in [('ASSET_MANIFEST.json',O/'RESULT.json'),('ASSET_METADATA.json',O/'ASSET_METADATA.json'),('ORIGINAL_SCOPE_INVENTORIES.json',O/'ORIGINAL_SCOPE_INVENTORIES.json'),('CI26_RESULT.json',B/'v4-sealed-corrected-forced-correctness-r1/RESULT.json'),('JAR_INPUTS.json',B/'v4-sealed-corrected-artifact-preparation-r1/JAR_INPUTS.json'),('LINUX_METADATA.json',B/'v4-sealed-corrected-linux-metadata-execution-r1/actual-linux-observation.json'),('CAMPAIGN.json',B/'v4-sealed-controller-preparation-r2/CAMPAIGN.json'),('archive.py',Path(__file__))]:shutil.copy2(path,A/name)
freezes=A/'frozen-points';freezes.mkdir()
for point in campaign['points']:
 name=f"point-{point['factor']}-{point['rate']}-{point['arm']}";shutil.copy2(B/'v4-sealed-controller-preparation-r2'/name/'SOURCE_FREEZE.json',freezes/(name+'.json'))
(A/'README.md').write_text('# Qualified sealed-history export experiment\n\nFresh full CPU CI26 verifies source78a420ce:544 Java/207 Python,11 real PostgreSQL tests,actual failover and Web checks,zero failures/errors/skips.307 application class bodies match actual CI,454 JDK files match the benchmark image,and58 actual Linux loaded origins match the staged JARs. Both real three-JVM routes include complete original frames,financial replay,snapshots and cold restoration. The old CI25 ingress-position label was corrected before any capacity point;both ingress and ordinary offer positions are explicitly not consensus commit positions.\n\nRegistered candidate500/s qualification,then4000/s CLUSTER C1,DIRECT_UDP D1,CLUSTER C2,DIRECT_UDP D2. Both arms enable identical servers and descriptor handshakes;only the historical-read route changes. Leader0,sync2,CONTINUE,CLOSED reads,agent100us,owner1ms,batch4/50us,cut1536,read32/page32/chunk6144. Business,PrepareArchive and destructive ACKs retain the replicated path and forced/readback prefix receipts.52 controller tests must pass again on Linux before launch.30 complete inputs per point are frozen. No capacity,production,SLA,independent-physical-host or100M claim follows from admission.\n')

write(A/'INVENTORY.json',tree(A));write(A/'CLOSED.json',dict(passed=True,atUTC=result['atUTC'],inventorySha256=sha(A/'INVENTORY.json'),assetId=result['assetId'],assetBytes=result['bytes'],assetSha256=result['sha256'],nativeNotYetExecuted=True))
print(json.dumps({k:v for k,v in result.items()if k!='everyOriginalMemberVerified'}))
