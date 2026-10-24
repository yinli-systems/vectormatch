from pathlib import Path
import sys,subprocess,json,hashlib,datetime,time,zipfile,argparse
S=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--attempt',required=True);p.add_argument('--parser',action='store_true');a=p.parse_args();out=S/a.attempt;out.mkdir()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
inputs={str(p.relative_to(S)):sha(p)for p in sorted(S.rglob('*'))if p.is_file()and not any(part.startswith('guards-')for part in p.relative_to(S).parts)}
modules=['test_long_contract','test_phase_baseline','test_read_window32']if a.parser else ['test_read_window32_delta'];cwd=S/'long-parser'if a.parser else S;argv=[sys.executable,'-B','-m','unittest','-v',*modules]
save(out/'registration.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':argv,'cwd':str(cwd),'inputs':inputs,'scope':'pure source guards; synthetic root/capacity declarations are not actual benchmark evidence','noSshJavaNativeBusiness':True})
with zipfile.ZipFile(out/'sources.zip','x',compression=zipfile.ZIP_DEFLATED)as z:
 for name in inputs:z.write(S/name,name)
start=time.monotonic()
with(out/'stdout').open('xb')as stdout,(out/'stderr').open('xb')as stderr:r=subprocess.run(argv,cwd=cwd,stdout=stdout,stderr=stderr,timeout=90)
same=all(sha(S/name)==value for name,value in inputs.items());save(out/'completion.json',{'exitCode':r.returncode,'allInputsUnchanged':same,'durationSeconds':time.monotonic()-start,'stdoutSha256':sha(out/'stdout'),'stderrSha256':sha(out/'stderr'),'sourceZipSha256':sha(out/'sources.zip'),'noSshJavaNativeBusiness':True})
print(json.dumps({'exitCode':r.returncode,'allInputsUnchanged':same,'attempt':a.attempt}));raise SystemExit(r.returncode)
