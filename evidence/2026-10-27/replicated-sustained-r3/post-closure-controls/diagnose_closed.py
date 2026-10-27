from pathlib import Path
import sys,json,base64,hashlib
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import controller as c
assert (P/'SUSTAINED_CLOSED.json').exists()
proof=json.loads((P/'archive-sustained-r1/PRIVATE_ASSET_VERIFIED.json').read_text());assert proof['authenticatedFullDownloadVerified']
w=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards');body=(w/'scripts/diagnose-sustained-window.py').read_bytes()
code='ROOT='+repr(c.ROOT)+'\nSOURCE='+repr(base64.b64encode(body).decode())+'\nSHA='+repr(hashlib.sha256(body).hexdigest())+'\nPROOF='+repr(proof)+'\n'+r'''
from pathlib import Path
import os,json,time,hashlib,base64,subprocess
r=Path(ROOT);p=r/'diagnosis-r1';p.mkdir(exist_ok=False)
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
assert all((r/'experiments/sustained-r1'/('node%d-g0'%i)/'EXIT.json').exists()for i in range(4))
body=base64.b64decode(SOURCE);assert hashlib.sha256(body).hexdigest()==SHA;(p/'diagnose.py').write_bytes(body)
v={'clockTicksPerSecond':os.sysconf('SC_CLK_TCK'),'bootId':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'observedAfterNativeClosureEpoch':time.time(),'originalPrivateArchiveSha256':PROOF['sha256'],'scriptSha256':SHA,'scope':'post-arrival host unit observation on unchanged boot; original raw files not modified'}
(p/'HOST_MEASUREMENT.json').write_text(json.dumps(v,indent=2)+'\n')
q=subprocess.run(['python3',str(p/'diagnose.py'),str(r/'experiments/sustained-r1'),'--host-measurement',str(p/'HOST_MEASUREMENT.json'),'--output',str(p/'DIAGNOSIS.json')],capture_output=True,text=True,timeout=180)
(p/'RUN.json').write_text(json.dumps({'returncode':q.returncode,'stdout':q.stdout,'stderr':q.stderr},indent=2)+'\n')
print(json.dumps({f.name:f.read_text()for f in p.iterdir()if f.suffix=='.json'}))
'''
values=c.checked(code,200);dest=w/'evidence/2026-10-27/replicated-sustained-r3/diagnosis';dest.mkdir(exist_ok=True)
for n,s in values.items():(dest/n).write_text(s)
assert json.loads(values['RUN.json'])['returncode']==0,values['RUN.json'];c.save(P/'DIAGNOSIS_CLOSED.json',{'passed':True,'originalArchiveSha256':proof['sha256'],'scriptSha256':hashlib.sha256(body).hexdigest()})
print('POST_CLOSURE_DIAGNOSIS_COMPLETE')
