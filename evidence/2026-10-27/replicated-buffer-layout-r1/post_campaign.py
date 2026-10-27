"""Read-only closure audit for these two existing-CPU campaigns."""
from pathlib import Path
import json,sys
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import controller as c
layout=json.loads((P/'COMPLETE.json').read_text())
prior=P.parent.parent/'replicated-path-probe-20261027-r2/cloud'
assert json.loads((prior/'COMPLETE.json').read_text())['all11NativeArmsClosed']
cohorts={str(json.loads((prior/'PLAN.json').read_text())['root']) if 'root'in json.loads((prior/'PLAN.json').read_text()) else '/opt/vectormatch-cpu/experiments/replicated-path-probe-20261027-r2':list(json.loads((prior/'PLAN.json').read_text())['cases']),c.ROOT:list(c.PLAN['cases']) if layout['promotedTmpfs']else list(c.PLAN['cases'])[:-1]}
out=c.checked('COHORTS='+repr(cohorts)+'\nBOOT='+repr(c.PLAN['boot'])+'\n'+r'''
from pathlib import Path
import json,shutil,time
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
rows=[]
for root,cases in COHORTS.items():
 for case in cases:
  p=Path(root)/'experiments'/case
  assert json.loads((p/'complete.json').read_text())['audited']
  for role in range(4):
   d=p/f'node{role}-g0';launch=json.loads((d/'LAUNCH.json').read_text());exited=json.loads((d/'EXIT.json').read_text());assert exited['returncode']in[0,143]
   stat=Path('/proc')/str(launch['pid'])/'stat';alive=stat.exists()and stat.read_text().split(') ',1)[1].split()[19]==launch['startTicks'];assert not alive
   rows.append({'root':root,'case':case,'role':role,'pid':launch['pid'],'sameBirthAlive':alive,'returncode':exited['returncode']})
  for flag in launch['argv']:
   if flag.startswith('-Dvectormatch.probe.driverRoot='):assert not Path(flag.split('=',1)[1]).exists()
java=[]
for f in Path('/proc').glob('[0-9]*/comm'):
 try:
  if f.read_text().strip()=='java':java.append(str(f.parent))
 except(FileNotFoundError,ProcessLookupError):pass
print(json.dumps({'epoch':time.time(),'host':Path('/etc/hostname').read_text().strip(),'boot':BOOT,'allOwnedJvmsClosed':True,'processes':rows,'javaRemaining':java,'overlayFreeBytes':shutil.disk_usage('/').free,'tmpfsFreeBytes':shutil.disk_usage('/dev/shm').free,'existingCpuHostRetained':True,'newCloudResourcesCreated':False}))
''',60)
c.save(P/'POST_CAMPAIGN.json',out)
print(json.dumps({k:v for k,v in out.items()if k!='processes'}))
