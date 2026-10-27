from pathlib import Path
import json,hashlib,shutil,subprocess
P=Path(__file__).resolve().parent;W=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards')
old=P.parent.parent/'replicated-path-probe-20261027-r2/cloud'
plan=json.loads((old/'PLAN.json').read_text());plan['cases']={}
for name,seconds,on in [('functional-off',2,False),('functional-on',2,True),('trace-a1',30,False),('trace-b1',30,True),('trace-a2',30,False),('trace-b2',30,True)]:
 plan['cases'][name]=dict(mode='MATCHING',seconds=seconds,rate=10 if name.startswith('functional')else 100,maxParkNs=1000000,traceEnabled=on)
plan['scope']='same-host request/log-position attribution; shared native CLOCK_MONOTONIC and identical diagnostic Aeron overlay in every arm; fixed sync2, G1, affinity, leader, 1ms park, overlay storage'
plan['selection']='Observer OFF/ON/OFF/ON; do not call instrumentation a performance improvement. Require all native originals auditable. Select a new optimization only after all six arms close.'
(P/'PLAN.json').write_text(json.dumps(plan,indent=2)+'\n')
s=(P/'controller.py').read_text()
needle="props=['-Daeron.cluster.max.sessions=256'";assert needle in s
s=s.replace(needle,"props=['-Dvectormatch.stage.clockLibrary='+ROOT+'/libvmclock.so','-Dvectormatch.stage.directory='+prefix+'/stages/node%d-g0'%role,'-Dvectormatch.stage.capacity=1048576','-Dvectormatch.stage.trace='+str(spec['traceEnabled']).lower(),'-Daeron.cluster.max.sessions=256'")
(P/'controller.py').write_text(s)
s=(P/'process_agent.py').read_text();oldcp="str(root/'lib/*')";assert s.count(oldcp)==1;s=s.replace(oldcp,"str(root/'stage-patch.jar')+':'+str(root/'lib/*')");(P/'process_agent.py').write_text(s)
s=(P/'close_case.py').read_text().replace("ROOT+'/audit-replicated-path-probe.py'","ROOT+'/audit-replicated-stage-trace.py'")
s=s.replace("for i in range(4):names +=", "for i in range(4):names += ['stages/node%d-g0/'%i+n for n in ['clock.txt','complete.json']]\nfor i in range(4):names +=")
(P/'close_case.py').write_text(s)
s=(P/'archive_closed.py').read_text();a=s.index(' assert name in [');b=s.index('\n',a);s=s[:a]+' assert name in '+repr(list(plan['cases']))+s[b:];(P/'archive_closed.py').write_text(s)
s=(P/'stage.py').read_text();s=s.replace("if not f.is_file()or f.suffix=='.pyc':continue", "if not f.is_file()or f.suffix=='.pyc' or f.name.endswith(('.stdout','.stderr','.lock')):continue");(P/'stage.py').write_text(s)
(P/'lib').mkdir()
for f in (W/'cluster/build/install/cluster/lib').glob('*.jar'):shutil.copy2(f,P/'lib'/f.name)
shutil.copy2(W/'cluster/build/libs/vectormatch-soak-agent-0.1.0-SNAPSHOT.jar',P/'soak-agent.jar')
for name in ['audit-replicated-path-probe.py','audit-replicated-stage-trace.py']:shutil.copy2(W/'scripts'/name,P/name)
shutil.copy2(P.parent/'native-clock/libvmclock.so',P/'libvmclock.so');shutil.copy2(P.parent/'native-clock/BUILD.json',P/'NATIVE_CLOCK_BUILD.json')
shutil.copy2(P.parent/'patch-r1/stage-patch.jar',P/'stage-patch.jar');shutil.copy2(P.parent/'patch-r1/MANIFEST.json',P/'PATCH_MANIFEST.json');shutil.copy2(P.parent/'patch-r1/instrumentation.patch',P/'instrumentation.patch')
for f in (P.parent/'patch-r1/original').glob('*.java'):shutil.copy2(f,P/('original-'+f.name))
for f in (P.parent/'patch-r1/modified').glob('*.java'):shutil.copy2(f,P/('patched-'+f.name))
shutil.copy2(W/'tools/replicated-stage-probe/clock.c',P/'clock.c')
candidate=json.loads((old/'CANDIDATE.json').read_text());candidate['sourceCommit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=W,text=True).strip();candidate['files']={}
for f in [*(P/'lib').glob('*.jar'),P/'soak-agent.jar',P/'stage-patch.jar',P/'libvmclock.so',P/'audit-replicated-path-probe.py',P/'audit-replicated-stage-trace.py',P/'process_agent.py']:
 candidate['files'][str(f.relative_to(P))]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size}
(P/'CANDIDATE.json').write_text(json.dumps(candidate,indent=2)+'\n')
print(json.dumps({'sourceCommit':candidate['sourceCommit'],'cases':list(plan['cases']),'files':len(candidate['files'])}))
