"""Offline validation of actual original all-member CnC samples. Never controls a process."""
TYPES={'0','101','200','201','203','207','212','215','239'}
ERRORS={'0','101','212','215'}
REQUIRED=TYPES-{'101'}
def need(value,message):
 if not value:raise ValueError(message)
def validate_readiness(report,member_pids,origin):
 need(report['schema']=='retention-all-member-startup-readiness-v1'and report['passed']is True,'Readiness gate did not pass')
 need(report['quietPeriodNs']==2000000000 and report['deadlineNs']==45000000000,'Original quiet/deadline policy differs')
 need(report['originalErrorLogsRemainStrict']is True and report['readOnlyMappings']is True and report['aeronClientsRegistered']is False and report['atomicSnapshot']is False and report['performedBeforeLoadOrders']is True,'Readiness scope differs')
 start,end=report['startedMonotonicNs'],report['endedMonotonicNs'];need(type(start)is int and start>0 and start<=end<origin and end-start<=45000000000,'Readiness outside admitted pre-arrival interval')
 samples=report['observations'];need(isinstance(samples,list)and 2<=len(samples)<=512 and report['failure']is None and report['failureType']is None,'Original complete readiness rows required')
 last=-1;since=None;position=None;maxGap=0
 for row in samples:
  offset=row['offsetNs'];need(type(offset)is int and last<offset<=end-start,'Original monotonic readiness sample order')
  if last>=0:maxGap=max(maxGap,offset-last)
  last=offset;members=row['members'];need(len(members)==3 and {r['member']for r in members}=={0,1,2},'Original three member samples required');values={};converged=True
  for member in members:
   node=member['member'];need(member['pid']==member_pids[node],'Readiness PID differs from original registered child');counters=member['countersByType'];need(set(counters)<=TYPES,'Unexpected readiness counter type');need(len({c['counterId']for c in counters.values()})==len(counters),'Aliased readiness counter ids');values[node]={k:c['value']for k,c in counters.items()}
   for k,c in counters.items():need(type(c['counterId'])is int and c['counterId']>=0 and type(c['registrationId'])is int and type(c['value'])is int,'Counter identity/value malformed')
   for k in ERRORS&set(counters):need(values[node][k]==0,'Nonzero native startup error')
   converged&=set(counters)>=REQUIRED and 0<=member['heartbeatAgeMillis']<=2000
   if set(counters)>=REQUIRED:converged&=values[node]['200']==1 and values[node]['207']==17 and values[node]['201']==(2 if node==0 else 0)and values[node]['239']==0 and values[node]['203']>=0
  if converged:converged=len({v['203']for v in values.values()})==1
  need(row['allMembersConverged']is converged,'Actual readiness flag does not match original counter values')
  if not converged:since=None;position=None
  else:
   current=values[0]['203']
   if since is None or current!=position:since=offset;position=current
 need(since is not None and last-since>=2000000000,'Original stable sample interval below2s')
 need(maxGap<=500000000,'Readiness sampling gap above500ms; qualification requires review')
 return dict(passed=True,originalPidAndCounterBindingsVerified=True,samples=len(samples),actualFinalQuietNs=last-since,maximumSampleGapNs=maxGap,commitPosition=position,startedMonotonicNs=start,endedMonotonicNs=end,notAtomicOrHardRealtime=True)
