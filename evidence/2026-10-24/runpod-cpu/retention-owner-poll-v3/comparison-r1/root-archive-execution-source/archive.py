from pathlib import Path
import argparse,datetime,hashlib,json,subprocess,sys
BASE=Path(__file__).resolve().parents[4]/'runtime/cloud/cpu-20261024'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n')
def invoke(cmd,out,label):
    save(out/(label+'-registration.json'),dict(command=cmd,atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    with (out/(label+'.stdout.json')).open('xb') as stdout,(out/(label+'.stderr.txt')).open('xb') as stderr:
        result=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=180)
    save(out/(label+'-completion.json'),dict(exitCode=result.returncode,stdoutSha256=sha(out/(label+'.stdout.json')),stderrSha256=sha(out/(label+'.stderr.txt'))))
    assert result.returncode==0,'Preserve this attempt; no automatic retry'
    return json.loads((out/(label+'.stdout.json')).read_text())
p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--arm',type=int,choices=[3,4],required=True);a=p.parse_args()
prep=BASE/'owner-cloud-arm-archive-preparation-r2'
assert sha(prep/'SOURCE_FROZEN.json')=='99e52e7a653a532561b152eeada04bbf41013b2ec0c43b77d8f0894fec2b401b'
review=BASE/('owner-cloud-root-review-arm-%d-r1/ROOT_REVIEW.json'%a.arm)
assert json.loads(review.read_text())['passed']
out=BASE/('owner-cloud-arm-%d-archive-execution-r1'%a.arm);out.mkdir()
config=BASE/('owner-cloud-arm-%d-archive-config-r1'%a.arm)
invoke([sys.executable,'-B',str(prep/'prepare_config.py'),'--arm',str(a.arm),'--root-review-sha256',sha(review),'--output',str(config)],out,'prepare')
config=config/'archive-config.json'
result=invoke([sys.executable,'-B',str(prep/'archive_arm.py'),'--config',str(config),'--config-sha256',sha(config)],out,'archive')
save(out/'SUCCESS.json',dict(result,wrapperSha256=sha(Path(__file__))))
print(json.dumps(result))
