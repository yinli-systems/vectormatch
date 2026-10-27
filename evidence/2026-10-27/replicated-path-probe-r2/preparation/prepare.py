from pathlib import Path
import json,hashlib,shutil,subprocess
P=Path(__file__).resolve().parent;W=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards')
old=P.parent.parent/'replicated-sustained-20261027-r3/cloud'
plan=json.loads((old/'PLAN.json').read_text())
plan.pop('qualifiedCases');plan['cases']={}
for name,mode,seconds in [('functional-noop','NOOP',2),('functional-matching','MATCHING',2),('path-a1','NOOP',30),('path-b1','MATCHING',30),('path-a2','NOOP',30),('path-b2','MATCHING',30),('idle-a1','MATCHING',60),('idle-b1','MATCHING',60),('idle-a2','MATCHING',60),('idle-b2','MATCHING',60),('sustained-r1','MATCHING',1800)]:
 plan['cases'][name]=dict(mode=mode,seconds=seconds,rate=10 if name.startswith('functional')else 100,maxParkNs=100000 if name in ['idle-b1','idle-b2']else 1000000)
plan['selection']='100us only if both paired B accept all originals, no unknown, release max <=20ms, >=99% in-window, p99 <=90% paired A and p999 <=paired A; otherwise explicit1ms'
plan['scope']='same-host replicated diagnostic, source memory tape; sync2 unchanged; NOOP not trading; no continuous export/retention claim'
(P/'PLAN.json').write_text(json.dumps(plan,indent=2)+'\n')
s=(P/'controller.py').read_text();a=s.index('def config(');b=s.index('def start(',a)
s=s[:a]+'''def config(role,case,collector,seconds,qualification,probe=None):
 prefix=ROOT+'/experiments/'+case;run=prefix+'/node%d-g0'%role;spec=PLAN['cases'][case]
 env=dict(VECTOR_AERON_MTU_LENGTH='1248',VECTOR_CLUSTER_HOSTS='127.0.0.1,127.0.0.1,127.0.0.1',VECTOR_CLIENT_EGRESS_HOST='127.0.0.1',VECTOR_OUTBOX_CAPACITY='524288')
 state=prefix+('/evidence'if role==3 else'/state');telemetry=prefix+'/telemetry/node%d-g0'%role
 props=['-Daeron.cluster.max.sessions=256','-Xlog:class+load=info:file='+run+'/class-origins.log','-javaagent:'+ROOT+'/soak-agent.jar='+state+','+telemetry,'-Xlog:gc*,safepoint:file='+run+'/gc.log:time,uptime,level,tags:filecount=2,filesize=10M']
 if role<3:
  props+=['-Daeron.cluster.appointed.leader.id=0','-Dvectormatch.node.dataPathMaxParkNs='+str(spec['maxParkNs'])]
  args=['io.vectormatch.cluster.ReplicatedPathProbeNode',spec['mode'],prefix+'/worker-%d.csv'%role,str(role),prefix+'/state',str(PLAN['portBase']),'2','524288',env['VECTOR_CLUSTER_HOSTS'],'capacity-190k-v1','131072','SHARED']
 else:args=['io.vectormatch.cluster.ReplicatedPathProbe',prefix+'/evidence',str(PLAN['portBase']),str(spec['rate']),str(seconds),spec['mode']]
 return dict(root=ROOT,java=JAVA,boot=PLAN['boot'],host=PLAN['host'],case=case,generation='node%d-g0'%role,deadline=time.time()+seconds+900,environment=env,properties=props,mainArgs=args,collector='G1',cpus=PLAN['cpuSets'][role])
''' + s[b:]
(P/'controller.py').write_text(s)
(P/'lib').mkdir(exist_ok=True)
for f in (W/'cluster/build/install/cluster/lib').glob('*.jar'):shutil.copy2(f,P/'lib'/f.name)
shutil.copy2(W/'cluster/build/libs/vectormatch-soak-agent-0.1.0-SNAPSHOT.jar',P/'soak-agent.jar')
shutil.copy2(W/'scripts/audit-replicated-path-probe.py',P/'audit-replicated-path-probe.py')
candidate=json.loads((old/'CANDIDATE.json').read_text());candidate['sourceCommit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=W,text=True).strip();candidate['files']={}
for f in [*(P/'lib').glob('*.jar'),P/'soak-agent.jar',P/'audit-replicated-path-probe.py',P/'process_agent.py']:
 candidate['files'][str(f.relative_to(P))]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size}
(P/'CANDIDATE.json').write_text(json.dumps(candidate,indent=2)+'\n')
# Build a new, hash-checked installation; no prior campaign is edited.
s=(old/'stage.py').read_text().replace('replicated-sustained-20261027-r3','replicated-path-probe-20261027-r2')
s=s.replace("C=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/benchmarks/process-isolation-20261027-r1/cloud');assert json.loads((C/'COMPLETE.json').read_text())['all20OriginalGroupsClosed']",'')
(P/'stage.py').write_text(s)
