from pathlib import Path
import sys,subprocess,json,hashlib,datetime,time,zipfile,argparse
S=Path(__file__).resolve().parent;B=S.parent
p=argparse.ArgumentParser();p.add_argument('--attempt',required=True);a=p.parse_args();out=S/a.attempt;out.mkdir()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
inputs={'scope/'+str(p.relative_to(S)):p for p in sorted(S.rglob('*'))if p.is_file()and not any(part.startswith('guards-')for part in p.relative_to(S).parts)}
source=B/'cpu-read-window32-cloud-preparation-r2'
frozen=json.loads((source/'LOCAL_PREPARATION_FROZEN.json').read_text())
for name in list(frozen['files'])+['LOCAL_PREPARATION_FROZEN.json','INVENTORY.json','CLOSED.json']:
 inputs['actual-controller/'+name]=source/name
for name in ['read-window32-long-parser-preparation-r1/SOURCE_FROZEN.json','cpu-idle-cloud-preparation-r2/candidate/release/current-stopped-original-state.json','cpu-event-fetch-cloud-preparation-r1/idle_attestation.py','owner-poll-native-preparation-r1/PARSER_SOURCE_FROZEN.json','remote.py']:
 inputs['actual-external/'+name]=B/name
registered={name:{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}for name,p in inputs.items()}
argv=[sys.executable,'-B','-m','unittest','-v','test_stage_launch']
save(out/'registration.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':argv,'cwd':str(S),'inputs':registered,'scope':'pure source guards; synthetic root/JAR declarations are not real ready-release or benchmark evidence','noSshJavaNativeBusiness':True})
with zipfile.ZipFile(out/'sources.zip','x',compression=zipfile.ZIP_DEFLATED)as z:
 for name,p in inputs.items():z.write(p,name)
start=time.monotonic()
with(out/'stdout').open('xb')as stdout,(out/'stderr').open('xb')as stderr:r=subprocess.run(argv,cwd=S,stdout=stdout,stderr=stderr,timeout=90)
same=all(sha(inputs[name])==row['sha256']for name,row in registered.items());save(out/'completion.json',{'exitCode':r.returncode,'allInputsUnchanged':same,'durationSeconds':time.monotonic()-start,'stdoutSha256':sha(out/'stdout'),'stderrSha256':sha(out/'stderr'),'sourceZipSha256':sha(out/'sources.zip'),'noSshJavaNativeBusiness':True})
print(json.dumps({'exitCode':r.returncode,'allInputsUnchanged':same,'attempt':a.attempt}));raise SystemExit(r.returncode)
