"""Read-only bounded control-plane probe. No imports of project code, signals, writes, launches or native hashing. Arm1 only.
Send this source on SSH stdin to: python3 -B - --arm 1 --release-sha256 <frozen SHA>.
"""
import argparse
import hashlib
import json
import os
import pathlib
import platform
import stat
import time

PREP=pathlib.Path('/opt/vectormatch-cpu/preparation/cpu-idle-cloud-abab-r1')
RELEASE_SHA='c2df0427bea0cdd8575ee3130adf4ff4aa43c65fca0a5458ed0c7c8c1eea4676'
CONTROLLER_SHA='07016602e61a9d415fdf968ada64c1ad6d40172926fd64ef44ab7c9dd124f98c'
PROTECTED_SHA='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753'
MAX_PROC=4096
FILES={}
EXPECTED_CONTROLLER={'pid':63935,'startTicks':3861055,
    'commandSha256':'2c25798d553d9ba7f4239103e6751002cd4b21a72d9856d435c16d66ed7493b2'}


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


def expected_parent(release,root):
    return [release['java'],'-Dvectormatch.retention.idleMaxParkNs=1000000']+release['parentJvmArguments']+[
        '-cp',':'.join(release['classPath']),'io.vectormatch.cluster.RetentionCapacityAeronPilotV3',str(root),'idle-window8','42000']


def expected_node(release,root,reg,node):
    return [release['java'],'-Dvectormatch.retention.idleMaxParkNs=1000000',
        '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED',
        '-Xmx256m','-Daeron.cluster.appointed.leader.id=0','-cp',':'.join(release['nodeClassPath']),
        'io.vectormatch.cluster.RetentionNodeMainV3',str(node),str(root),'42000','2',release['profileId'],
        reg['lineage'],release['profileFingerprint'],release['codeFingerprint'],'bounded-maintenance-v1']


def inspect(arm_number,release_sha,prior_sha):
    require(platform.system()=='Linux' and platform.machine()=='x86_64' and platform.node()=='ed6c0673f5cb' and os.geteuid()==0,'Exact CPU/Linux/x86_64/root required')
    require(type(arm_number) is int and arm_number==1 and release_sha==RELEASE_SHA,'Exact frozen round/release required')
    require(prior_sha is None, 'This frozen probe is arm1 only, without any prior gate')
    expected_args=['/usr/bin/python3','-B',str(PREP/'cpu_idle_abab.py'),'--arm','1','--release-sha256',release_sha,'--start-new']
    if prior_sha:expected_args+=['--prior-collection-sha256',prior_sha]
    register=PREP/('arm-%d-execution-register.json'%arm_number)
    data=bounded(register,65536,True)
    if data is None:return {'state':'NOT_LAUNCHED_OR_NO_REGISTER','closedGate':False}
    entries=[json.loads(line) for line in data.splitlines() if line.strip()]
    require(1<=len(entries)<=8,'Bounded append-only registration rows required')
    require(entries[0]['state']=='INTENT_NO_PID_YET' and entries[0]['expectedArguments']==expected_args,'Original launch intent differs')
    if len(entries)<3:return {'state':'LAUNCH_IDENTITY_PENDING','closedGate':False,'registrationRows':len(entries),'neverResubmit':True}
    require(len(entries)==3 and entries[0]['arm']==1 and entries[0]['frozenReleaseSha256']==RELEASE_SHA
            and entries[1]['state']=='SPAWNED_IDENTITY_PENDING' and entries[1]['arm']==1, 'Exact three-row append-only launch format required')
    launch=entries[2]
    require(entries[1]['pid']==launch['pid'] and launch['arm']==1, 'Pending/verified controller PID/arm differs')
    require(launch['expectedArguments']==expected_args and launch['observedCommandSha256']==argv_sha(expected_args) and launch['observedExecArgvMatches'] is True and launch['stableStartTicks'] is True and launch['frozenReleaseSha256']==release_sha,'Exact stable controller launch identity required')
    controller={'pid':launch['pid'],'startTicks':launch['startTicks'],'commandSha256':launch['observedCommandSha256'],'arguments':expected_args}
    require({k:controller[k] for k in EXPECTED_CONTROLLER}==EXPECTED_CONTROLLER,
            'Exact independently recorded actual arm1 launch identity differs')
    observed=identity_state(controller)
    if observed['observation'] not in ['PID_ABSENT','REGISTERED_IDENTITY_RUNNING']:
        return {'state':'CONTROLLER_IDENTITY_NOT_STRICTLY_ABSENT','closedGate':False,'controller':observed,'neverSignalOrResubmit':True}
    if observed['originalIdentityRunning']:
        return {'state':'CONTROLLER_RUNNING','closedGate':False,'controller':observed,'nativeOrRawEvidenceRead':False,'note':'May be loading, cleaning, validating or archiving; no completion/CSV/native reads or full hashing while active.'}
    # Only after the registered controller no longer runs inspect bounded control-plane receipts.
    release_bytes=bounded(PREP/'release/release.json',2*1024**2)
    require(hashlib.sha256(release_bytes).hexdigest()==RELEASE_SHA,'Actual ready release bytes differ')
    release=json.loads(release_bytes)
    require(release['releaseReady'] is True and release['controllerSha256']==CONTROLLER_SHA
            and release['sourceCommit']=='7aa3e98ccc77c4be89f9f4b98c98d688c18e5d23'
            and release['codeFingerprint']=='f78025f91f9e43ad634840b400ab04ed4ae422597c35800984e434dbd1844c8f',
            'Actual ready source/code/controller differs')
    require(hashlib.sha256(bounded(PREP/'cpu_idle_abab.py',1024**2)).hexdigest()==CONTROLLER_SHA,
            'Actual frozen controller source differs')
    job=PREP/('arm-%d'%arm_number)
    blocked=js(job/'BENCHMARK_BLOCKED.json',optional=True)
    completion=js(job/'completion.json',optional=True)
    stop=js(job/'python-owned-stop.json',optional=True)
    if blocked is not None:return {'state':'BLOCKED_STOP_UNCONFIRMED','closedGate':False,'controller':observed,'blockedReason':blocked.get('reason'),'neverResubmit':True}
    if completion is None or stop is None:return {'state':'CONTROLLER_EXITED_CLOSE_RECEIPTS_INCOMPLETE','closedGate':False,'controller':observed,'completionPresent':completion is not None,'stopReceiptPresent':stop is not None,'neverResubmit':True}
    require(completion['arm']==1 and completion['maximumParkNs']==1000000 and completion['frozenReleaseSha256']==release_sha,'Completion scope mismatch')
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
            and reg['retentionIdleSelection']['maximumParkNs']==1000000,'Exact arm registration differs')
    require(unique['pilot-parent']['arguments']==expected_parent(release,root),'Registered actual Java parent argv differs')
    handle=js(job/'parent-launch-handle.json',65536)
    require(handle['pid']==unique['pilot-parent']['pid'] and handle['expectedArguments']==expected_parent(release,root)
            and handle['expectedCommandSha256']==unique['pilot-parent']['commandSha256'],'Independent parent launch/kernel binding differs')
    for n in range(3):
        claimed=js(root/('node-%d-identity.json'%n),65536);record=unique['window-8-node-%d'%n]
        require(record['arguments']==expected_node(release,root,reg,n)
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
    require(before['controllerSha256']==CONTROLLER_SHA and before['baseSha256']=='8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87',
            'Actual before/preflight frozen controller/ownership source differs')
    result=completion['result'];require(result['passed'] is True and len(result['arms'])==1,'Full successful single-arm controller result required')
    arm=result['arms'][0];summary=arm['functional']['actualSourceSummary'];logs=arm['nodeLogClassifications']
    require(arm['maximumParkNs']==1000000 and arm['readWindow']==8 and arm['functional']['passed'] is True
            and summary['confirmedAcceptedUniqueOrders']==6400 and summary['notSent']==0 and summary['unknownFinal']==0
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
    return {'state':'CLOSED_PASS_CONTROL_PLANE','closedGate':True,'safeForIndependentClosedCollection':True,'controller':observed,'controllerExitCodeIndependentlyObserved':False,'javaParentNormalExitBasis':'Frozen controller passed only after parent.returncode==0 and parent.wait; not a separately observed controller exit code.','ownership':ownership,'processesObserved':proc_count,'allOwnedStoppedAtObservation':True,'allFourOwnedJvmsStrictlyPidAbsent':True,'protectedNative57Pg989ReceiptsExact':True,'protectedFinalValues':protected,'archiveMetadataOnly':advertised,'archiveFullHashReadHere':False,'fullNativeOrRawEvidenceRead':False,'independentRawAndFullArchiveCollectionStillRequired':True,'nextArmPromotionAuthorizedByThisProbe':False,'arm':1,'maximumParkNs':1000000,'controllerOriginalIdentity':controller,'controllerFullSuccessReceiptPassed':True,'schedulerTimingValidReported':summary['schedulerTimingValid'],'retainedPostCheckpointEosWarningPairs':arm['retainedPostCheckpointEosWarningPairs'],'afterSigtermWallTimeProven':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--arm',type=int,choices=(1,),required=True);p.add_argument('--release-sha256',required=True);p.add_argument('--prior-collection-sha256');args=p.parse_args()
    try:
        result=inspect(args.arm,args.release_sha256,args.prior_collection_sha256)
        result.update(observedAtUnixNs=time.time_ns(),controlPlaneInputs=FILES,readOnly=True,networkOrSignalsOrWritesPerformed=False)
        print(json.dumps(result,sort_keys=True));raise SystemExit(0)
    except Exception as error:
        print(json.dumps({'state':'INSPECTION_INDETERMINATE','closedGate':False,'errorType':type(error).__name__,'error':str(error)[:1024],'controlPlaneInputs':FILES,'readOnly':True,'neverSignalOrResubmit':True},sort_keys=True));raise SystemExit(2)
