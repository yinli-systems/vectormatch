"""Archive closed derived observations and map their inputs to full original evidence."""
from pathlib import Path
import datetime,hashlib,json,os,shutil,stat
ROOT=Path(__file__).resolve().parents[4];BASE=ROOT/'runtime/cloud/cpu-20261024'
EVIDENCE=ROOT/'evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3'
TARGET=EVIDENCE/'comparison-r1'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def save(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n')
def row(p):
    assert not p.is_symlink();s=p.stat();assert stat.S_ISREG(s.st_mode) and s.st_nlink==1
    return dict(bytes=s.st_size,sha256=sha(p),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
def snapshot(p):
    files={};dirs={}
    for x in [p]+list(p.rglob('*')):
        if any(v in ['__pycache__','.pytest_cache'] for v in x.relative_to(p).parts):continue
        assert not x.is_symlink();s=x.stat();n=str(x.relative_to(p))
        if x.is_dir():dirs[n]=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
        else:files[n]=row(x)
    return dict(files=files,directories=dirs)
assert not TARGET.exists() and shutil.disk_usage(ROOT).free>1024**3+32*1024**2
comp=BASE/'owner-poll-comparison-abab-r1/COMPARISON.json';x=json.loads(comp.read_text())
assert x['passed'] and x['allInputsUnchanged'] and len(x['observations'])==4 and len(x['pairs'])==2
references={};portable={}
for n in range(1,5):
    archive=EVIDENCE/('cloud-arm-%d-r1'%n);manifest=archive/'INVENTORY.json';closed=json.loads((archive/'CLOSED.json').read_text())
    assert closed['passed'] and closed['inventorySha256']==sha(manifest)
    references[str(n)]=dict(path=str(archive.relative_to(ROOT)),inventorySha256=sha(manifest),closedSha256=sha(archive/'CLOSED.json'))
for name,pin in x['inputs'].items():
    p=Path(name);assert p.stat().st_size==pin['bytes'] and sha(p)==pin['sha256']
    matches=[]
    for n in range(1,5):
        original=BASE/('cpu-owner-poll-arm-%d-collection-r1'%n)
        if p.is_relative_to(original):matches.append(EVIDENCE/('cloud-arm-%d-r1'%n)/'actual-collection'/p.relative_to(original))
    assert len(matches)==1;mirror=matches[0];assert mirror.stat().st_size==pin['bytes'] and sha(mirror)==pin['sha256']
    portable[name]=dict(pin,archivedPath=str(mirror.relative_to(ROOT)))
trees={
    'comparison-source':BASE/'owner-poll-comparison-preparation-r1',
    'actual-a1':BASE/'owner-poll-comparison-a1-r1',
    'actual-first-pair':BASE/'owner-poll-comparison-a1-b1-r1',
    'actual-abab':BASE/'owner-poll-comparison-abab-r1',
    'root-prior-gate-source':BASE/'owner-cloud-prior-gate-preparation-r1',
    'root-archive-review-source':BASE/'owner-cloud-archive-root-review-preparation-r1',
    'root-archive-execution-source':BASE/'owner-cloud-archive-root-execution-preparation-r1',
    'archive-source':Path(__file__).parent,
    'resource-after-a1':BASE/'owner-resource-readonly-r2',
    'resource-after-b1':BASE/'owner-resource-readonly-r3',
    'next-factor-review':BASE/'maintenance-next-factor-review-r1',
    'actual-private-push':BASE/'owner-poll-abab-private-push-r1',
}
for n in range(1,5):trees['root-archive-review-%d'%n]=BASE/('owner-cloud-arm-%d-archive-root-review-r1'%n)
for n in range(1,4):trees['prior-gate-%d'%n]=BASE/('owner-cloud-arm-%d-prior-gate-r1'%n)
for n in range(2,5):trees['archive-execution-%d'%n]=BASE/('owner-cloud-arm-%d-archive-execution-r1'%n)
before={n:snapshot(p) for n,p in trees.items()}
assert sum(len(s['files']) for s in before.values())<1000
assert sum(r['bytes'] for s in before.values() for r in s['files'].values())<32*1024**2
TARGET.mkdir()
for name,source in trees.items():
    dest=TARGET/name;inv=before[name]
    for rel,meta in sorted(inv['directories'].items(),key=lambda item:len(Path(item[0]).parts)):
        p=dest if rel=='.' else dest/rel;p.mkdir(mode=meta['mode'])
    for rel in inv['files']:shutil.copy2(source/rel,dest/rel)
    for rel,meta in inv['directories'].items():os.chmod(dest if rel=='.' else dest/rel,meta['mode'])
    assert snapshot(dest)==inv and snapshot(source)==inv
save(TARGET/'SOURCE_MAP.json',dict(trees={k:str(v) for k,v in trees.items()},snapshots=before,originalsUnchanged=True))
save(TARGET/'PORTABLE_INPUT_BINDINGS.json',dict(passed=True,fullOriginalArchives=references,bindings=portable,derivedBytesNotEdited=True))
(TARGET/'README.md').write_text('Four separate finite33792@500/s lineages on one CPU host with three loopbackUDP JVM nodes. Owner requested park order1ms/100us/1ms/100us; server/driver100us and all other controls fixed. actual-abab/COMPARISON.json retains both paired changes, all latency partitions and coarse observed-span CPU data. Full original evidence remains in cloud-arm-1-r1 through cloud-arm-4-r1; PORTABLE_INPUT_BINDINGS maps original runtime paths to byte-equal archived inputs. Counts cannot be merged into one endurance lineage. No throughput-limit, hard realtime,100M/s or100M physicalconnection result is claimed.\n')
assert all(snapshot(p)==before[n] for n,p in trees.items())
inventory=snapshot(TARGET)
save(TARGET/'INVENTORY.json',dict(inventory,excludedSelfAndClosure=['INVENTORY.json','CLOSED.json']))
save(TARGET/'CLOSED.json',dict(passed=True,atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=sha(TARGET/'INVENTORY.json'),
    files=len(inventory['files']),directories=len(inventory['directories']),allCopiedBytesModesOwnersDirectoriesVerified=True,
    originalComparisonAndRawInputsUnchanged=True,performanceConfigurationPromoted=False,rawArchivesReferencedNotDuplicated=True))
print(json.dumps(dict(passed=True,inventorySha256=sha(TARGET/'INVENTORY.json'),closedSha256=sha(TARGET/'CLOSED.json'),files=len(inventory['files']))))
