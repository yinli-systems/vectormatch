from pathlib import Path
import argparse, datetime, hashlib, json, subprocess, sys
ROOT=Path(__file__).resolve().parents[4];BASE=ROOT/'runtime/cloud/cpu-20261024'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n')
p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--arm',type=int,choices=[2,3,4],required=True)
p.add_argument('--prior-directory',type=Path,action='append',required=True);a=p.parse_args()
prior={}
for directory in a.prior_directory:
    directory=directory.resolve();gate=directory/'collection-gate.json';push=directory/'private-push.json'
    n=json.loads(gate.read_text())['arm'];assert n not in prior;prior[n]=(gate,push)
assert set(prior)==set(range(1,a.arm))
prep=BASE/'cpu-owner-poll-collection-preparation-r2'
assert sha(prep/'LOCAL_PREPARATION_FROZEN.json')=='28f6865201389901f26b2c6a7c698622d5d8acc635bad24d09ddadff05777b56'
out=BASE/('owner-cloud-arm-%d-config-execution-r1'%a.arm);out.mkdir()
cmd=[sys.executable,'-B',str(prep/'build_config.py'),'--arm',str(a.arm),
    '--release',str(BASE/'owner-cloud-root-release-freeze-r1/release/release.json'),
    '--release-sha256','0751fc006390f8ef94786479b3523f0272d0149df42f400aa8bf7de34f2a3c18',
    '--stage',str(BASE/'cpu-owner-poll-cloud-staging-r1/STAGE_SUCCESS.json'),
    '--stage-sha256','57a9d1c85567035dbd7022f99ccc66e1e8054f27ff8bfcd4d1153eac3160388a',
    '--protected',str(BASE/'owner-cloud-root-release-freeze-r1/release/current-stopped-original-state.json'),
    '--protected-sha256','6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753',
    '--output',str(BASE/('owner-cloud-arm-%d-config-r1'%a.arm))]
for suffix in ['-register.json','.stdout','.stderr']:cmd+=['--execution-metadata','arm-%d-execution%s'%(a.arm,suffix)]
for n,(gate,push) in sorted(prior.items()):cmd+=['--prior-gate',str(n),str(gate),sha(gate),str(push),sha(push)]
save(out/'REGISTRATION.json',dict(argv=cmd,wrapperSha256=sha(Path(__file__)),atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),remoteAccessed=False))
with (out/'stdout.json').open('xb') as stdout,(out/'stderr.txt').open('xb') as stderr:r=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=45)
save(out/'completion.json',dict(exitCode=r.returncode,stdoutSha256=sha(out/'stdout.json'),stderrSha256=sha(out/'stderr.txt')))
print(json.dumps(dict(arm=a.arm,exitCode=r.returncode)));raise SystemExit(r.returncode)
