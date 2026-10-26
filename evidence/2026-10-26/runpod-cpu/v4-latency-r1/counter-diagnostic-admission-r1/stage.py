from pathlib import Path
import importlib.util,hashlib,subprocess,json,base64,shlex,datetime
import sys
P=Path(__file__).resolve().parent;B=P.parent;factor='counter-diagnostic';rate=4000;arm='x1';point=P;O=B/('v4-'+factor+'-'+str(rate)+'-'+arm+'-staging-r1');assert not O.exists()
proof=json.loads((B/'v4-latency-linux-admission-private-proof-r1/PRIVATE_PUSH.json').read_text());assert proof['passed']and proof['private']and proof['qualifiedSource']=='c6445604b0a55119ad239d01e493ef556fd8efac'
freeze=json.loads((point/'SOURCE_FREEZE.json').read_text());files={}
for name,pin in freeze['files'].items():
 body=(point/'inputs'/name).read_bytes();assert len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256'];files[name]=base64.b64encode(body).decode()
script=r'''from pathlib import Path
import sys,json,base64,hashlib,os,socket,subprocess
c=json.load(sys.stdin);root=Path('/opt/vectormatch-cpu/experiments')/('v4-'+c['freeze']['factor']+'-'+str(c['freeze']['rate'])+'-'+c['freeze']['arm']+'-r1');assert socket.gethostname()=='33ace3d92505'and not root.exists()
for parent in root.parents:assert parent.is_dir()and not parent.is_symlink()
assert set(c['files'])=={'analyze.py','audit-async-capacity-v4.py','config.json','controller.py','idle-proof-fixture-inputs/SOURCE_MANIFEST.json','idle-proof-fixture-inputs/node-0-actual-original.json','idle-proof-fixture-inputs/node-1-actual-original.json','idle-proof-fixture-inputs/node-2-actual-original.json','idle-proof-fixture-inputs/owner-original-first-sample.json','idle_attestation.py','idle_proof.py','node-contract-fixtures/actual-linux-observation.json','node-contract-fixtures/config.json','node-contract-fixtures/recovery-proof.json','node_contract.py','owned_linux_base_8eeb.py','owned_process_identity.py','retention_read_yield_audit_v4.py','test_idle_node_contract.py','test_idle_proof.py','test_node_contract.py','AeronCounterWatch.java','counter-classes/io/vectormatch/cluster/AeronCounterWatch.class','counter-classes/io/vectormatch/cluster/AeronCounterWatch$Mapping.class'}
for name,encoded in c['files'].items():
 body=base64.b64decode(encoded);pin=c['freeze']['files'][name];assert len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256']
 if name.endswith('.py'):compile(body,name,'exec')
os.umask(0o077);root.mkdir(mode=0o700)
for name,encoded in c['files'].items():
 (root/name).parent.mkdir(parents=True,exist_ok=True)
 with(root/name).open('xb')as f:f.write(base64.b64decode(encoded))
(root/'SOURCE_FREEZE.json').write_text(json.dumps(c['freeze'],indent=2,sort_keys=True)+'\n')
with(root/'node-contract-tests.stdout').open('xb')as stdout,(root/'node-contract-tests.stderr').open('xb')as stderr:r=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(root),'-p','test*.py','-v'],stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,timeout=30)
assert r.returncode==0
log=(root/'node-contract-tests.stderr').read_text();assert 'Ran 23 tests'in log and '\nOK\n'in log and 'skipped'not in log
result=dict(passed=True,remoteContractTests=23,remoteContractSkipped=0,root=str(root),sourceCommit=c['freeze']['sourceCommit'],artifactFingerprint=c['freeze']['artifactFingerprint'],inputBodiesVerified=len(c['files']),actualSystemPythonSyntaxCompiled=True,privateAdmissionCommit=c['privateCommit'],noJavaOrBusinessStarted=True)
(root/'STAGED.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result))
'''
s=importlib.util.spec_from_file_location('remote',B/'current-read-window32-collection-preparation-r2/remote_current.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
O.mkdir();(O/'REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=hashlib.sha256(script.encode()).hexdigest(),privateAdmissionCommit=proof['commit'],stageOnlyNoWorkload=True),indent=2)+'\n')
r=m.run(shlex.join(['python3','-B','-c',script]),input=json.dumps(dict(files=files,freeze=freeze,privateCommit=proof['commit'])),timeout=60);(O/'stdout.json').write_text(r.stdout);(O/'stderr').write_text(r.stderr);(O/'EXECUTION.json').write_text(json.dumps(dict(exitCode=r.returncode))+'\n');assert r.returncode==0,r.stderr;assert json.loads(r.stdout)['passed'];print(r.stdout)
