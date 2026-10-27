#!/usr/bin/env python3
"""Add actual mapped-device proof to the original-frame replicated-path audit."""
from pathlib import Path
import argparse,importlib.util,json,os

def verify_layout(root):
 root=Path(root);host=json.loads((root/'host.json').read_text());medium=None;roles=[]
 assert len(set(host['durableStateDevices']))==1 and host['durableStateDevices'][0]==host['overlayDevice']!=host['tmpfsDevice']
 for role in range(4):
  launch=json.loads((root/f'node{role}-g0/LAUNCH.json').read_text());maps=json.loads((root/f'node{role}-g0/DRIVER_MAPPINGS.json').read_text());assert maps['pid']==launch['pid'] and maps['boot']==launch['boot']
  flags=[x for x in launch['argv']if x.startswith('-Dvectormatch.probe.driverRoot=')];assert len(flags)<=1
  this='tmpfs'if flags else'overlay';assert medium is None or medium==this;medium=this
  leaf=f'node-{role}'if role<3 else'load'
  argv=launch['argv']
  if flags:prefix=flags[0].split('=',1)[1]+'/'+leaf+'/'
  elif role<3:prefix=argv[argv.index('io.vectormatch.cluster.ReplicatedPathProbeNode')+4]+f'/node-{role}/driver/'
  else:prefix=argv[argv.index('io.vectormatch.cluster.ReplicatedPathProbe')+1]+'/driver/'
  expected=host['tmpfsDevice']if flags else host['overlayDevice'];paths=[]
  for line in maps['maps']:
   x=line.split(None,5);path=x[5];assert path.startswith(prefix),path
   major,minor=[int(v,16)for v in x[3].split(':')];assert os.makedev(major,minor)==expected
   paths.append(path)
  assert any(p.endswith('/cnc.dat')for p in paths)
  if flags:assert 'filesystem=tmpfs durableStateRelocated=false'in(root/f'node{role}-g0/stdout.log').read_text()
  roles.append(dict(role=role,medium=this,mappedDevice=expected,driverPrefix=prefix,mappingCount=len(paths),cncObserved=True))
 return dict(medium=medium,roles=roles,durableStateDevices=host['durableStateDevices'],durableStateRemainsOnOriginalOverlay=True)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--jfr',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 spec=importlib.util.spec_from_file_location('probe_audit',Path(__file__).with_name('audit-replicated-path-probe.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 v=m.audit(a.root,a.jfr);v['driverLayout']=verify_layout(a.root);a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({k:v[k]for k in ['case','counts','fullLatency','registeredGatePass','driverLayout']}))
