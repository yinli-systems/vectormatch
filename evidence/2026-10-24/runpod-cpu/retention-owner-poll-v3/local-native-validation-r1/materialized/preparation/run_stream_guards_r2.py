"""One registered pure-fixture attempt, no native/Java/SSH invocation."""
from pathlib import Path
import datetime,hashlib,json,platform,subprocess,sys,time,zipfile
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
SOURCES=['stream_archive_r2.py','test_stream_archive_r2.py','capture_closed_pair_r2.py','audit_closed_pair_r2.py','PLAN_R2.md','run_stream_guards_r2.py']
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
 with path.open('x')as output:json.dump(value,output,indent=2);output.write('\n')
def main():
 attempt=HERE/'guards-stream-r1';attempt.mkdir(mode=0o700)
 rows={name:{'bytes':(HERE/name).stat().st_size,'sha256':sha(HERE/name)}for name in SOURCES}
 command=[sys.executable,'-B','-m','unittest','-v','test_stream_archive_r2']
 write(attempt/'REGISTRATION.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'arguments':command,'cwd':str(HERE),'python':sys.version,'executable':sys.executable,'executableSha256':sha(sys.executable),'platform':platform.platform(),'sourceFiles':rows,'testsExpected':3,'temporarySyntheticFixturesOnly':True,'noNativeBusinessReadOrLaunch':True})
 with zipfile.ZipFile(attempt/'source-inputs.zip','x',compression=zipfile.ZIP_DEFLATED)as archive:
  for name in SOURCES:archive.write(HERE/name,name)
 for name in SOURCES:
  if name.endswith('.py'):compile((HERE/name).read_bytes(),str(HERE/name),'exec')
 start=time.monotonic()
 with (attempt/'stdout.txt').open('xb')as output,(attempt/'stderr.txt').open('xb')as error:
  result=subprocess.run(command,cwd=HERE,stdout=output,stderr=error,timeout=30)
 unchanged=all(sha(HERE/name)==row['sha256']for name,row in rows.items())
 passed=result.returncode==0 and unchanged and b'Ran 3 tests'in(attempt/'stderr.txt').read_bytes()
 write(attempt/'COMPLETION.json',{'passed':passed,'exitCode':result.returncode,'durationSeconds':time.monotonic()-start,'tests':3,'sourcesUnchanged':unchanged,'sourceZipSha256':sha(attempt/'source-inputs.zip'),'stdoutSha256':sha(attempt/'stdout.txt'),'stderrSha256':sha(attempt/'stderr.txt'),'temporarySyntheticFixturesOnly':True,'businessPairRerun':False})
 print(json.dumps({'passed':passed,'completionSha256':sha(attempt/'COMPLETION.json')}))
 if not passed:raise SystemExit(1)
if __name__=='__main__':main()
