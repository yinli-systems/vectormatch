#!/usr/bin/env python3
"""Verify fresh initialization receipts, unchanged sync2, and exact original force/stage joins."""
from pathlib import Path
import argparse,importlib.util,json,re,hashlib

def load(name,file):
 s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def initialization(root):
 p=Path(root);proof=json.loads((p/'RECORDING_INITIALIZATION.json').read_text());modes=[];markers=[]
 assert proof['beforeSourceLaunch'] and proof['settleSeconds']==30 and len(proof['roles'])==3
 assert proof['captureStartedMonotonicNs']-proof['readyObservedMonotonicNs']>=30_000_000_000
 h=hashlib.sha256()
 for _ in range(128):h.update(bytes(1024**2))
 expected=h.hexdigest();origin=json.loads((p/'evidence/window.json').read_text())['originNs']
 for role in range(4):
  launch=json.loads((p/f'node{role}-g0/LAUNCH.json').read_text());argv=launch['argv']
  mode=[a for a in argv if a.startswith('-Dvectormatch.stage.initializeRecording=')];assert len(mode)==1 and mode[0].split('=')[1]in['true','false'];enabled=mode[0].endswith('=true');modes.append(enabled)
  assert '-Dvectormatch.stage.trace=true'in argv and '-Dvectormatch.forceWait.enabled=true'in argv and '-Dvectormatch.stage.preallocate=false'in argv and '-Dvectormatch.stage.capacity=2097152'in argv
  if role==3:continue
  assert argv[-6]=='2'
  r=proof['roles'][role];assert r['role']==role and len(r['files'])==1 and r['capturedMonotonicNs']<origin
  lines=[l for l in(p/f'node{role}-g0/stdout.log').read_text().splitlines()if l.startswith('VECTOR_RECORDING_INITIALIZED ')]
  assert len(lines)==(1 if enabled else 0)
  for f in r['files']:
   target=p/f['relative'];assert target.is_file() and f['logicalBytes']==128*1024**2 and f['device']==48 and f['inode']>0
   assert f['allocatedBytes']>0 and f['allocatedBytes']<=f['logicalBytes'] and target.stat().st_size==f['logicalBytes'] and re.fullmatch('[0-9a-f]{64}',f['sha256BeforeSource'])
   if enabled:
    assert f['allocatedBytes']==f['logicalBytes']
    m=re.fullmatch(r'VECTOR_RECORDING_INITIALIZED path=(\S+) logicalBytes=(\d+) sha256=([0-9a-f]{64}) durationNs=(\d+) forceNs=(\d+) createNew=true forceMetadata=true readbackVerified=true syncUnchanged=true',lines[0]);assert m and m[1].endswith('/experiments/'+p.name+'/'+f['relative']) and int(m[2])==f['logicalBytes'] and m[3]==expected
    assert 0<=int(m[5])<=int(m[4]);markers.append({'role':role,'durationNs':int(m[4]),'forceNs':int(m[5]),'zeroReadbackSha256':m[3]})
 assert len(set(modes))==1
 return {'enabled':modes[0],'allThreeRecordingsVerifiedBeforeArrivals':True,'recordings':proof['roles'],'startupInitialization':markers,'scope':'fresh CREATE_NEW, full zero-write/readback and force(true); same overlay and sync2; startup cost excluded from arrival latency and reported separately; no rollover/recovery claim'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--jfr',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 v=load('base','audit-replicated-path-probe.py').audit(a.root,a.jfr);v['initialization']=initialization(a.root);v['stages']=load('stages','audit-replicated-stage-trace.py').audit_stages(a.root);v['forceWait']=load('force','audit-force-wait.py').audit_wait(a.root)
 a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'case':v['case'],'initialization':v['initialization']['enabled'],'fullLatency':v['fullLatency'],'gate':v['registeredGatePass']}))
