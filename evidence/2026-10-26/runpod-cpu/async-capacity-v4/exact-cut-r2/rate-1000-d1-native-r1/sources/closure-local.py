from pathlib import Path
import sys,json,hashlib,subprocess,importlib.util,shlex,datetime
P=Path(__file__).resolve().parent;B=P.parent;rate=int(sys.argv[1]);arm=sys.argv[2];point=B/'async-v4-cut-gate-controller-preparation-r1'/('point-'+str(rate)+'-'+arm);O=B/('async-v4-cut-gate-'+str(rate)+'-'+arm+'-closure-r1');assert not O.exists();O.mkdir()
source=(P/'remote.py').read_text();scope=(B/'dispatch-capacity-scope-tar-preparation-r1/scope_tar.py').read_text();freeze=json.loads((point/'SOURCE_FREEZE.json').read_text());c=dict(root='/opt/vectormatch-cpu/experiments/async-v4-cut-gate-'+str(rate)+'-'+arm+'-r1',rate=rate,arm=arm,freeze=freeze,remoteSource=source,scopeSource=scope,remoteSha256=hashlib.sha256(source.encode()).hexdigest(),scopeSha256=hashlib.sha256(scope.encode()).hexdigest())
(O/'REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=c['remoteSha256'],scopeSha256=c['scopeSha256'],freezeSha256=hashlib.sha256((point/'SOURCE_FREEZE.json').read_bytes()).hexdigest(),oneClosureOnly=True,noBusinessCommandsIssued=True),indent=2)+'\n')
spec=importlib.util.spec_from_file_location('remote',B/'current-read-window32-collection-preparation-r2/remote_current.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
r=m.run(shlex.join(['python3','-B','-c',source]),input=json.dumps(c),timeout=600);(O/'remote-manifest.json').write_text(r.stdout);(O/'stderr').write_text(r.stderr);(O/'EXECUTION.json').write_text(json.dumps(dict(exitCode=r.returncode))+'\n');assert r.returncode==0,r.stderr;manifest=json.loads(r.stdout);a=manifest['archive'];local=O/'complete-native-point-and-independent-audit.tar.gz'
with local.open('xb')as out,(O/'download.stderr').open('xb')as err:r=subprocess.run(m.sshargs()+[shlex.join(['cat',a['path']])],stdout=out,stderr=err,timeout=300)
assert r.returncode==0 and local.stat().st_size==a['bytes']
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import sha,verify
assert sha(local)==a['sha256'];review=verify(local,manifest['sourceScopes']);assert review==manifest['everyOriginalMemberVerified']
(O/'VERIFIED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),nativePassed=manifest['nativePassed'],independentAuditPassed=manifest['independentAuditPassed'],analysisPassed=manifest['analysisPassed'],archiveBytes=a['bytes'],archiveSha256=a['sha256'],everyOriginalMemberVerified=review),indent=2,sort_keys=True)+'\n')
import tarfile
with tarfile.open(local)as t:
 for name,label in [('SUCCESS.json','NATIVE_SUCCESS.json'),('state/load/load-result.json','SOURCE_RESULT.json'),('analysis/RESULT.json','ANALYSIS.json'),('independent-audit/RESULT.json','AUDIT.json')]:
  key='original/point/'+name
  try:body=t.extractfile(key).read()
  except KeyError:continue
  (O/label).write_bytes(body)
print(json.dumps(dict(passed=True,nativePassed=manifest['nativePassed'],auditPassed=manifest['independentAuditPassed'],analysisPassed=manifest['analysisPassed'],originalFiles=review['originalFiles'],archiveBytes=a['bytes'])))
