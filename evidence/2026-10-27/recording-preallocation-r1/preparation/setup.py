from pathlib import Path
import json,shutil,subprocess,hashlib
p=Path(__file__).parent;c=p/'cloud';c.mkdir(exist_ok=False);old=p.parent/'replicated-stage-trace-20261027-r1/cloud';w=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards')
oldid='replicated-stage-trace-20261027-r1';newid='recording-preallocation-20261027-r1'
for name in ['controller.py','process_agent.py','close_case.py','archive_closed.py','archive_runtime.py','stage.py']:
 s=(old/name).read_text().replace(oldid,newid).replace('replicated-stage-trace-r1','recording-preallocation-r1');(c/name).write_text(s)
plan=json.loads((old/'PLAN.json').read_text());plan['cases']={}
for name,seconds,preallocate in [('functional-a',2,False),('functional-b',2,True),('allocation-a1',60,False),('allocation-b1',60,True),('allocation-a2',60,False),('allocation-b2',60,True),('sustained-b1',1800,True)]:
 plan['cases'][name]=dict(mode='MATCHING',seconds=seconds,rate=10 if name.startswith('functional')else 100,maxParkNs=1000000,traceEnabled=True,preallocate=preallocate)
plan['scope']='same-host exact request stages; sole A/B switch is recording segment preallocation; same native CLOCK_MONOTONIC, artifact, trace ON, sync2, G1, affinity, leader0, park1ms, overlay device48'
plan['selection']='Run first six arms in order. Require all originals accepted, all stages joined, all existing gates in BOTH A/B pairs, identical canonical final state, B/A p99<=0.90 and p99.9<=1.0 EACH pair. Only then run sustained-b1 for 1800s; otherwise retain negative result without promotion.'
plan['qualSeconds']=60;(c/'PLAN.json').write_text(json.dumps(plan,indent=2)+'\n')
s=(c/'controller.py').read_text();s=s.replace("props=['-Dvectormatch.stage.clockLibrary=", "props=['-Dvectormatch.stage.preallocate='+str(spec['preallocate']).lower(),'-Dvectormatch.stage.clockLibrary=")
s=s.replace("save(P/(case+'-nodes-ready.json'),ss);start(config(3,case,collector,seconds,qualification,probe))", "save(P/(case+'-nodes-ready.json'),ss);capture_allocation(case);start(config(3,case,collector,seconds,qualification,probe))")
s+='''
def capture_allocation(case):
 code='ROOT='+repr(ROOT)+'\\nCASE='+repr(case)+'\\n'+r"""
from pathlib import Path
import json,time
p=Path(ROOT)/'experiments'/CASE;rows=[]
assert not(p/'node3-g0/LAUNCH.json').exists()
for role in range(3):
 files=[]
 for f in sorted((p/('state/node-%d/archive'%role)).glob('*.rec')):
  assert not f.is_symlink();s=f.stat();files.append({'relative':str(f.relative_to(p)),'logicalBytes':s.st_size,'allocatedBytes':s.st_blocks*512,'device':s.st_dev,'inode':s.st_ino})
 assert len(files)==1,files
 rows.append({'role':role,'files':files,'capturedEpoch':time.time(),'capturedMonotonicNs':time.monotonic_ns()})
v={'beforeSourceLaunch':True,'roles':rows};(p/'RECORDING_ALLOCATION.json').open('x').write(json.dumps(v,indent=2)+'\\n');print(json.dumps(v))
"""
 save(P/(case+'-ALLOCATION.json'),checked(code))
'''
(c/'controller.py').write_text(s)
s=(c/'close_case.py').read_text().replace("ROOT+'/audit-replicated-stage-trace.py'","ROOT+'/audit-recording-preallocation.py'").replace("names=['AUDIT.json'","names=['RECORDING_ALLOCATION.json','AUDIT.json'");(c/'close_case.py').write_text(s)
s=(c/'archive_closed.py').read_text();a=s.index(' assert name in [');b=s.index('\n',a);s=s[:a]+' assert name in '+repr(list(plan['cases']))+s[b:];(c/'archive_closed.py').write_text(s)
s=(c/'archive_runtime.py').read_text().replace("'stage.py','prepare.py'","'stage.py','prepare.py','setup.py','LAUNCH_MATRIX.json'");(c/'archive_runtime.py').write_text(s)
(c/'lib').mkdir()
for f in (w/'cluster/build/install/cluster/lib').glob('*.jar'):shutil.copy2(f,c/'lib'/f.name)
shutil.copy2(w/'cluster/build/libs/vectormatch-soak-agent-0.1.0-SNAPSHOT.jar',c/'soak-agent.jar')
for n in ['audit-replicated-path-probe.py','audit-replicated-stage-trace.py','audit-recording-preallocation.py']:shutil.copy2(w/'scripts'/n,c/n)
for n in ['libvmclock.so','qualification.tar.gz','QUALIFICATION_MANIFEST.json','qualify.py']:shutil.copy2(p/'native-clock'/n,c/n)
shutil.copy2(p/'native-clock/BUILD.json',c/'NATIVE_CLOCK_BUILD.json')
for src,dst in [('stage-patch.jar','stage-patch.jar'),('MANIFEST.json','PATCH_MANIFEST.json'),('instrumentation.patch','instrumentation.patch')]:shutil.copy2(p/'patch-r1'/src,c/dst)
for typ in ['original','modified']:
 for f in (p/'patch-r1'/typ).glob('*.java'):shutil.copy2(f,c/(typ+'-'+f.name))
shutil.copy2(w/'tools/replicated-stage-probe/clock.c',c/'clock.c');shutil.copy2(Path(__file__),c/'setup.py')
shutil.copy2(w/'docs/RECORDING_PREALLOCATION_PROTOCOL.md',c/'PROTOCOL.md')
