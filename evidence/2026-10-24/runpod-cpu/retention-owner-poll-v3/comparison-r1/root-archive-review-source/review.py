from pathlib import Path
import argparse,datetime,hashlib,json,stat
ROOT=Path(__file__).resolve().parents[4];BASE=ROOT/'runtime/cloud/cpu-20261024'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--arm',type=int,choices=[2,3,4],required=True)
p.add_argument('--inventory-sha256',required=True);p.add_argument('--closed-sha256',required=True);a=p.parse_args()
archive=ROOT/('evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3/cloud-arm-%d-r1'%a.arm)
assert sha(archive/'INVENTORY.json')==a.inventory_sha256 and sha(archive/'CLOSED.json')==a.closed_sha256
m=json.loads((archive/'INVENTORY.json').read_text());closed=json.loads((archive/'CLOSED.json').read_text())
assert closed['passed'] and closed['arm']==a.arm and closed['inventorySha256']==a.inventory_sha256
files={};dirs={}
for f in [archive]+list(archive.rglob('*')):
    assert not f.is_symlink();s=f.stat();n=str(f.relative_to(archive));meta=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
    if f.is_dir():dirs[n]=meta
    elif n not in ['INVENTORY.json','CLOSED.json']:files[n]=dict(meta,bytes=s.st_size,sha256=sha(f))
assert files==m['files'] and dirs==m['directories']
original=BASE/('cpu-owner-poll-arm-%d-collection-r1'%a.arm);count=0
for f in original.rglob('*'):
    if f.is_file() and not any(k in ['__pycache__','.pytest_cache'] for k in f.relative_to(original).parts):
        mirror=archive/'actual-collection'/f.relative_to(original)
        assert sha(f)==sha(mirror) and f.stat().st_size==mirror.stat().st_size;count+=1
out=BASE/('owner-cloud-arm-%d-archive-root-review-r1'%a.arm);out.mkdir()
r=dict(passed=True,arm=a.arm,inventorySha256=a.inventory_sha256,closedSha256=a.closed_sha256,
    allPayloadFileHashesAndDirectoryModesOwnersVerified=True,files=len(files),directories=len(dirs),
    allActualCollectionFilesExactlyCopied=True,actualCollectionFiles=count,atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=sha(Path(__file__)))
with (out/'ROOT_REVIEW.json').open('x') as f:json.dump(r,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(r))
