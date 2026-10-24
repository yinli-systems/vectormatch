from pathlib import Path
import subprocess,json,hashlib,datetime
R=Path.cwd();O=Path(__file__).resolve().parent
scopes=['evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/comparison-and-ui-r1','evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/local-unit-validation-r1']
extra=['cluster/RETENTION_EVENT_FETCH_V3.md','docs/EVENT_FETCH_PROGRESS.md','docs/READ_WINDOW32_PROGRESS.md','evidence/index.json','scripts/export-event-fetch-ui.py']
def git(*args):return subprocess.check_output(['git',*args])
head=git('rev-parse','HEAD').decode().strip();remote=git('ls-remote','origin','refs/heads/main').decode().split()[0];assert head==remote and head.startswith('d915161e')
assert not git('status','--porcelain','--',*scopes,*extra)
rows=[]
for entry in git('ls-tree','-r','-z',head,'--',*scopes,*extra).split(b'\0'):
 if not entry:continue
 meta,path=entry.split(b'\t',1);mode,typ,oid=meta.split();assert typ==b'blob'
 rows.append(dict(path=path.decode(),gitBlob=oid.decode()))
assert len(rows)==700
actual=git('hash-object','--',*[r['path'] for r in rows]).decode().splitlines()
assert len(actual)==len(rows)
for row,got in zip(rows,actual):
 assert got==row['gitBlob'];p=R/row['path'];row.update(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
v=R/'runtime/cloud/cpu-20261024/event-cloud-repository-visibility-r2/REPOSITORY.json';visibility=json.loads(v.read_text())['metadata'];assert visibility['visibility']=='private' and visibility['repository_full_name']=='yinli-systems/vectormatch'
r=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),repository='yinli-systems/vectormatch',privateRepositoryReceiptSha256=hashlib.sha256(v.read_bytes()).hexdigest(),head=head,actualRemoteMain=head,all700ChangedFileBodiesMatchCommittedGitBlobs=True,changedArchiveScopesAndPublishedFilesClean=True,files=rows,priorRootReportingReviewSha256=hashlib.sha256((R/'runtime/cloud/cpu-20261024/event-fetch-reporting-root-review-r1/ROOT_REVIEW.json').read_bytes()).hexdigest())
with (O/'PUSH_VERIFIED.json').open('x') as f:json.dump(r,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({k:v for k,v in r.items() if k!='files'}))
