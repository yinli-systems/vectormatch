#!/usr/bin/env python3
"""Audit a pre-registered allocation-only arm, including original stage joins."""
from pathlib import Path
import argparse,importlib.util,json,re

def load(name,file):
 s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def allocation(root):
 p=Path(root);proof=json.loads((p/'RECORDING_ALLOCATION.json').read_text());modes=[];markers=[]
 assert len(proof['roles'])==3
 for role in range(4):
  launch=json.loads((p/f'node{role}-g0/LAUNCH.json').read_text());argv=launch['argv']
  mode=[a for a in argv if a.startswith('-Dvectormatch.stage.preallocate=')];assert len(mode)==1 and mode[0].split('=')[1]in['true','false'];enabled=mode[0].endswith('=true');modes.append(enabled)
  assert '-Dvectormatch.stage.trace=true'in argv
  if role==3:continue
  r=proof['roles'][role];assert r['role']==role and len(r['files'])==1 and r['capturedMonotonicNs']<json.loads((p/'evidence/window.json').read_text())['originNs']
  text=(p/f'node{role}-g0/stdout.log').read_text();lines=[l for l in text.splitlines()if l.startswith('VECTOR_RECORDING_PREALLOC ')]
  if enabled:assert len(lines)==1
  else:assert not lines
  for f in r['files']:
   target=p/f['relative'];assert target.is_file() and f['logicalBytes']==128*1024**2 and f['device']==48 and f['inode']>0
   assert f['allocatedBytes']>0 and f['allocatedBytes']<=f['logicalBytes'] and target.stat().st_size==f['logicalBytes']
   if enabled:
    assert f['allocatedBytes']==f['logicalBytes']
    m=re.fullmatch(r'VECTOR_RECORDING_PREALLOC path=(\S+) logicalBytes=(\d+) allocatedBytes=(\d+) durationNs=(\d+) keepSize=true syncUnchanged=true',lines[0]);assert m and m[1].endswith('/experiments/'+p.name+'/'+f['relative']) and int(m[2])==f['logicalBytes'] and int(m[3])==f['allocatedBytes'];markers.append({'role':role,'durationNs':int(m[4])})
 assert len(set(modes))==1
 return {'enabled':modes[0],'allThreeRecordingsVerifiedBeforeArrivals':True,'recordings':proof['roles'],'startupAllocation':markers,'scope':'Linux fallocate KEEP_SIZE; same overlay device and sync level 2; no crash-durability certification'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--jfr',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 v=load('base','audit-replicated-path-probe.py').audit(a.root,a.jfr);v['allocation']=allocation(a.root);v['stages']=load('stages','audit-replicated-stage-trace.py').audit_stages(a.root)
 a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'case':v['case'],'allocation':v['allocation']['enabled'],'fullLatency':v['fullLatency'],'gate':v['registeredGatePass']}))
