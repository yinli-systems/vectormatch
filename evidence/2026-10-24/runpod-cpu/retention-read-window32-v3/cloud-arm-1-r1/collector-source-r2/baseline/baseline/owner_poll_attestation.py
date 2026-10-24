"""Pure constructed-owner + unchanged driver/node evidence gate; no IO or process actions.

Callers must first bind every JSON/argv payload to the closed raw inventory and exact
registered process identities. Selection intent alone never passes this gate.
"""
from idle_attestation import validate_actual, selection as driver_selection
OWNER_PROPERTY='vectormatch.retention.ownerPollMaxParkNs'
DRIVER_PROPERTY='vectormatch.retention.idleMaxParkNs'

def require(value,message):
    if not value:raise RuntimeError(message)

def expected_owner_selection(maximum):
    require(type(maximum)is int and maximum in (1000000,100000),'Canonical explicit owner cap required')
    return {'schema':'retention-owner-poll-selection-v1','property':OWNER_PROPERTY,
            'maximumParkNs':maximum,'factor':'owner poll requested park cap only','hardRealtimeGuaranteed':False}

def expected_wait_policy(maximum):
    expected_owner_selection(maximum)
    return 'deadline-aware park up to '+('1ms'if maximum==1000000 else'100us')+'; OS lateness is not bounded'

def properties(arguments,property_name):
    require(isinstance(arguments,list)and arguments and all(isinstance(v,str)and v for v in arguments),'Actual full argv required')
    key='-D'+property_name
    return [v for v in arguments if v==key or v.startswith(key+'=')]

def validate_owner_bundle(*,registration,configuration,summary,before,after,parent,nodes,
                          expected_owner_cap,expected_parent_arguments,expected_node_arguments,
                          node_idle_actuals,parent_idle_actuals):
    selected=expected_owner_selection(expected_owner_cap);wait=expected_wait_policy(expected_owner_cap)
    for label,value in [('registration',registration),('configuration',configuration),('summary',summary)]:
        require(value.get('ownerPollSelection')==selected,label+' owner selection missing or differs')
        require(value.get('retentionIdleSelection')==driver_selection(100000),label+' unchanged100us driver selection differs')
    expected_actual={'available':True,'schema':'retention-owner-poll-actual-v1',
                     'source':'actual-constructed-owner-snapshot','ownerPollMaxParkNs':expected_owner_cap,
                     'waitPolicy':wait,'requestedSleepOnly':True,'osLatenessBounded':False}
    for label,value in [('configuration',configuration),('summary',summary)]:
        require(value.get('ownerPollActual')==expected_actual,label+' must attest the actual constructed owner')
    for label,value,alive in [('before',before,True),('after',after,False)]:
        require(value.get('ownerPollMaxParkNs')==expected_owner_cap and value.get('waitPolicy')==wait
                and value.get('ownerPollRequestedSleepOnly')is True and value.get('ownerPollOsLatenessBounded')is False
                and value.get('ownerThreadAlive')is alive,label+' actual owner snapshot cap/wait/scope/lifecycle differs')
    require(configuration.get('batchFlushNs')==before.get('flushDeadlineNs')==after.get('flushDeadlineNs')==50000,
            'Independent50us batch flush changed with owner polling cap')
    require(type(parent.get('pid'))is int and parent['pid']>1,'Actual parent PID required')
    require(parent.get('arguments')==expected_parent_arguments,'Exact registered parent full argv differs')
    require(properties(parent['arguments'],OWNER_PROPERTY)==['-D'+OWNER_PROPERTY+'='+str(expected_owner_cap)]
            and properties(parent['arguments'],DRIVER_PROPERTY)==['-D'+DRIVER_PROPERTY+'=100000'],
            'Parent must explicitly select owner cap and unchanged100us driver exactly once')
    require(set(nodes)==set(expected_node_arguments)==set(node_idle_actuals)=={0,1,2},'Exact three actual node identities/argv/idle records required')
    pids={parent['pid']};node_reports=[]
    for member in (0,1,2):
        node=nodes[member];pid=node.get('pid');arguments=node.get('arguments')
        require(type(pid)is int and pid>1 and pid not in pids,'Distinct actual node PID required');pids.add(pid)
        require(arguments==expected_node_arguments[member],'Exact registered node full argv differs')
        require(not properties(arguments,OWNER_PROPERTY) and properties(arguments,DRIVER_PROPERTY)==['-D'+DRIVER_PROPERTY+'=100000'],
                'Child must have no owner property and exactly unchanged100us node/driver property')
        node_reports.append(validate_actual(node_idle_actuals[member],100000,pid,member))
    require(isinstance(parent_idle_actuals,list)and parent_idle_actuals,'Actual owner-driver factory observations required')
    parent_reports=[validate_actual(value,100000,parent['pid'],-1)for value in parent_idle_actuals]
    creations=sum(v['actualFactoryCreations']for v in node_reports)+parent_reports[-1]['actualFactoryCreations']
    require(creations==22,'Exact configured22factory-object closure required')
    return {'passed':True,'schema':'retention-owner-poll-bundle-v1','ownerPollMaximumParkNs':expected_owner_cap,
            'serverDriverMaximumParkNs':100000,'selectionIntentAndConstructedOwnerSnapshotReconciled':True,
            'ownerBeforeAliveAfterStopped':True,'exactRegisteredParentAndThreeNodeArgumentsVerified':True,
            'ownerPropertyParentOnly':True,'actualConfiguredIdleFactoryCreations':creations,
            'ownerDriverObservationCount':len(parent_reports),'nodeIdleReports':node_reports,
            'parentIdleReport':parent_reports[-1],'actualSleepDurationMeasured':False,
            'hardRealtimeOrPerformanceClaimed':False,
            'scope':'Pure evidence reconciliation; caller separately proves archive bytes, PID/start/argv ownership, business/canonical/raw correctness and closed lifecycle'}
