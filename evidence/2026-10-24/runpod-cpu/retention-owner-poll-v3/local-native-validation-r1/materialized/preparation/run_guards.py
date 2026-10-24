from pathlib import Path
import datetime,hashlib,json,subprocess,sys,time,zipfile
p=Path(__file__).resolve().parent
out=p/'guards-r1';out.mkdir(exist_ok=False)
names=['owner_poll_attestation.py','idle_attestation.py','shutdown_warning.py','test_owner_poll_attestation.py']
rows={n:{'bytes':(p/n).stat().st_size,'sha256':hashlib.sha256((p/n).read_bytes()).hexdigest()}for n in names}
argv=[sys.executable,'-B','-m','unittest','-v','test_owner_poll_attestation']
(out/'REGISTRATION.json').write_text(json.dumps({'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':argv,'cwd':str(p),'sources':rows,'runnerSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Pure synthetic owner+driver attestation guards; no Java/native/SSH/Git'},indent=2)+'\n')
with zipfile.ZipFile(out/'sources.zip','x',compression=zipfile.ZIP_DEFLATED)as z:
 for name in names:z.write(p/name,name)
start=time.monotonic()
with(out/'stdout.log').open('xb')as stdout,(out/'stderr.log').open('xb')as stderr:r=subprocess.run(argv,cwd=p,stdout=stdout,stderr=stderr,timeout=30)
unchanged=all(hashlib.sha256((p/n).read_bytes()).hexdigest()==v['sha256']for n,v in rows.items())
log=(out/'stderr.log').read_text()
receipt={'passed':r.returncode==0 and unchanged and 'Ran 14 tests' in log,'exitCode':r.returncode,'allSourcesUnchanged':unchanged,'tests':14 if 'Ran 14 tests' in log else None,'elapsedSeconds':time.monotonic()-start,'scope':'Pure fixture guards only; not runtime proof'}
(out/'COMPLETION.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt));print(log)
raise SystemExit(0 if receipt['passed'] else 1)
