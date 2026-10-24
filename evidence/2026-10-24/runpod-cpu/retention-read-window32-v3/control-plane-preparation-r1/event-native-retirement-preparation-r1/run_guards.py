from pathlib import Path
import ast, datetime, hashlib, json, os, re, subprocess, sys, time, zipfile
P=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,value):
    with p.open('x')as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
out=P/'guards-r1';out.mkdir(exist_ok=False)
files=sorted(P.glob('*.py'))+[P/'CONFIG.json'];pins={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)}for p in files}
for p in files:
    if p.suffix=='.py':ast.parse(p.read_text(),filename=str(p))
status=ast.parse((P/'read_status.py').read_text());program=next(n.value.value for n in status.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='REMOTE_PROGRAM'for t in n.targets));ast.parse(program,filename='frozen read-only remote status program')
expected=sum(isinstance(n,ast.FunctionDef)and n.name.startswith('test_')for p in P.glob('test_*guards.py')for n in ast.walk(ast.parse(p.read_text())))
with zipfile.ZipFile(out/'source.zip','x',compression=zipfile.ZIP_DEFLATED)as z:
    for p in files:z.write(p,p.name)
command=[sys.executable,'-B','-m','unittest','discover','-s',str(P),'-p','test_*guards.py','-v']
save(out/'REGISTRATION.json',dict(atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='PURE_SMALL_SYNTHETIC_EVENT87A_RETIREMENT_GUARDS_ONLY',command=command,inputs=pins,sourceZipSha256=sha(out/'source.zip'),expectedDistinctGuards=expected,noRemoteLargeBodyCopyOrRestoreOrDelete=True,noSshJvmGitOrActualGateApproval=True))
started=time.monotonic();result=subprocess.run(command,cwd=P,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True)
with(out/'stdout').open('xb')as f:f.write(result.stdout)
with(out/'stderr').open('xb')as f:f.write(result.stderr)
matched=re.search(r'Ran (\d+) tests? in ',result.stderr.decode());ran=int(matched.group(1))if matched else None
unchanged=all(p.stat().st_size==pins[p.name]['bytes']and sha(p)==pins[p.name]['sha256']for p in files)
value=dict(passed=result.returncode==0 and unchanged and ran==expected,exitCode=result.returncode,durationSeconds=time.monotonic()-started,actualDistinctGuards=ran,allRegisteredInputsUnchanged=unchanged,sourceZipSha256=sha(out/'source.zip'),stdoutSha256=sha(out/'stdout'),stderrSha256=sha(out/'stderr'),allFilesystemFixturesSmallSyntheticLocalOnly=True,actual87aRemoteExecutionOrApprovalClaimed=False)
save(out/'COMPLETION.json',value);print(json.dumps(value));sys.exit(0 if value['passed']else 1)
