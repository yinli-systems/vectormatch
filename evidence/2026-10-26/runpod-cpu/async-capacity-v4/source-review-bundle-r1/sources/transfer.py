from pathlib import Path,PurePosixPath
import json,subprocess,hashlib,zipfile,os,datetime
B=Path(__file__).resolve().parent.parent;P=B/'source-review-bundle-r1';O=B/'source-review-bundle-private-transfer-r1';assert not O.exists();pin=json.loads((P/'BUNDLE.json').read_text());assert pin['passed'];bundle=Path(pin['path']);assert bundle.stat().st_size==pin['bytes']and hashlib.sha256(bundle.read_bytes()).hexdigest()==pin['sha256']
def api(path):return json.loads(subprocess.check_output(['gh','api',path]))
repo='yinli-systems/vectormatch';assert api('repos/'+repo)['private'];release=api('repos/'+repo+'/releases/423510304');assert release['draft']and not any(a['name']==bundle.name for a in release['assets'])
O.mkdir();(O/'UPLOAD_REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),assetName=bundle.name,bytes=pin['bytes'],sha256=pin['sha256'],oneUploadOnly=True,sourcePublicationCommit=pin['sourcePublicationCommit'],noCpuOrBusinessAction=True),indent=2))
with(O/'upload.stdout').open('xb')as out,(O/'upload.stderr').open('xb')as err:r=subprocess.run(['gh','release','upload','evidence-private-20261025',str(bundle),'--repo',repo],stdout=out,stderr=err,timeout=300)
(O/'UPLOAD_EXECUTION.json').write_text(json.dumps(dict(exitCode=r.returncode)));assert r.returncode==0,'Inspect same remote asset;no blind retry'
release=api('repos/'+repo+'/releases/423510304');assets=[a for a in release['assets']if a['name']==bundle.name];assert len(assets)==1;asset=assets[0];assert asset['state']=='uploaded'and asset['size']==pin['bytes']and asset['digest']=='sha256:'+pin['sha256'];(O/'ASSET_METADATA.json').write_text(json.dumps(asset,indent=2,sort_keys=True))
download=O/'authenticated-source-review.zip'
with download.open('xb')as out,(O/'download.stderr').open('xb')as err:r=subprocess.run(['gh','api','repos/'+repo+'/releases/assets/'+str(asset['id']),'-H','Accept: application/octet-stream'],stdout=out,stderr=err,timeout=300,env={**os.environ,'GODEBUG':'http2client=0'})
assert r.returncode==0 and download.stat().st_size==pin['bytes']and hashlib.sha256(download.read_bytes()).hexdigest()==pin['sha256']
manifest=json.loads((P/'vectormatch-review/SOURCE_MANIFEST.json').read_text());names=set(manifest['trackedFiles'])|{'SOURCE_MANIFEST.json','REVIEW_BUNDLE.md','BUNDLE_COMPILATION_VALIDATION.json'}
with zipfile.ZipFile(download)as z:
 assert z.testzip()is None and set(z.namelist())=={'vectormatch-review/'+n for n in names}
 for name in names:
  p=PurePosixPath(name);assert not p.is_absolute()and'..'not in p.parts
  body=z.read('vectormatch-review/'+name);assert body==(P/'vectormatch-review'/name).read_bytes()
  if name in manifest['trackedFiles']:
   v=manifest['trackedFiles'][name];assert len(body)==v['bytes']and hashlib.sha256(body).hexdigest()==v['sha256']and hashlib.sha1(b'blob '+str(len(body)).encode()+bytes([0])+body).hexdigest()==v['gitBlob']and (z.getinfo('vectormatch-review/'+name).external_attr>>16)&0o777==v['mode']
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),private=True,draft=True,repository=repo,releaseId=423510304,assetId=asset['id'],assetName=asset['name'],assetApiUrl=asset['url'],bytes=pin['bytes'],sha256=pin['sha256'],sourcePublicationCommit=pin['sourcePublicationCommit'],backendQualifiedCommit=pin['backendQualifiedCommit'],completeAuthenticatedDownloadVerified=True,allZipMemberBodiesAndOriginalGitBlobHashesVerified=len(names),coreAndClusterClassesByteEqualActualLinuxCi=265,tenCompilationTasksForced=True,functionalTestsNotRerun=True,noCpuOrBusinessAction=True)
(O/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+chr(10));download.unlink();print(json.dumps(result))
