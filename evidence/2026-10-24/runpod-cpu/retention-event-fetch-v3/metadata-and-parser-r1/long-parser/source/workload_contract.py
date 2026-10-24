"""Exact admitted long preset, distinct from the unchanged6400 default/CPU gates."""
from typing import NamedTuple
from event_fetch_contract import selected_page


class Workload(NamedTuple):
    arrivals:int;rate:int;cycles:int;phases:int;final_business:int;final_events:int;final_market:int


LONG=Workload(33792,500,12,24,33795,67587,67585)


def require(value,message):
    if not value:raise AssertionError(message)


def contract(value):
    require(type(value) is Workload and value==LONG,'Only the explicit admitted33792 long preset is supported')
    return value


def validate_plan(plan,workload):
    w=contract(workload)
    require(plan['admitted'] is True and plan['arrivals']==w.arrivals and plan['maximumMaintenanceCycles']==w.cycles
        and plan['maximumEvents']==w.final_events and plan['requestedReadWindow']==8,'Exact admitted long prospective plan differs')
    require(w.phases==2*plan['maximumMaintenanceCycles'],'Read-phase bound must derive from admitted cycle bound')
    return w.phases


def validate_actual_plan_observation(observation,registered_plan,actual_code,*,event_fetch_count):
    selected_page(event_fetch_count)
    require(observation['actualCodeFingerprint']==actual_code and set(observation['plans'])=={'16','32'},'Captured actual-JAR selected page/code differs')
    allowed={'eventFetchCount','selectedMaximumLogicalMaintenanceRpcs','selectedMaximumEventFetchRpcs'}
    values=[]
    for page in(16,32):
        row=observation['plans'][str(page)];plan=row['plan']
        require(row['configuration']['eventFetchCount']==page and row['configuration']['commonEventFetchEnvelope']is True
            and plan['eventFetchCount']==page and plan['commonEventFetchEnvelope']is True,'Captured actual-JAR page/common envelope differs')
        values.append({k:v for k,v in plan.items()if k not in allowed})
    require(values[0]==values[1] and observation['plans'][str(event_fetch_count)]['plan']==registered_plan,
        'Captured actual-JAR selected full plan/common operational envelope differs')


def scheduler_gate(late_count,reported_valid,*,local_functional_only=False):
    require(type(local_functional_only)is bool and type(reported_valid)is bool and type(late_count)is int and late_count>=0,'Explicit scheduler admission types required')
    valid=late_count==0;require(reported_valid==valid,'Source scheduler timing flag differs from raw lateness')
    require(valid or local_functional_only,'Scheduler timing INVALID: performance admission refused by default')
    return {'schedulerTimingValid':valid,'localFunctionalDiagnosticOptIn':local_functional_only,'performanceAdmissionAllowed':valid and not local_functional_only}


def validate_setup_commands(commands):
    expected=[{'type':1,'account':1,'producer':'fund','seq':1,'asset':0,'amount':LONG.arrivals},
              {'type':1,'account':2,'producer':'fund','seq':1,'asset':1,'amount':LONG.arrivals*10},
              {'type':2,'account':1,'producer':'seed','seq':1,'client':'v3:1:seed:1','side':1,'price':10,'quantity':LONG.arrivals,'tif':0}]
    require(commands==expected,'Exact long setup funding/maker identity/amount differs; old6400 setup is insufficient')


def validate_terminal_row(row):
    require(row['status']=='APPLIED' and row['result_code']=='ACCEPTED' and row['unknown_observed_offset_ns']==''
        and row['not_sent_reason']=='0' and row['reply_replayed']=='false' and row['initial_server_admission_status']=='',
        'Unexpected terminal/UNKNOWN/rejection/replay in long original identities')


def validate_business_answer(answer,batch):
    require(answer['index']==batch and answer['status']==0 and answer['result']['code']==0 and not answer['replayed'],
        'Long business wire result/status/replay mismatch')


def validate_cycle_frontiers(cycles,phase_report,workload):
    w=contract(workload)
    require(len(cycles)==w.cycles and [c['cycle']for c in cycles]==list(range(1,w.cycles+1)),'Exact12 ordered maintenance cycles required')
    require([c['throughCommandSeq']for c in cycles]==[3072*n for n in range(1,12)]+[w.final_business],'Eleven full command cuts plus final3-command partial required')
    phases=phase_report['readPhases']
    require(len(phases)==w.phases and [p['generation']for p in phases]==list(range(1,w.phases+1)),'Exact24 consecutive read phases required')
    require([p['kind']for p in phases]==['ArchiveChunk','FetchEvents']*w.cycles,'Every cycle must have ordered archive/event read phases')


def validate_final(final):
    require((final['businessSeq'],final['eventSeq'],final['marketSeq'],final['exportedEventSeq'],final['leaderMemberId'])
        ==(LONG.final_business,LONG.final_events,LONG.final_market,LONG.final_events,0),'Exact long final business/event/market/export/leader frontiers differ')
