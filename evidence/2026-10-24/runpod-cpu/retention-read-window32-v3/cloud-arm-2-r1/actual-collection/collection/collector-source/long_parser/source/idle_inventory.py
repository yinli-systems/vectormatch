"""Exact prior native-r2 validator function; factory objects, not measured sleeps/threads."""
def validate_idle(actual,maximum,node,pid):
 require(actual['schema']=='retention-idle-actual-v2' and actual['node']==node and actual['pid']==pid,'Actual idle association differs')
 require(actual['selection']['maximumParkNs']==maximum and actual['selection']['property']=='vectormatch.retention.idleMaxParkNs','Actual idle selection differs')
 require(actual['instancesDistinct'] is True and actual['sleepDurationMeasured'] is False and actual['hardRealtimeGuaranteed'] is False and actual['runningAgentThreadCountIndependentlyObserved'] is False,'Idle witness scope differs')
 expected={'owner-driver-shared':1} if node<0 else {'driver-shared':1,'archive-shared':2,'consensus':2,'service':2}
 require(actual['expectedConsumptionCounts']==actual['observedConsumptionCounts']==expected and set(actual['selectedLogicalRoles'])==set(expected),'Per-role exact factory inventory differs')
 instances=actual['instances'];total=sum(expected.values())
 require(len(instances)==total and {v['instanceOrdinal'] for v in instances}==set(range(1,total+1)),'Distinct actual creation inventory differs')
 consumers={'archive-shared':('io.aeron.archive.ArchiveConductor','io.aeron.archive.Archive'),'consensus':('io.aeron.cluster.ConsensusModuleAgent','io.aeron.cluster.ConsensusModule'),'service':('io.aeron.cluster.service.ClusteredServiceAgent','io.aeron.cluster.service.ClusteredServiceContainer')}
 contexts={'archive-shared':'io.aeron.archive.Archive$Context','consensus':'io.aeron.cluster.ConsensusModule$Context','service':'io.aeron.cluster.service.ClusteredServiceContainer$Context'}
 observed={role:set() for role in expected}
 for row in instances:
  role=row['role'];ordinal=row['roleConsumptionOrdinal'];require(role in expected and 1<=ordinal<=expected[role] and ordinal not in observed[role],'Per-role consumption ordinal differs');observed[role].add(ordinal)
  yields=5 if 'driver' in role else 20
  expected_text=f'BackoffIdleStrategy{{alias=backoff, maxSpins=10, maxYields={yields}, minParkPeriodNs=1000, maxParkPeriodNs={maximum}}}'
  require(row['strategyClass']=='org.agrona.concurrent.BackoffIdleStrategy' and row['strategyDescription']==expected_text,'Actual supplied strategy differs')
  require((row['maximumSpins'],row['maximumYields'],row['minimumParkNs'],row['maximumParkNs'],row['roleConsumptionBound'])==(10,yields,1000,maximum,expected[role]),'Actual configured tuple/bound differs')
  trace=row['factoryCallerStack'];require(1<=len(trace)<=5 and row['factoryCallerFrameLimit']==5 and row['factoryCallerTextByteLimit']==256,'Caller trace bound differs')
  for frame in trace:require(len(frame['class'].encode())<=256 and len(frame['method'].encode())<=256,'Caller strings exceed byte bound')
  require(not trace[0]['classTruncated'] and not trace[0]['methodTruncated'],'Head consumer frame truncated')
  if 'driver' in role:
   expected_class='io.vectormatch.cluster.RetentionNodeMainV3' if node>=0 else 'io.vectormatch.cluster.RetentionBatchAeronTransportV3'
   require(trace[0]['class']==expected_class,'Direct driver creator differs')
   require(row['association']=='actual installed shared-driver getter object','Direct driver association differs')
  else:
   require(len(trace)>=2 and trace[0]['class']==contexts[role] and trace[0]['method']=='idleStrategy','Observed factory context call differs')
   require(trace[1]['class']==consumers[role][ordinal-1] and trace[1]['method']=='<init>','Observed pinned constructor consumer differs')
   require('source-ordered factory consumption' in row['association'],'Factory/runner inference scope differs')
  require(row['sourceDerivedIntendedUse'],'Missing source-derived intended use')
 require(all(observed[role]==set(range(1,count+1)) for role,count in expected.items()),'Per-role creation sequence incomplete')
 return {'node':node,'pid':pid,'maximumRequestedParkNs':maximum,'selectedLogicalRoles':sorted(expected),'factoryCreations':total,'perRoleConsumptions':expected,'configuredObjectsAndCallerStacksAttested':True,'sleepDurationMeasured':False,'activeThreadCountClaimed':False}
