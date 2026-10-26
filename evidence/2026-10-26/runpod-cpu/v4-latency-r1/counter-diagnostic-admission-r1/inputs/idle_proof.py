"""Closed-run configured instance proof for both original and cold-restored nodes."""
from pathlib import Path
import json
from idle_attestation import validate_actual,selection

def validate(root,owned,maximum):
 root=Path(root)
 for p in [root,*root.parents]:assert not p.is_symlink()
 parents=[r for r in owned if r['role']=='parent'];assert len(parents)==1;parent=parents[0]
 nodes=[r for r in owned if r['role']=='node'];assert len(nodes)==6
 reports=[];all_pids=set()
 for node in range(3):
  records=[r for r in nodes if int(r['member'])==node];assert len(records)==2
  pids={r['pid']for r in records};assert len(pids)==2 and not pids&all_pids;all_pids.update(pids)
  folder=root/f'node-{node}/idle-observations';assert folder.is_dir()and not folder.is_symlink()and not folder.parent.is_symlink()
  expected={f'idle-{slot:03}.{kind}.json'for slot in [0,1]for kind in ['intent','actual']};assert {p.name for p in folder.iterdir()}==expected
  observed=set()
  for slot in [0,1]:
   paths=[folder/f'idle-{slot:03}.{kind}.json'for kind in ['intent','actual']]
   for p in paths:assert p.is_file()and not p.is_symlink()and p.stat().st_size<=1024**2
   intent,actual=[json.loads(p.read_text())for p in paths];pid=actual['pid'];assert pid in pids and pid not in observed;observed.add(pid)
   assert set(intent)=={'schema','slot','node','pid','atUTC','selection'}and intent['schema']=='retention-idle-startup-intent-v1'and type(intent['slot'])is int and intent['slot']==slot and intent['node']==node and intent['pid']==pid and intent['selection']==selection(maximum)
   report=validate_actual(actual,maximum,pid,node)
   lines=(root/f'node-{node}-g{slot+1}.log').read_text().splitlines();logged=[json.loads(s.split('VECTOR_V3_IDLE_ATTESTATION ',1)[1])for s in lines if s.startswith('VECTOR_V3_IDLE_ATTESTATION ')]
   assert logged==[actual];reports.append(dict(report,node=node,generation=slot+1,pid=pid))
  assert observed==pids
  marker=root/f'node-{node}/V3_IDENTITY.txt';assert marker.is_file()and not marker.is_symlink()and marker.read_text().endswith('\nsync=2\nidleMaxParkNs='+str(maximum)+'\n')
 summary=json.loads((root/'load/load-result.json').read_text());registration=json.loads((root/'registration.json').read_text())
 assert summary['retentionIdleSelection']==registration['retentionIdleSelection']==selection(maximum)
 samples=json.loads((root/'load/transport-observations.json').read_text());assert isinstance(samples,list)and samples
 for sample in samples:
  assert sample['leaderMemberId']==0 and sample['leadershipTermId']==0 and sample['newLeaderEvents']==[]
  assert sample['mtuLength']==1248 and sample['archiveChunkBytes']==6144 and sample['profileSha256']==registration['profile']and sample['lineageId']==registration['lineage']
  reports.append(validate_actual(sample['retentionIdlePolicy'],maximum,parent['pid'],-1))
 terminal=summary['physicalOfferTape']['lastActualTransportObservation'];assert terminal['leaderMemberId']==0 and terminal['leadershipTermId']==0 and terminal['newLeaderEvents']==[];validate_actual(terminal['retentionIdlePolicy'],maximum,parent['pid'],-1)
 return dict(passed=True,allSixOriginalAndColdNodeProcessesBound=True,allRecordedLeaderObservationsZeroAndNoClientObservedTermChange=True,configuredMaximumParkNs=maximum,reports=reports,actualSleepDurationMeasured=False,runningAgentThreadCountIndependentlyObserved=False,scope='Direct installed shared-driver getter objects and source-associated bounded factory consumptions;not observed OS sleeps or private-agent-field readback')
