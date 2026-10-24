"""Bounded LOCAL pure guard recorder. Never imports a remote helper or reads actual benchmark data."""
import argparse,datetime,hashlib,json,os,platform,re,subprocess,sys,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x')as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')

def run(output):
    assert output.parent.resolve()==HERE and not output.exists(),'New immediate preparation child required'
    files={str(p.relative_to(HERE)):{'bytes':p.stat().st_size,'sha256':sha(p)}for p in sorted(HERE.rglob('*'))if p.is_file()and not any(x.startswith(('guards-','__pycache__'))for x in p.relative_to(HERE).parts)}
    assert sum(v['bytes']for v in files.values())<4*1024**2
    output.mkdir(mode=0o700)
    with zipfile.ZipFile(output/'source.zip','x',compression=zipfile.ZIP_DEFLATED)as z:
        for name in files:z.write(HERE/name,name)
    argv=[sys.executable,'-B','-m','unittest','-v','test_inspect_closed_read_window32_arm']
    save(output/'registration.json',dict(createdAtUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=argv,cwd=str(HERE),
        interpreter=dict(executable=sys.executable,version=platform.python_version()),sourceFiles=files,sourceZipSha256=sha(output/'source.zip'),scope='PURE_SYNTHETIC_READ_WINDOW32_CLOSE_GUARDS_NO_PROC_OR_REMOTE'))
    with(output/'stdout').open('xb')as out,(output/'stderr').open('xb')as err:
        result=subprocess.run(argv,cwd=HERE,stdout=out,stderr=err,timeout=120,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    unchanged=all((HERE/n).stat().st_size==v['bytes']and sha(HERE/n)==v['sha256']for n,v in files.items())
    match=re.search(r'Ran (\d+) tests? in ',(output/'stderr').read_text())
    value=dict(passed=result.returncode==0 and unchanged,exitCode=result.returncode,actualTestsRun=int(match.group(1))if match else None,
        allInputSourcesUnchanged=unchanged,stdoutSha256=sha(output/'stdout'),stderrSha256=sha(output/'stderr'),registrationSha256=sha(output/'registration.json'),
        javaSshGitBenchmarkExecuted=False,actualRawRead=False)
    save(output/'completion.json',value);print(json.dumps(value));return 0 if value['passed']else 1
if __name__=='__main__':
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--output',required=True,type=Path);raise SystemExit(run(p.parse_args().output.absolute()))
