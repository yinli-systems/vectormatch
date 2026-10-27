from pathlib import Path
import sys,json,shutil
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import controller as c,archive_closed as archive
W=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards');E=W/'evidence/2026-10-27/replicated-path-probe-r1'
def close(case):
 prefix=c.ROOT+'/experiments/'+case
 code='PREFIX='+repr(prefix)+'\nJAVA='+repr(c.JAVA)+'\nROOT='+repr(c.ROOT)+'\n'+r'''
from pathlib import Path
import hashlib,json,subprocess,os
p=Path(PREFIX)
for i in range(4):assert(p/('node%d-g0'%i)/'EXIT.json').is_file()
assert(p/'evidence/complete.json').is_file()
if(p/'complete.json').exists():print((p/'AUDIT.json').read_text());raise SystemExit(0)
host=p/'host.json'
if not host.exists():host.write_text(json.dumps({'bootId':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'clockTicksPerSecond':os.sysconf('SC_CLK_TCK')}))
files={}
for f in sorted(p.rglob('*')):
 assert not f.is_symlink()
 if not f.is_file()or f.name in ['MEMBER_MANIFEST.json','AUDIT.json','AUDIT_RUN.json','complete.json']:continue
 h=hashlib.sha256()
 with f.open('rb')as inp:
  for b in iter(lambda:inp.read(1024**2),b''):h.update(b)
 files[str(f.relative_to(p))]={'bytes':f.stat().st_size,'sha256':h.hexdigest()}
f=p/'MEMBER_MANIFEST.json';value={'files':files}
if f.exists():assert json.loads(f.read_text())==value
else:f.write_text(json.dumps(value,indent=2)+'\n')
q=subprocess.run(['python3',ROOT+'/audit-replicated-path-probe.py',str(p),'--jfr',str(Path(JAVA).with_name('jfr')),'--output',str(p/'AUDIT.json')],capture_output=True,text=True,timeout=600)
(p/'AUDIT_RUN.json').write_text(json.dumps({'returncode':q.returncode,'stdout':q.stdout,'stderr':q.stderr},indent=2))
assert q.returncode==0,q.stderr
audit=json.loads((p/'AUDIT.json').read_text())
(p/'complete.json').write_text(json.dumps({'closed':True,'audited':True,'correctnessPassed':True},indent=2)+'\n');print(json.dumps(audit))
'''
 audit=c.checked(code,660);c.save(P/(case+'-AUDIT.json'),audit)
 proof=archive.archive(case);d=E/case;d.mkdir(parents=True,exist_ok=True)
 meta=c.checked('PREFIX='+repr(prefix)+'\n'+r'''
from pathlib import Path
import json
p=Path(PREFIX);names=['AUDIT.json','AUDIT_RUN.json','complete.json','host.json','MEMBER_MANIFEST.json','evidence/window.json','evidence/correctness.json']
for i in range(4):names += ['node%d-g0/'%i+n for n in ['LAUNCH.json','EXIT.json','JFR_CONTROLLED_DUMP.json']]
print(json.dumps({n:(p/n).read_text()for n in names if(p/n).is_file()}))
''')
 for n,body in meta.items():
  f=d/n.replace('/','__')
  if f.exists():assert f.read_text()==body
  else:f.write_text(body)
 for n in ['ARCHIVE_MEMBER_MANIFEST.json','PRIVATE_ASSET_VERIFIED.json','EXACT_COMPRESSED_PLAN.json']:shutil.copy2(P/('archive-'+case)/n,d/n)
 c.progress({'stage':'raw_private_verified','case':case,'assetId':proof['assetId'],'latency':audit['fullLatency'],'gate':audit['registeredGatePass']})
 return audit
