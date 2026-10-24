"""One registered synthetic-only guard attempt; never calls freeze/upload main or Git/SSH."""
from pathlib import Path
import datetime, hashlib, json, stat, subprocess, sys, zipfile
HERE=Path(__file__).resolve().parent
def row(path):
    data=path.read_bytes();s=path.stat()
    return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),mode=stat.S_IMODE(s.st_mode))
def save(path,value):
    with path.open('x')as out:json.dump(value,out,indent=2,sort_keys=True);out.write('\n')
def main():
    output=HERE/'guards-r1';output.mkdir()
    files={name:row(HERE/name)for name in ['contracts.py','freeze.py','upload_pair.py','test_prior.py','run_guards.py']}
    argv=[sys.executable,'-B','-m','unittest','-v','test_prior']
    save(output/'REGISTRATION.json',dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),argv=argv,cwd=str(HERE),sourceFiles=files,syntheticAndTemporaryOnly=True,noActualFreezeUploadGitSshJavaRawAudit=True))
    with zipfile.ZipFile(output/'sources.zip','x',compression=zipfile.ZIP_DEFLATED)as archive:
        for name in files:archive.write(HERE/name,name)
    with(output/'stdout').open('xb')as stdout,(output/'stderr').open('xb')as stderr:
        result=subprocess.run(argv,cwd=HERE,stdout=stdout,stderr=stderr,timeout=60)
    after={name:row(HERE/name)for name in files}
    save(output/'EXECUTION.json',dict(exitCode=result.returncode,sourceFilesBefore=files,sourceFilesAfter=after,sourceInputsUnchanged=files==after,
        sourceZip=row(output/'sources.zip'),stdout=row(output/'stdout'),stderr=row(output/'stderr'),actualFreezeOrUploadRun=False))
    print(json.dumps(dict(exitCode=result.returncode,sourceInputsUnchanged=files==after,stderr=(output/'stderr').read_text())))
    raise SystemExit(result.returncode or int(files!=after))
if __name__=='__main__':main()
