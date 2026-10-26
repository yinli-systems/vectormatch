from pathlib import Path
import json,sys,hashlib,shlex,datetime,subprocess
B=Path(__file__).resolve().parent.parent;P=Path(__file__).resolve().parent;O=B/'v4-jfr-runtime-cache-retirement-r1';assert not O.exists()
sys.path.insert(0,str(B/'current-read-window32-collection-preparation-r2'));import remote_current
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import verify,sha
points=[]
cases=[('v4-jfr-qualification',500,'q1'),('v4-jfr-diagnostic',4000,'x1')]
for namespace,rate,arm in cases:
 root=B/f'{namespace}-{rate}-{arm}-closure-r1';m=json.loads((root/'remote-manifest.json').read_text());p=json.loads((B/f'{namespace}-{rate}-{arm}-private-proof-r1/PRIVATE_PUSH.json').read_text());assert p['passed']and p['completeAuthenticatedAssetDownloadVerified']and sha(root/'complete-native-point-and-independent-audit.tar.gz')==p['assetSha256'];points.append(dict(manifest=m,proof=p,namespace=namespace))
source=(P/'remote.py').read_text();c=dict(points=points,remoteSource=source,scopeSource=(B/'dispatch-capacity-scope-tar-preparation-r1/scope_tar.py').read_text())
O.mkdir();(O/'REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),remoteSha256=hashlib.sha256(source.encode()).hexdigest(),only2FullyClosedVerifiedRuntimeDuplicates=True,uniqueArchivesRemainLocalCpuAndPrivate=True),indent=2)+'\n')
x=remote_current.run('python3 -B -c '+shlex.quote(source),input=json.dumps(c),timeout=300)
(O/'remote.stdout.json').write_text(x.stdout);(O/'remote.stderr').write_text(x.stderr);(O/'EXECUTION.json').write_text(json.dumps(dict(exitCode=x.returncode))+'\n');assert x.returncode==0,x.stderr
m=json.loads(x.stdout);assert m['passed'];archive=O/'complete-retirement.tar.gz'
with archive.open('xb')as f,(O/'download.stderr').open('xb')as err:x=subprocess.run(remote_current.sshargs()+['cat '+shlex.quote(m['archive']['path'])],stdout=f,stderr=err,timeout=60)
assert x.returncode==0 and archive.stat().st_size==m['archive']['bytes']and sha(archive)==m['archive']['sha256'];review=verify(archive,m['originalScopeInventories']);assert review==m['everyOriginalMemberVerified']
(O/'VERIFIED.json').write_text(json.dumps(dict(passed=True,result=m['result'],archiveSha256=sha(archive),everyOriginalMemberVerified=review),indent=2)+'\n');print(json.dumps(m['result']))
