"""Read-only bounded one-arm long-cuts control-plane probe.
No project imports, signals, writes, launches, raw parsing or native hashing.
Supply actual root-frozen release/controller SHA and exact launch PID/start/argv.
Default ACTIVE observation reads no completion/raw/native files. A closed PASS
allows independent collection only; it is not an independent raw-capacity proof.
"""
import argparse
import hashlib
import json
import os
import pathlib
import platform
import stat
import time

PREP=pathlib.Path('/opt/vectormatch-cpu/preparation/cpu-long-cuts-cloud-r1')
PROTECTED_SHA='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753'
MAX_PROC=4096
FILES={}
MAXIMUM_PARK_NS=100000
SOURCE_COMMIT='bcf49c10b77a14708b53d3fc6c115a6a3b834408'
CODE_SHA='6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8'
PROFILE_SHA='732201775469861083f9dd0798a465dec1d0ed6bff39ed281dbef58c28b9fc68'


def require(value,message):
    if not value:raise ValueError(message)


def argv_sha(args):return hashlib.sha256(b''.join(os.fsencode(v)+b'\x00' for v in args)).hexdigest()


def bounded(path,cap,optional=False):
    for p in [path]+list(path.parents):require(not p.is_symlink(),'Symlink control path refused')
    try:s=path.stat()
    except FileNotFoundError:
        if optional:return None
        raise
    require(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<=cap,'Nonregular/oversized/hardlinked control file')
    with path.open('rb') as f:data=f.read(cap+1)
    end=path.stat();require(len(data)<=cap and len(data)==end.st_size==s.st_size and end.st_mtime_ns==s.st_mtime_ns,'Control file changed during bounded read')
    FILES[str(path)]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    return data


def js(path,cap=1024**2,optional=False):
    data=bounded(path,cap,optional)
    return None if data is None else json.loads(data)


def process(pid):
    require(type(pid) is int and pid>1,'Invalid registered PID')
    base=pathlib.Path('/proc')/str(pid)
    try:
        before=(base/'stat').read_bytes();require(len(before)<=65536,'Oversized proc stat')
        fields=before[before.rfind(b')')+2:].split();require(len(fields)>19,'Incomplete proc stat')
        state=fields[0].decode('ascii');ticks=int(fields[19])
        if state=='Z':return {'pid':pid,'startTicks':ticks,'state':'Z','running':False}
        with (base/'cmdline').open('rb') as f:raw=f.read(65537)
        require(len(raw)<=65536 and raw.endswith(b'\x00'),'Incomplete/oversized proc argv')
        after=(base/'stat').read_bytes();parts=after[after.rfind(b')')+2:].split()
        require(len(parts)>19 and ticks==int(parts[19]),'Process identity changed during capture')
        return {'pid':pid,'startTicks':ticks,'commandSha256':hashlib.sha256(raw).hexdigest(),'arguments':[os.fsdecode(x) for x in raw[:-1].split(b'\x00')],'state':parts[0].decode('ascii'),'running':parts[0]!=b'Z'}
    except (FileNotFoundError,ProcessLookupError):return None


def identity_state(expected):
    require(type(expected['pid']) is int and expected['pid']>1 and type(expected['startTicks']) is int
            and expected['startTicks']>0 and isinstance(expected['arguments'],list)
            and expected['arguments'] and all(isinstance(v,str) for v in expected['arguments']), 'Complete registered process identity required')
    require(expected['commandSha256']==argv_sha(expected['arguments']),'Registered original argv SHA differs')
    current=process(expected['pid'])
    if current is None:return {'pid':expected['pid'],'originalIdentityRunning':False,'observation':'PID_ABSENT'}
    if current['startTicks']!=expected['startTicks']:return {'pid':expected['pid'],'originalIdentityRunning':False,'observation':'PID_REUSED_DIFFERENT_START_TICKS'}
    if not current['running']:return {'pid':expected['pid'],'originalIdentityRunning':False,'observation':'REGISTERED_IDENTITY_ZOMBIE_NOT_RUNNING','reapedProven':False}
    require(current['commandSha256']==expected['commandSha256'] and current['arguments']==expected['arguments'],'Same-PID/start changed argv; stop classification, never signal')
    return {'pid':expected['pid'],'originalIdentityRunning':True,'observation':'REGISTERED_IDENTITY_RUNNING'}


def live_jvm_pg():
    found=[];count=0
    for folder in pathlib.Path('/proc').iterdir():
        if not folder.name.isdigit() or int(folder.name) in (0,1,os.getpid()):continue
        count+=1;require(count<=MAX_PROC,'Finite proc observation cap exceeded')
        try:
            with (folder/'cmdline').open('rb') as f:raw=f.read(65537)
            require(len(raw)<=65536,'Oversized proc argv during idle observation')
            if not raw:continue
            name=pathlib.Path(os.fsdecode(raw.split(b'\x00',1)[0])).name
            if name not in ('java','javaw','postgres','postmaster'):continue
            value=process(int(folder.name))
            if value and value['running']:found.append({k:value[k] for k in ('pid','startTicks','commandSha256')})
        except (FileNotFoundError,ProcessLookupError):continue
    return found,count


def expected_parent(release,root,maximum):
    return [release['java'],'-Dvectormatch.retention.idleMaxParkNs='+str(maximum)]+release['parentJvmArguments']+[
        '-cp',':'.join(release['classPath']),'io.vectormatch.cluster.RetentionCapacityAeronPilotV3',str(root),'idle-window8-long-cuts','42000']


def expected_node(release,root,reg,node,maximum):
    return [release['java'],'-Dvectormatch.retention.idleMaxParkNs='+str(maximum),
        '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED',
        '-Xmx256m','-Daeron.cluster.appointed.leader.id=0','-cp',':'.join(release['nodeClassPath']),
        'io.vectormatch.cluster.RetentionNodeMainV3',str(node),str(root),'42000','2',release['profileId'],
        reg['lineage'],release['profileFingerprint'],release['codeFingerprint'],'bounded-maintenance-v1']


def inspect(arm_number,release_sha,controller_sha,expected_controller):
    require(platform.system()=='Linux' and platform.machine()=='x86_64' and platform.node()=='ed6c0673f5cb' and os.geteuid()==0,'Exact CPU/Linux/x86_64/root required')
    require(type(arm_number) is int and arm_number==1,'Exactly one manual long-cut arm required')
    for value in (release_sha,controller_sha):
        require(isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value),'Explicit actual root-frozen release/controller SHA required')
    require(set(expected_controller)=={'pid','startTicks','commandSha256'}
            and type(expected_controller['pid']) is int and expected_controller['pid']>1
            and type(expected_controller['startTicks']) is int and expected_controller['startTicks']>0
            and isinstance(expected_controller['commandSha256'],str) and len(expected_controller['commandSha256'])==64
            and all(c in '0123456789abcdef' for c in expected_controller['commandSha256']), 'Explicit actual launch identity required')
    maximum=MAXIMUM_PARK_NS
    expected_args=['/usr/bin/python3','-B',str(PREP/'cpu_long_cuts.py'),'--arm',str(arm_number),'--release-sha256',release_sha,'--start-new']
    require(argv_sha(expected_args)==expected_controller['commandSha256'], 'Actual controller argv SHA does not bind exact one long-cut arm')
    register=PREP/('arm-%d-execution-register.json'%arm_number)
    data=bounded(register,65536,True)
    if data is None:return {'state':'NOT_LAUNCHED_OR_NO_REGISTER','closedGate':False}
    entries=[json.loads(line) for line in data.splitlines() if line.strip()]
    require(1<=len(entries)<=8,'Bounded append-only registration rows required')
    require(entries[0]['state']=='INTENT_NO_PID_YET' and entries[0]['expectedArguments']==expected_args,'Original launch intent differs')
    if len(entries)<3:return {'state':'LAUNCH_IDENTITY_PENDING','closedGate':False,'registrationRows':len(entries),'neverResubmit':True}
    require(len(entries)==3 and entries[0]['arm']==arm_number and entries[0]['frozenReleaseSha256']==release_sha
            and entries[1]['state']=='SPAWNED_IDENTITY_PENDING' and entries[1]['arm']==arm_number, 'Exact three-row append-only launch format required')
    launch=entries[2]
    require(entries[1]['pid']==launch['pid'] and launch['arm']==arm_number, 'Pending/verified controller PID/arm differs')
    require(launch['expectedArguments']==expected_args and launch['observedCommandSha256']==argv_sha(expected_args) and launch['observedExecArgvMatches'] is True and launch['stableStartTicks'] is True and launch['frozenReleaseSha256']==release_sha,'Exact stable controller launch identity required')
    controller={'pid':launch['pid'],'startTicks':launch['startTicks'],'commandSha256':launch['observedCommandSha256'],'arguments':expected_args}
    require({k:controller[k] for k in expected_controller}==expected_controller,
            'Exact independently recorded actual controller launch identity differs')
    observed=identity_state(controller)
    if observed['observation'] not in ['PID_ABSENT','REGISTERED_IDENTITY_RUNNING']:
        return {'state':'CONTROLLER_IDENTITY_NOT_STRICTLY_ABSENT','closedGate':False,'controller':observed,'neverSignalOrResubmit':True}
    if observed['originalIdentityRunning']:
        return {'state':'CONTROLLER_RUNNING','closedGate':False,'controller':observed,'nativeOrRawEvidenceRead':False,'note':'May be loading, cleaning, validating or archiving; no completion/CSV/native reads or full hashing while active.'}
    # Only after the registered controller no longer runs inspect bounded control-plane receipts.
    release_bytes=bounded(PREP/'release/release.json',2*1024**2)
    require(hashlib.sha256(release_bytes).hexdigest()==release_sha,'Actual ready release bytes differ')
    release=json.loads(release_bytes)
    require(release['releaseReady'] is True and release['controllerSha256']==controller_sha
            and release['sourceCommit']==SOURCE_COMMIT
            and release['codeFingerprint']==CODE_SHA and release['profileFingerprint']==PROFILE_SHA,
            'Actual ready source/code/controller differs')
    require(hashlib.sha256(bounded(PREP/'cpu_long_cuts.py',1024**2)).hexdigest()==controller_sha,
            'Actual frozen controller source differs')
    job=PREP/('arm-%d'%arm_number)
    blocked=js(job/'BENCHMARK_BLOCKED.json',optional=True)
    completion=js(job/'completion.json',optional=True)
    stop=js(job/'python-owned-stop.json',optional=True)
    if blocked is not None:return {'state':'BLOCKED_STOP_UNCONFIRMED','closedGate':False,'controller':observed,'blockedReason':blocked.get('reason'),'neverResubmit':True}
    if completion is None or stop is None:return {'state':'CONTROLLER_EXITED_CLOSE_RECEIPTS_INCOMPLETE','closedGate':False,'controller':observed,'completionPresent':completion is not None,'stopReceiptPresent':stop is not None,'neverResubmit':True}
    require(completion['arm']==arm_number and completion['maximumParkNs']==maximum and completion['frozenReleaseSha256']==release_sha,'Completion scope mismatch')
    if not completion.get('allOwnedStopped') or not stop.get('allOwnedStopped') or stop.get('errors') or stop.get('forcedKill') is not False or stop.get('numericPidSignalFallback') is not False:
        return {'state':'CONTROLLER_EXITED_OWNED_STOP_NOT_CLOSED','closedGate':False,'controller':observed,'neverResubmit':True}
    parent=js(job/'identity-observation-000.json',65536)
    require(parent['role']=='pilot-parent' and parent['origin']=='independent-direct-child-proc','Java parent launch identity origin differs')
    identities=[dict(role='pilot-parent',identity=parent['kernelIdentity'])]
    require(len(stop['reports'])==3 and all(r['stopped'] is True for r in stop['reports']),
            'Exactly three successful raw node stop reports required')
    for record in stop['reports']:identities.append({'role':record['role'],'identity':record['record']})
    unique={}
    for entry in identities:
        old=unique.get(entry['role']);require(old is None or old==entry['identity'],'Conflicting registered role identity');unique[entry['role']]=entry['identity']
    roles={'pilot-parent'}|{'window-8-node-%d'%n for n in range(3)}
    require(set(unique)==roles,'Exact Java parent plus three node identities required')
    require(len({r['pid'] for r in unique.values()})==4,'Four distinct registered owned JVM PIDs required')
    root=job/'idle-arm';reg=js(root/'registration.json')
    require(reg['ports']==42000 and reg['readWindow']==8 and reg['appointedLeader']==0 and reg['sync']==2
            and reg['profileSha256']==release['profileFingerprint'] and reg['codeSha256']==release['codeFingerprint']
            and reg['retentionIdleSelection']['maximumParkNs']==maximum
            and reg['arrivals']==33792 and reg['rate']==500 and reg['batchCap']==4 and reg['archiveChunkBytes']==6144
            and reg['eventFetchCount']==16 and reg['commonReadWindowEnvelope'] is True and reg['commonChunkEnvelope'] is False
            and reg['workloadPreset']=='long-cuts-33792-v1' and reg['expectedFullCommandCuts']==11
            and reg['expectedTrailingCommands']==3 and reg['equivalentFullLoadCutNumbers']==list(range(2,12)),'Exact long arm registration differs')
    require(unique['pilot-parent']['arguments']==expected_parent(release,root,maximum),'Registered actual Java parent argv differs')
    handle=js(job/'parent-launch-handle.json',65536)
    require(handle['pid']==unique['pilot-parent']['pid'] and handle['expectedArguments']==expected_parent(release,root,maximum)
            and handle['expectedCommandSha256']==unique['pilot-parent']['commandSha256'],'Independent parent launch/kernel binding differs')
    for n in range(3):
        claimed=js(root/('node-%d-identity.json'%n),65536);record=unique['window-8-node-%d'%n]
        require(record['arguments']==expected_node(release,root,reg,n,maximum)
                and claimed['pid']==record['pid'] and claimed['linuxStartTicks']==record['startTicks']
                and claimed['linuxCommandSha256']==record['commandSha256']
                and [claimed['command']]+claimed['arguments']==record['arguments'], 'Node JSON/full argv/kernel stop record differs')
    ownership=[dict(role=role,**identity_state(value)) for role,value in sorted(unique.items())]
    foreign,proc_count=live_jvm_pg()
    if any(x['observation']!='PID_ABSENT' for x in ownership) or foreign:
        return {'state':'CONTROLLER_EXITED_LIVE_JVM_OR_PG','closedGate':False,'controller':observed,'ownership':ownership,'liveJavaPg':foreign,'neverSignalOrResubmit':True}
    if completion.get('passed') is not True or completion.get('errors'):
        return {'state':'CLOSED_FAILED_OUTCOME','closedGate':False,'safeForReadOnlyFailureCollection':True,'controller':observed,'ownership':ownership,'errors':completion.get('errors'),'allOwnedStoppedAtObservation':True}
    before=js(job/'before.json',4*1024**2);after=js(job/'after-clean-stop.json',4*1024**2)
    require(before['controllerSha256']==controller_sha and before['baseSha256']=='8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87',
            'Actual before/preflight frozen controller/ownership source differs')
    require(before['arm']==1 and before['singleManualArmOnly'] is True and before['noJavaStarted'] is True,'One manual arm default-preflight receipt differs')
    result=completion['result'];require(result['passed'] is True and len(result['arms'])==1,'Full successful single-arm controller result required')
    arm=result['arms'][0];summary=arm['functional']['actualSourceSummary'];logs=arm['nodeLogClassifications']
    require(arm['maximumParkNs']==maximum and arm['readWindow']==8 and arm['functional']['passed'] is True
            and summary['confirmedAcceptedUniqueOrders']==33792 and summary['notSent']==0 and summary['unknownObserved']==0 and summary['unknownFinal']==0
            and summary['scheduledArrivals']==33792 and summary['releasedArrivals']==33792 and summary['completedLogicalReplies']==33792
            and summary['ratePerSecond']==500 and summary['batchCap']==4 and summary['archiveChunkBytes']==6144 and summary['readWindow']==8
            and summary['serverRejected']==0 and summary['duplicateOrOutOfRangeAcceptedOrderIds']==0 and summary['maintenanceCycles']==12
            and summary['schedulerTimingValid'] is True and summary['schedulerLatenessOver20ms']==0 and summary['arrivalClockPausedForMaintenance'] is False
            and len(logs)==3 and {v['node'] for v in logs}=={0,1,2}
            and arm['retainedPostCheckpointEosWarningPairs']==sum(v['warningPairCount'] for v in logs)<=2,
            'Controller full success/warning receipt differs; no raw audit performed here')
    require(all(v['afterSigtermWallTimeProven'] is False and v['allLogLinesClassifiedAndRetained'] is True for v in logs),
            'Warning qualification/log closure metadata differs')
    protected=before['protectedOriginal']
    require(protected==after['protectedOriginal'] and protected['passed'] is True and protected['manifestSha256']==PROTECTED_SHA and sum(v['files'] for v in protected['nativeTrees'])==57 and protected['postgres']['files']==989,'Frozen controller protected57/PG989 receipt mismatch')
    archive=after['archive'];require(archive['sameHostReadback']['passed'] is True and archive['requiresIndependentCollectorStreamReadback'] is True,'Controller archive closure receipt incomplete')
    advertised=archive['archive'];expected_archive=job/'pilot-after-clean-stop.tar.gz';require(advertised['path']==str(expected_archive),'Archive path differs')
    st=expected_archive.lstat();require(stat.S_ISREG(st.st_mode) and not expected_archive.is_symlink() and st.st_size==advertised['bytes']<=256*1024**2,'Stopped archive metadata differs')
    require(identity_state(controller)['observation']=='PID_ABSENT','Controller observation changed')
    require(all(identity_state(value)['observation']=='PID_ABSENT' for value in unique.values()),'Owned JVM absence changed during metadata inspection')
    return {'state':'CLOSED_PASS_CONTROL_PLANE','closedGate':True,'safeForIndependentClosedCollection':True,'controller':observed,'controllerExitCodeIndependentlyObserved':False,'javaParentNormalExitBasis':'Frozen controller passed only after parent.returncode==0 and parent.wait; not a separately observed controller exit code.','ownership':ownership,'processesObserved':proc_count,'allOwnedStoppedAtObservation':True,'allFourOwnedJvmsStrictlyPidAbsent':True,'protectedNative57Pg989ReceiptsExact':True,'protectedFinalValues':protected,'archiveMetadataOnly':advertised,'archiveFullHashReadHere':False,'fullNativeOrRawEvidenceRead':False,'independentRawAndFullArchiveCollectionStillRequired':True,'nextArmExists':False,'benchmarkOrBusinessCommandStartedByProbe':False,'arm':arm_number,'maximumParkNs':maximum,'frozenReleaseSha256':release_sha,'controllerSha256':controller_sha,'controllerOriginalIdentity':controller,'controllerFullSuccessReceiptPassed':True,'schedulerTimingValidReported':summary['schedulerTimingValid'],'retainedPostCheckpointEosWarningPairs':arm['retainedPostCheckpointEosWarningPairs'],'afterSigtermWallTimeProven':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--arm',type=int,choices=(1,),required=True);p.add_argument('--release-sha256',required=True);p.add_argument('--controller-sha256',required=True);p.add_argument('--controller-pid',type=int,required=True);p.add_argument('--controller-start-ticks',type=int,required=True);p.add_argument('--controller-argv-sha256',required=True);args=p.parse_args()
    try:
        result=inspect(args.arm,args.release_sha256,args.controller_sha256,{'pid':args.controller_pid,'startTicks':args.controller_start_ticks,'commandSha256':args.controller_argv_sha256})
        result.update(observedAtUnixNs=time.time_ns(),controlPlaneInputs=FILES,readOnly=True,networkOrSignalsOrWritesPerformed=False)
        print(json.dumps(result,sort_keys=True));raise SystemExit(0)
    except Exception as error:
        print(json.dumps({'state':'INSPECTION_INDETERMINATE','closedGate':False,'errorType':type(error).__name__,'error':str(error)[:1024],'controlPlaneInputs':FILES,'readOnly':True,'neverSignalOrResubmit':True},sort_keys=True));raise SystemExit(2)
