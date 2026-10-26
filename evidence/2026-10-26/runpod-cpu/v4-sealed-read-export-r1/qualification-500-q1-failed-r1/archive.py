from pathlib import Path
import json,hashlib,tarfile,subprocess,os,shutil,importlib.util,datetime
B=Path(__file__).resolve().parent;W=B/'interbank-v4-worktree';C=B/'v4-sealed-qualification-500-q1-closure-r1';O=B/'v4-sealed-qualification-500-q1-failed-archive-r1';assert not O.exists()
s=importlib.util.spec_from_file_location('scope',B/'dispatch-capacity-scope-tar-preparation-r1/scope_tar.py');scope=importlib.util.module_from_spec(s);s.loader.exec_module(scope)
m=json.loads((C/'remote-manifest.json').read_text());assert m['passed']and not m['nativePassed'];original=C/'complete-native-point-and-independent-audit.tar.gz';assert scope.sha(original)==m['archive']['sha256'];review=scope.verify(original,m['sourceScopes']);assert review==m['everyOriginalMemberVerified']
O.mkdir();bundle=O/'v4-sealed-qualification-500-q1-failed-originals-r1.tar.gz';shutil.copy2(original,bundle);repo='yinli-systems/vectormatch';release=423510304;tag='evidence-private-20261025';env={**os.environ,'GODEBUG':'http2client=0'}
def api(path):return json.loads(subprocess.check_output(['gh','api',path],env=env))
assert api('repos/'+repo)['private'];r=api('repos/'+repo+'/releases/'+str(release));assert r['draft']and r['tag_name']==tag and not any(a['name']==bundle.name for a in r['assets'])
(O/'UPLOAD_REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),assetName=bundle.name,bytes=bundle.stat().st_size,sha256=scope.sha(bundle),oneUploadOnly=True,nativePassed=False),indent=2)+'\n')
with(O/'upload.stdout').open('xb')as out,(O/'upload.stderr').open('xb')as err:r=subprocess.run(['gh','release','upload',tag,str(bundle),'--repo',repo],stdout=out,stderr=err,timeout=600,env=env)
(O/'UPLOAD_EXECUTION.json').write_text(json.dumps(dict(exitCode=r.returncode))+'\n');assert r.returncode==0,'Query same asset;no blind reupload'
r=api('repos/'+repo+'/releases/'+str(release));matches=[a for a in r['assets']if a['name']==bundle.name];assert len(matches)==1;a=matches[0];assert a['state']=='uploaded'and a['size']==bundle.stat().st_size and a['digest']=='sha256:'+scope.sha(bundle)
download=O/'authenticated-failed-originals.tar.gz'
with download.open('xb')as out,(O/'download.stderr').open('xb')as err:r=subprocess.run(['gh','api','repos/'+repo+'/releases/assets/'+str(a['id']),'-H','Accept: application/octet-stream'],stdout=out,stderr=err,timeout=300,env=env)
assert r.returncode==0 and download.stat().st_size==bundle.stat().st_size and scope.sha(download)==scope.sha(bundle);assert scope.verify(download,m['sourceScopes'])==review;download.unlink()
A=W/'evidence/2026-10-26/runpod-cpu/v4-sealed-read-export-r1/qualification-500-q1-failed-r1';assert not A.exists();A.mkdir(parents=True)
manifest=dict(archiveVerified=True,nativePassed=False,notQualifiedCapacity=True,private=True,draft=True,repository=repo,releaseId=release,assetId=a['id'],assetName=a['name'],assetApiUrl=a['url'],bytes=a['size'],sha256=scope.sha(bundle),completeAuthenticatedDownloadAndEveryMemberVerified=True,sourceCommit=m['sourceCommit'],artifactFingerprint=m['artifactFingerprint'],originalScopeReview=review)
(A/'ASSET_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n');(A/'ORIGINAL_SCOPE_INVENTORIES.json').write_text(json.dumps(m['sourceScopes'],indent=2)+'\n')
for n in ['remote-manifest.json','VERIFIED.json','REGISTRATION.json','EXECUTION.json']:shutil.copy2(C/n,A/n)
with tarfile.open(bundle)as t:
 for member,name in [('FAILED.json','FAILED.json'),('state/completion.json','NATIVE_COMPLETION.json'),('state/failure.txt','NATIVE_FAILURE.txt'),('state/load/load-result.json','UNQUALIFIED_LOAD_RESULT.json')]:
  (A/name).write_bytes(t.extractfile('original/point/'+member).read())
(A/'README.md').write_text('This failed500/s qualification remains unqualified.10000 synthetic orders received replies with0 unknown/notSent,but the legacy terminal verifier compared Cluster-only header associations9727 with the combined callback count11120.1393 actual direct DATA deliveries account for the difference. Full financial replay,snapshots and cold recovery did not run after that gate failed. No throughput,p99 or improvement claim is made from this point. The original CPU/local/private complete archive and all failed records are preserved;no in-place retry occurred.\n')
shutil.copy2(__file__,A/'archive.py');(A/'INVENTORY.json').write_text(json.dumps(scope.tree(A),indent=2)+'\n');(A/'CLOSED.json').write_text(json.dumps(dict(archiveVerified=True,nativePassed=False,inventorySha256=scope.sha(A/'INVENTORY.json'),assetId=a['id']),indent=2)+'\n');(O/'VERIFIED.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest))
