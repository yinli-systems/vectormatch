from pathlib import Path
import json,shutil,subprocess,hashlib,sys
p=Path(__file__).parent;c=p/'cloud';c.mkdir(exist_ok=False);old=p.parent/'recording-preallocation-20261027-r1/cloud';w=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards')
oldid='recording-preallocation-20261027-r1';newid='force-wait-decomposition-20261027-r1'
for name in ['controller.py','process_agent.py','close_case.py','archive_closed.py','archive_runtime.py','stage.py']:
 s=(old/name).read_text().replace(oldid,newid).replace('recording-preallocation-r1','force-wait-decomposition-r1');(c/name).write_text(s)
plan=json.loads((old/'PLAN.json').read_text());plan['cases']={}
for name,seconds,enabled in [('functional-a',2,False),('functional-b',2,True),('observer-a1',60,False),('observer-b1',60,True),('observer-a2',60,False),('observer-b2',60,True)]:
 plan['cases'][name]=dict(mode='MATCHING',seconds=seconds,rate=10 if name.startswith('functional')else 100,maxParkNs=1000000,traceEnabled=True,preallocate=False,forceWait=enabled)
plan['scope']='same-host force CPU/resource envelopes and own-thread kernel state/wchan; stage tracing ON, same artifact, sync2, G1, affinity, leader0, 1ms park and overlay storage'
plan['selection']='Observer OFF/ON/OFF/ON; preserve all originals and observer effects. Do not call probe a performance optimization. Close all six arms before freezing an optimization hypothesis. Exact runnable and storage durations unavailable: disabled kernel accounting.'
(c/'PLAN.json').write_text(json.dumps(plan,indent=2)+'\n')
s=(c/'controller.py').read_text();s=s.replace("props=['-Dvectormatch.stage.preallocate=", "props=['-Dvectormatch.forceWait.enabled='+str(spec['forceWait']).lower(),'-Dvectormatch.forceWait.library='+ROOT+'/libvmforce.so','-Dvectormatch.forceWait.directory='+prefix+'/force-wait/node%d-g0'%role,'-Dvectormatch.stage.preallocate=")
s=s.replace(";capture_allocation(case);start(config(3,case,collector,seconds,qualification,probe))", ";start(config(3,case,collector,seconds,qualification,probe))")
s=s[:s.index('\ndef capture_allocation(case):')];(c/'controller.py').write_text(s)
s=(c/'close_case.py').read_text().replace("ROOT+'/audit-recording-preallocation.py'","ROOT+'/audit-force-wait.py'").replace("names=['RECORDING_ALLOCATION.json','AUDIT.json'","names=['AUDIT.json'")
s=s.replace("print(json.dumps({n:(p/n).read_text()for n in names", "names += [str(f.relative_to(p)) for f in (p/'force-wait').rglob('*') if f.is_file() and (f.name.endswith('complete.json') or f.name=='clock.txt')]\nprint(json.dumps({n:(p/n).read_text()for n in names")
(c/'close_case.py').write_text(s)
s=(c/'archive_closed.py').read_text();a=s.index(' assert name in [');b=s.index('\n',a);s=s[:a]+' assert name in '+repr(list(plan['cases']))+s[b:];(c/'archive_closed.py').write_text(s)
(c/'lib').mkdir()
for f in (w/'cluster/build/install/cluster/lib').glob('*.jar'):shutil.copy2(f,c/'lib'/f.name)
shutil.copy2(w/'cluster/build/libs/vectormatch-soak-agent-0.1.0-SNAPSHOT.jar',c/'soak-agent.jar')
for n in ['audit-replicated-path-probe.py','audit-force-wait.py']:shutil.copy2(w/'scripts'/n,c/n)
# Preserve the pre-existing working-tree edit. Candidate uses the previously committed stage auditor.
(c/'audit-replicated-stage-trace.py').write_bytes(subprocess.check_output(['git','show','HEAD:scripts/audit-replicated-stage-trace.py'],cwd=w))
shutil.copy2(old/'libvmclock.so',c/'libvmclock.so');shutil.copy2(p/'native-qualification/libvmforce.so',c/'libvmforce.so')
for n in ['native-qualification.tar.gz','NATIVE_BUILD.json','NATIVE_QUALIFICATION_MANIFEST.json','NATIVE_QUALIFICATION_VERIFIED.json','probe-result.json','observation-qualification.json','probe.py','qualify_observation.py','collect_qualification.py']:shutil.copy2(p/n,c/n)
for src,dst in [('stage-patch.jar','stage-patch.jar'),('MANIFEST.json','PATCH_MANIFEST.json'),('instrumentation.patch','instrumentation.patch')]:shutil.copy2(p/'patch-r1'/src,c/dst)
for typ in ['original','modified']:
 for f in (p/'patch-r1'/typ).glob('*.java'):shutil.copy2(f,c/(typ+'-'+f.name))
for n in ['clock.c','force_wait.c']:shutil.copy2(w/'tools/replicated-stage-probe'/n,c/n)
shutil.copy2(Path(__file__),c/'setup.py');shutil.copy2(w/'docs/FORCE_WAIT_PROTOCOL.md',c/'PROTOCOL.md')
