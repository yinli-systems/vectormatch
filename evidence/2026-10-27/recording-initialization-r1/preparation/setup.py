from pathlib import Path
import json,shutil,subprocess
p=Path(__file__).parent;c=p/'cloud';c.mkdir(exist_ok=False);old=p.parent/'force-wait-decomposition-20261027-r1/cloud';w=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards')
for name in ['controller.py','process_agent.py','close_case.py','archive_closed.py','archive_runtime.py','stage.py','prepare.py']:
 s=(old/name).read_text().replace('force-wait-decomposition-20261027-r1','recording-initialization-20261027-r1').replace('force-wait-decomposition-r1','recording-initialization-r1');(c/name).write_text(s)
plan=json.loads((old/'PLAN.json').read_text());plan['cases']={}
for name,seconds,enabled in [('functional-a',2,False),('functional-b',2,True),('initialization-a1',60,False),('initialization-b1',60,True),('initialization-a2',60,False),('initialization-b2',60,True),('sustained-b1',1800,True)]:
 plan['cases'][name]=dict(mode='MATCHING',seconds=seconds,rate=10 if name.startswith('functional')else 100,maxParkNs=1000000,traceEnabled=True,preallocate=False,forceWait=True,initializeRecording=enabled)
plan['scope']='same-host sync2, identical force/stage diagnostics ON, stage capacity 2097152, 30-second pre-source settle and full recording capture; sole A/B switch fresh recording zero-write/force/readback initialization; no physical failure domain or high-rate claim'
plan['selection']='First six originals in order. Every A/B source/completion/correctness gate and exact joins must pass, states must agree. Both B latency gates must pass: p99<=25ms,p999<=100ms,every-minute-p99<=25ms. Baseline A latency failures remain reported but do not block selection. EACH pair B/A p99<=0.90,p999<=1.00. Only then run sustained-b1 1800s in same configuration. No default promotion.'
plan['settleSeconds']=30;plan['stageCapacity']=2097152
(c/'PLAN.json').write_text(json.dumps(plan,indent=2)+'\n')
s=(c/'controller.py').read_text().replace("props=['-Dvectormatch.forceWait.enabled=", "props=['-Dvectormatch.stage.initializeRecording='+str(spec['initializeRecording']).lower(),'-Dvectormatch.forceWait.enabled=").replace('stage.capacity=1048576','stage.capacity=2097152')
s=s.replace("save(P/(case+'-nodes-ready.json'),ss);start(config(3,case,collector,seconds,qualification,probe))", "save(P/(case+'-nodes-ready.json'),ss);capture_initialization(case);start(config(3,case,collector,seconds,qualification,probe))")
s+='\n'+(p/'capture-function.py.txt').read_text();(c/'controller.py').write_text(s)
s=(c/'close_case.py').read_text().replace("ROOT+'/audit-force-wait.py'","ROOT+'/audit-recording-initialization.py'").replace("names=['AUDIT.json'","names=['RECORDING_INITIALIZATION.json','AUDIT.json'")
(c/'close_case.py').write_text(s)
s=(c/'archive_closed.py').read_text();a=s.index(' assert name in [');b=s.index('\n',a);s=s[:a]+' assert name in '+repr(list(plan['cases']))+s[b:];(c/'archive_closed.py').write_text(s)
s=(c/'prepare.py').read_text().replace("old=P.parent.parent/'recording-preallocation-20261027-r1/cloud'","old=P.parent.parent/'force-wait-decomposition-20261027-r1/cloud'")
(c/'prepare.py').write_text(s)
shutil.copy2(p/'campaign.py.txt',c/'campaign.py')
(c/'lib').mkdir()
for f in(w/'cluster/build/install/cluster/lib').glob('*.jar'):shutil.copy2(f,c/'lib'/f.name)
shutil.copy2(w/'cluster/build/libs/vectormatch-soak-agent-0.1.0-SNAPSHOT.jar',c/'soak-agent.jar')
for n in ['audit-replicated-path-probe.py','audit-force-wait.py','audit-recording-initialization.py']:shutil.copy2(w/'scripts'/n,c/n)
(c/'audit-replicated-stage-trace.py').write_bytes(subprocess.check_output(['git','show','HEAD:scripts/audit-replicated-stage-trace.py'],cwd=w))
for n in ['libvmclock.so','libvmforce.so','native-qualification.tar.gz','NATIVE_BUILD.json','NATIVE_QUALIFICATION_MANIFEST.json','NATIVE_QUALIFICATION_VERIFIED.json','probe-result.json']:shutil.copy2(old/n,c/n)
for src,dst in [('stage-patch.jar','stage-patch.jar'),('MANIFEST.json','PATCH_MANIFEST.json'),('instrumentation.patch','instrumentation.patch')]:shutil.copy2(p/'patch-r1'/src,c/dst)
for typ in ['original','modified']:
 for f in(p/'patch-r1'/typ).glob('*.java'):shutil.copy2(f,c/(typ+'-'+f.name))
for n in ['clock.c','force_wait.c']:shutil.copy2(w/'tools/replicated-stage-probe'/n,c/n)
shutil.copy2(Path(__file__),c/'setup.py');shutil.copy2(w/'docs/RECORDING_INITIALIZATION_PROTOCOL.md',c/'PROTOCOL.md')
