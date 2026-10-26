from pathlib import Path
import json,subprocess,hashlib,base64,concurrent.futures,threading,datetime
p=Path(__file__).resolve().parent;reg=json.loads((p/'REGISTRATION.json').read_text());assert reg['private']and reg['commit']=='4be75612954a2aee9f4e3abe5c7daf5ffbe28fc6'and not(p/'VERIFIED.json').exists()
(p/'FIRST_ATTEMPT_INCOMPLETE.json').write_text(json.dumps(dict(passed=False,reason='Two read-only Git blob GET requests refused TCP connection to20.233.83.146:443;no source/evidence mutation or test retry',blobs=['103e2599355638fc56c1b6f70e3ca2466e3b49d5','2b8e4f754f79cbb2bea05cd73a9dfcd99df04d1f']),indent=2)+'\n')
lock=threading.Lock()
def event(value):
 with lock:
  with(p/'READ_ONLY_EVENTS.jsonl').open('a')as f:f.write(json.dumps(value,sort_keys=True)+'\n');f.flush()
def check(row):
 for attempt in range(1,4):
  r=subprocess.run(['gh','api','repos/yinli-systems/vectormatch/git/blobs/'+row['blob']],capture_output=True,text=True,timeout=45)
  if r.returncode==0:break
  event(dict(blob=row['blob'],attempt=attempt,error=r.stderr,readOnly=True))
  assert attempt<3 and any(x in r.stderr.lower()for x in ['connection refused','timeout','timed out','reset by peer','eof']),r.stderr
 result=json.loads(r.stdout);assert result['encoding']=='base64';body=base64.b64decode(result['content']);assert len(body)==row['bytes']and hashlib.sha256(body).hexdigest()==row['sha256']
 event(dict(blob=row['blob'],path=row['path'],verified=True,attempt=attempt));return row
with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:verified=list(pool.map(check,reg['files']))
(p/'VERIFIED.json').write_text(json.dumps(dict(passed=True,private=True,commit=reg['commit'],allNewSourceAndEvidenceGitBlobsVerified=len(verified),bytes=sum(x['bytes']for x in verified),onlyBoundedReadOnlyMetadataRetries=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n');print((p/'VERIFIED.json').read_text())
