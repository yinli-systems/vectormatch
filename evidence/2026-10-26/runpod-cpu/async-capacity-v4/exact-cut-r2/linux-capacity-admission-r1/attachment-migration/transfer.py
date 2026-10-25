from pathlib import Path
import sys,json,subprocess,shutil,os,datetime
B=Path(__file__).resolve().parent.parent;W=B/'async-maintenance-v4-worktree';O=B/'async-v4-cut-gate-admission-private-asset-r1';assert not O.exists()
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import verify,sha
commit='071800a99a6d9a1c575a77c860e25505c3122ca2';prefix='evidence/2026-10-26/runpod-cpu/async-capacity-v4/exact-cut-r2/linux-capacity-admission-r1'
def git(*args):return subprocess.check_output(['git','-C',str(W),*args])
def api(path):return json.loads(subprocess.check_output(['gh','api',path]))
repo='yinli-systems/vectormatch';assert api('repos/'+repo)['private'];release=api('repos/'+repo+'/releases/423510304');assert release['draft']and release['tag_name']=='evidence-private-20261025'
closed=json.loads(git('show',commit+':'+prefix+'/CLOSED.json'));inventories=json.loads(git('show',commit+':'+prefix+'/ORIGINAL_SCOPE_INVENTORIES.json'))
source=W/prefix/'complete-linux-correctness-artifact-and-capacity-admission.tar.gz';assert source.stat().st_size==closed['archiveBytes']and sha(source)==closed['archiveSha256']
assert git('hash-object',str(source)).decode().strip()==git('rev-parse',commit+':'+prefix+'/'+source.name).decode().strip()
assert verify(source,inventories)==closed['everyOriginalMemberVerified']
O.mkdir();name='async-v4-cut-gate-linux-admission-original-complete-r1.tar.gz';assert not any(a['name']==name for a in release['assets']);bundle=O/name;shutil.copy2(source,bundle)
(O/'UPLOAD_REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceGitCommit=commit,sourceGitPath=prefix+'/'+source.name,assetName=name,bytes=bundle.stat().st_size,sha256=sha(bundle),oneUploadOnly=True,avoidRepeatingLargeBlobInFutureGitCheckouts=True,noCpuOrBusinessCommandIssued=True),indent=2)+chr(10))
with(O/'upload.stdout').open('xb')as out,(O/'upload.stderr').open('xb')as err:r=subprocess.run(['gh','release','upload','evidence-private-20261025',str(bundle),'--repo',repo],stdout=out,stderr=err,timeout=600)
(O/'UPLOAD_EXECUTION.json').write_text(json.dumps(dict(exitCode=r.returncode)));assert r.returncode==0,'Inspect same asset;no overwrite or blind upload retry'
release=api('repos/'+repo+'/releases/423510304');matches=[a for a in release['assets']if a['name']==name];assert len(matches)==1;asset=matches[0]
assert asset['state']=='uploaded'and asset['size']==closed['archiveBytes']and asset['digest']=='sha256:'+closed['archiveSha256']
(O/'ASSET_METADATA.json').write_text(json.dumps(asset,indent=2,sort_keys=True)+chr(10));download=O/'authenticated-complete-download.tar.gz'
with download.open('xb')as out,(O/'download.stderr').open('xb')as err:r=subprocess.run(['gh','api','repos/'+repo+'/releases/assets/'+str(asset['id']),'-H','Accept: application/octet-stream'],stdout=out,stderr=err,timeout=600,env={**os.environ,'GODEBUG':'http2client=0'})
assert r.returncode==0 and download.stat().st_size==closed['archiveBytes']and sha(download)==closed['archiveSha256'];review=verify(download,inventories);assert review==closed['everyOriginalMemberVerified']
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),private=True,draft=True,repository=repo,releaseId=423510304,releaseTag='evidence-private-20261025',assetId=asset['id'],assetName=name,assetApiUrl=asset['url'],bytes=asset['size'],sha256=closed['archiveSha256'],serverDigest=asset['digest'],sourceGitCommit=commit,sourceGitPath=prefix+'/'+source.name,completeAuthenticatedDownloadVerified=True,everyOriginalMemberVerified=review,noApplicationSourceChange=True,noCpuOrBusinessCommandIssued=True,gitHistoryNotRewritten=True,checkoutMigrationNotYetPerformed=True)
(O/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+chr(10));download.unlink();print(json.dumps(result))
