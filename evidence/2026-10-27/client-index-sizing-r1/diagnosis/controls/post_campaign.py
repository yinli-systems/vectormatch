from pathlib import Path
import json,sys,hashlib
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import archive_closed as archive
assert json.loads((P/'COMPLETE.json').read_text())['all11OriginalGroupsClosed']
source=r'''
from pathlib import Path
import json,shutil
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();assert boot=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
active=[]
for f in Path('/proc').glob('[0-9]*/comm'):
 try:
  if f.read_text().strip()=='java':active.append(int(f.parent.name))
 except(FileNotFoundError,ProcessLookupError):pass
assert not active,'new Java remains; inspect identities, do not kill unrelated work'
workers=[]
for cohort in ['process-isolation-20261027-r1','client-index-sizing-20261027-r1']:
 r=Path('/opt/vectormatch-cpu/experiments')/cohort
 for name in json.loads((r/'PLAN.json').read_text())['points']:
  launch=json.loads((r/(name+'.worker.launch.json')).read_text());stat=Path('/proc')/str(launch['pid'])/'stat';same=False
  try:
   fields=stat.read_text().split(') ',1)[1].split();same=fields[19]==launch['startTicks']and fields[0]!='Z'
  except(FileNotFoundError,ProcessLookupError):pass
  assert not same;assert json.loads((r/name/'complete.json').read_text())['passed'];workers.append({'cohort':cohort,'point':name,'originalWorkerInactive':True})
clusters=[];r=Path('/opt/vectormatch-cpu/experiments/replicated-sustained-20261027-r3/experiments')
for name in ['qual-a1','qual-b1','qual-a2','qual-b2','sustained-r1','restore-r1']:
 for role in range(4):
  p=r/name/('node%d-g0'%role);launch=json.loads((p/'LAUNCH.json').read_text());exit=json.loads((p/'EXIT.json').read_text());assert launch['boot']==boot
  stat=Path('/proc')/str(launch['pid'])/'stat'
  try:
   fields=stat.read_text().split(') ',1)[1].split();assert fields[19]!=launch['startTicks']or fields[0]=='Z'
  except(FileNotFoundError,ProcessLookupError):pass
  clusters.append({'case':name,'role':role,'pid':launch['pid'],'closed':True,'returncode':exit['returncode']})
print(json.dumps({'bootId':boot,'host':Path('/etc/hostname').read_text().strip(),'noJavaProcessesRemain':True,'originalFiniteWorkers':workers,'originalReplicatedRoles':clusters,'freeBytes':shutil.disk_usage(r).free,'newPaidResourcesCreated':False,'existingCpuLeftRunning':True}))
'''
v=json.loads(archive.checked(source,60));(P/'POST_CAMPAIGN_QUIET.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({k:x for k,x in v.items()if k not in ['originalFiniteWorkers','originalReplicatedRoles']}))
