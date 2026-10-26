from pathlib import Path
import json,sys,subprocess,shlex,importlib.util,hashlib,datetime
P=Path(__file__).resolve().parent;B=P.parent;phase=sys.argv[1];assert phase in ['qualification','c1','d1','c2','d2']
O=B/('v4-force-materialization-'+phase+'-r1');assert not O.exists();O.mkdir()
if phase!='qualification':
 previous={'c1':'qualification','d1':'c1','c2':'d1','d2':'c2'}[phase];assert json.loads((B/('v4-force-materialization-'+previous+'-r1')/'VERIFIED.json').read_text())['passed']
config=json.loads((P/'CONFIG.json').read_text());config['phase']=phase;source=(P/'remote.py').read_text();(O/'REGISTRATION.json').write_text(json.dumps(dict(phase=phase,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),remoteSourceSha256=hashlib.sha256(source.encode()).hexdigest(),frozenConfigSha256=hashlib.sha256((P/'CONFIG.json').read_bytes()).hexdigest()),indent=2)+'\n')
s=importlib.util.spec_from_file_location('remote',B/'current-read-window32-collection-preparation-r2/remote_current.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
r=m.run(shlex.join(['python3','-B','-c',source]),input=json.dumps(config),timeout=330)
(O/'remote-manifest.json').write_text(r.stdout);(O/'stderr').write_text(r.stderr);(O/'EXECUTION.json').write_text(json.dumps(dict(exitCode=r.returncode)));assert r.returncode==0,r.stderr
x=json.loads(r.stdout);a=x['archive'];archive=O/'complete-original-files.tar.gz'
with archive.open('xb')as out,(O/'download.stderr').open('xb')as err:r=subprocess.run(m.sshargs()+[shlex.join(['cat',a['path']])],stdout=out,stderr=err,timeout=120)
assert r.returncode==0 and archive.stat().st_size==a['bytes']and hashlib.sha256(archive.read_bytes()).hexdigest()==a['sha256']
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import verify
review=verify(archive,x['sourceScopes']);assert review==x['everyOriginalMemberVerified'];(O/'VERIFIED.json').write_text(json.dumps(dict(passed=True,phase=phase,results=x['results'],everyOriginalMemberVerified=review,archive=a,strictOwnedProcessesAbsent=True,noNativeTradingPerformanceClaim=True),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,phase=phase,archiveBytes=a['bytes'],files=review['originalFiles'],results=x['results'])))
