from pathlib import Path
import hashlib,json,shutil,stat,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';P=R/'evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3/console-ledger-r1'
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def row(p):
 assert not p.is_symlink();s=p.stat();assert stat.S_ISREG(s.st_mode)
 return dict(bytes=s.st_size,sha256=h(p),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
assert not P.exists();P.mkdir()
files={'export-owner-poll-ui.py':R/'scripts/export-owner-poll-ui.py','evidence-index.json':R/'evidence/index.json','OWNER_POLL_RESULTS.md':R/'docs/OWNER_POLL_RESULTS.md','archive.py':Path(__file__)}
for name in ['REGISTRATION.json','LAUNCHED.json']:files['passive-local-preview/'+name]=R/'runtime/local-console-owner-poll-r1'/name
for n in [1,2]:
 source=B/('owner-evidence-ui-validation-r%d'%n)
 for f in source.rglob('*'):
  if f.is_file():files['http-and-browser-validation-r%d/'%n+str(f.relative_to(source))]=f
pins={name:row(p) for name,p in files.items()}
for name,source in files.items():
 dest=P/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest);assert row(dest)==pins[name]
assert all(row(p)==pins[name] for name,p in files.items())
(P/'README.md').write_text('Four qualified owner-poll observations added to the evidence ledger; all17historical runs and capacity curves retained. HTTP8011 evidence matches exactrepository ledger. Initial failed8011/8000 probes are retained; after launching a fresh passive local journal preview with bootstrap/flow disabled and no cloud/PostgreSQL configuration, HTTP200/page/state/evidence and actualbrowser drawer were verified. This preview is not a live connection to the cloud benchmark nodes. The screenshot shows selectedB2; allfour outcomes and mixeddirection paired changes are in OWNER_POLL_RESULTS.md. No newcloudresources or newbenchmark are represented here. Original source paths and filebytes are preserved.\n')
(P/'SOURCE_MAP.json').write_text(json.dumps({name:dict(source=str(files[name]),**pin) for name,pin in pins.items()},indent=2)+'\n')
inv={};dirs={}
for f in [P]+list(P.rglob('*')):
 s=f.stat();name=str(f.relative_to(P))
 if f.is_dir():dirs[name]=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
 else:inv[name]=row(f)
(P/'INVENTORY.json').write_text(json.dumps(dict(files=inv,directories=dirs,excludedSelfAndClosure=['INVENTORY.json','CLOSED.json']),indent=2)+'\n')
(P/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=h(P/'INVENTORY.json'),allPayloadHashesModesOwnersAndDirectoriesVerified=True,allSourceFilesUnchanged=True,localPreviewOnly=True),indent=2)+'\n')
print(json.dumps(dict(passed=True,files=len(inv),inventorySha256=h(P/'INVENTORY.json'),closedSha256=h(P/'CLOSED.json'))))
