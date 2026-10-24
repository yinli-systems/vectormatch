"""Run only Python pure schema/codec/synthetic guards in an isolated subprocess."""
from pathlib import Path
import argparse, ast, datetime, hashlib, json, os, re, subprocess, sys, time, zipfile
P=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(path,value):
 with path.open('x')as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
out=args.output;out.mkdir(exist_ok=False)
sources=sorted(p for folder in ['source','tests','fixtures']for p in(P/folder).rglob('*')if p.is_file())+[Path(__file__).resolve()]
pins={str(p.relative_to(P)):{'bytes':p.stat().st_size,'sha256':sha(p)}for p in sources}
for p in sources:
 if p.suffix=='.py':ast.parse(p.read_text(),filename=str(p))
expected=sum(isinstance(n,ast.FunctionDef)and n.name.startswith('test_')for p in(P/'tests').glob('test_*.py')for n in ast.walk(ast.parse(p.read_text())))
with zipfile.ZipFile(out/'source.zip','x',compression=zipfile.ZIP_DEFLATED)as z:
 for p in sources:z.write(p,str(p.relative_to(P)))
command=[sys.executable,'-B','-m','unittest','discover','-s',str(P/'tests'),'-p','test_*.py','-v']
save(out/'REGISTRATION.json',dict(atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='PURE_SYNTHETIC_READ_WINDOW32_PARSER_GUARDS',arguments=command,cwd=str(P),inputs=pins,sourceZipSha256=sha(out/'source.zip'),expectedDistinctGuardMethods=expected,syntheticFixturesNotJvmOrBenchmarkEvidence=True,actualLocalMetadataOnly=True,noNativeCloudSshGitOrBusinessAudit=True))
environment=dict(os.environ,PYTHONPATH=str(P/'source'),PYTHONDONTWRITEBYTECODE='1');started=time.monotonic()
result=subprocess.run(command,cwd=P,env=environment,capture_output=True)
with(out/'stdout').open('xb')as f:f.write(result.stdout)
with(out/'stderr').open('xb')as f:f.write(result.stderr)
text=result.stderr.decode();matched=re.search(r'Ran (\d+) tests? in ',text);ran=int(matched.group(1))if matched else None
unchanged=all(p.stat().st_size==pins[str(p.relative_to(P))]['bytes']and sha(p)==pins[str(p.relative_to(P))]['sha256']for p in sources)
completion=dict(passed=result.returncode==0 and ran==expected and unchanged,exitCode=result.returncode,durationSeconds=time.monotonic()-started,actualDistinctGuards=ran,expectedDistinctGuards=expected,allInputsUnchanged=unchanged,stdoutSha256=sha(out/'stdout'),stderrSha256=sha(out/'stderr'),sourceZipSha256=sha(out/'source.zip'),actualRawAuditOrJavaNativeSshGitExecuted=False)
save(out/'COMPLETION.json',completion);print(json.dumps(completion));sys.exit(0 if completion['passed']else 1)
