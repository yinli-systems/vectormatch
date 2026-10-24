"""Read-only bounded control-plane probe. No imports of project code, signals, writes, launches or native hashing.
Send this source on SSH stdin to: python3 -B - --round 1 --release-sha256 <frozen SHA>.
"""
import argparse
import hashlib
import json
import os
import pathlib
import platform
import stat
import time

PREP=pathlib.Path('/opt/vectormatch-cpu/preparation/window-cloud-abab-r1')
RELEASE_SHA='2a31b6f0d6b08c6863aef422a2bafa12d67a6ad11b651cbd2377b7b863943bed'
CONTROLLER_SHA='be513acb641e7fd836b05720ee3a274ee815f7d69335008aa4ff38f898c4ba31'
PROTECTED_SHA='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753'
MAX_PROC=4096
FILES={}


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


def inspect(round_number,release_sha,prior_sha):
    require(platform.system()=='Linux' and platform.machine()=='x86_64' and platform.node()=='ed6c0673f5cb' and os.geteuid()==0,'Exact CPU/Linux/x86_64/root required')
    require(round_number in (1,2) and release_sha==RELEASE_SHA,'Exact frozen round/release required')
    require((round_number==1 and prior_sha is None) or (round_number==2 and isinstance(prior_sha,str) and len(prior_sha)==64),'Round2 requires exact prior gate SHA')
    expected_args=['/usr/bin/python3','-B',str(PREP/'window_cloud_abab.py'),'--round',str(round_number),'--release-sha256',release_sha,'--start-new']
    if prior_sha:expected_args+=['--prior-collection-sha256',prior_sha]
    register=PREP/('round-%d-execution-register.json'%round_number)
    data=bounded(register,65536,True)
    if data is None:return {'state':'NOT_LAUNCHED_OR_NO_REGISTER','closedGate':False}
    entries=[json.loads(line) for line in data.splitlines() if line.strip()]
    require(1<=len(entries)<=8,'Bounded append-only registration rows required')
    require(entries[0]['state']=='INTENT_NO_PID_YET' and entries[0]['expectedArguments']==expected_args,'Original launch intent differs')
    if len(entries)<3:return {'state':'LAUNCH_IDENTITY_PENDING','closedGate':False,'registrationRows':len(entries),'neverResubmit':True}
    launch=entries[-1]
    require(launch['expectedArguments']==expected_args and launch['observedCommandSha256']==argv_sha(expected_args) and launch['observedExecArgvMatches'] is True and launch['stableStartTicks'] is True and launch['frozenReleaseSha256']==release_sha,'Exact stable controller launch identity required')
    controller={'pid':launch['pid'],'startTicks':launch['startTicks'],'commandSha256':launch['observedCommandSha256'],'arguments':expected_args}
    observed=identity_state(controller)
    if observed['originalIdentityRunning']:
        return {'state':'CONTROLLER_RUNNING','closedGate':False,'controller':observed,'nativeOrRawEvidenceRead':False,'note':'May be loading, cleaning, validating or archiving; no completion/CSV/native reads or full hashing while active.'}
    # Only after the registered controller no longer runs inspect bounded control-plane receipts.
    job=PREP/('round-%d'%round_number)
    blocked=js(job/'BENCHMARK_BLOCKED.json',optional=True)
    completion=js(job/'completion.json',optional=True)
    stop=js(job/'python-owned-stop.json',optional=True)
    if blocked is not None:return {'state':'BLOCKED_STOP_UNCONFIRMED','closedGate':False,'controller':observed,'blockedReason':blocked.get('reason'),'neverResubmit':True}
    if completion is None or stop is None:return {'state':'CONTROLLER_EXITED_CLOSE_RECEIPTS_INCOMPLETE','closedGate':False,'controller':observed,'completionPresent':completion is not None,'stopReceiptPresent':stop is not None,'neverResubmit':True}
    require(completion['round']==round_number and completion['frozenReleaseSha256']==release_sha,'Completion scope mismatch')
    if not completion.get('allOwnedStopped') or not stop.get('allOwnedStopped') or stop.get('errors') or stop.get('forcedKill') is not False or stop.get('numericPidSignalFallback') is not False:
        return {'state':'CONTROLLER_EXITED_OWNED_STOP_NOT_CLOSED','closedGate':False,'controller':observed,'neverResubmit':True}
    parent=js(job/'identity-observation-000.json',65536)
    require(parent['role']=='pilot-parent' and parent['origin']=='independent-direct-child-proc','Java parent launch identity origin differs')
    identities=[dict(role='pilot-parent',identity=parent['kernelIdentity'])]
    for record in stop['reports']:identities.append({'role':record['role'],'identity':record['record']})
    unique={}
    for entry in identities:
        old=unique.get(entry['role']);require(old is None or old==entry['identity'],'Conflicting registered role identity');unique[entry['role']]=entry['identity']
    roles={'pilot-parent'}|{'window-%d-node-%d'%(w,n) for w in (1,8) for n in range(3)}
    require(set(unique)==roles,'Exact Java parent plus six node identities required')
    ownership=[dict(role=role,**identity_state(value)) for role,value in sorted(unique.items())]
    foreign,proc_count=live_jvm_pg()
    if any(x['originalIdentityRunning'] for x in ownership) or foreign:
        return {'state':'CONTROLLER_EXITED_LIVE_JVM_OR_PG','closedGate':False,'controller':observed,'ownership':ownership,'liveJavaPg':foreign,'neverSignalOrResubmit':True}
    if completion.get('passed') is not True or completion.get('errors'):
        return {'state':'CLOSED_FAILED_OUTCOME','closedGate':False,'safeForReadOnlyFailureCollection':True,'controller':observed,'ownership':ownership,'errors':completion.get('errors'),'allOwnedStoppedAtObservation':True}
    before=js(job/'before.json',4*1024**2);after=js(job/'after-clean-stop.json',4*1024**2)
    protected=before['protectedOriginal']
    require(protected==after['protectedOriginal'] and protected['passed'] is True and protected['manifestSha256']==PROTECTED_SHA and sum(v['files'] for v in protected['nativeTrees'])==57 and protected['postgres']['files']==989,'Frozen controller protected57/PG989 receipt mismatch')
    archive=after['archive'];require(archive['sameHostReadback']['passed'] is True and archive['requiresIndependentCollectorStreamReadback'] is True,'Controller archive closure receipt incomplete')
    advertised=archive['archive'];expected_archive=job/'pilot-after-clean-stop.tar.gz';require(advertised['path']==str(expected_archive),'Archive path differs')
    st=expected_archive.lstat();require(stat.S_ISREG(st.st_mode) and not expected_archive.is_symlink() and st.st_size==advertised['bytes']<=256*1024**2,'Stopped archive metadata differs')
    require(identity_state(controller)['originalIdentityRunning'] is False,'Controller observation changed')
    return {'state':'CLOSED_PASS_CONTROL_PLANE','closedGate':True,'safeForIndependentClosedCollection':True,'controller':observed,'controllerExitCodeIndependentlyObserved':False,'javaParentNormalExitBasis':'Frozen controller passed only after parent.returncode==0 and parent.wait; not a separately observed controller exit code.','ownership':ownership,'processesObserved':proc_count,'allOwnedStoppedAtObservation':True,'protectedNative57Pg989ReceiptsExact':True,'archiveMetadataOnly':advertised,'archiveFullHashReadHere':False,'fullNativeOrRawEvidenceRead':False,'independentRawAndFullArchiveCollectionStillRequired':True,'round2PromotionAuthorizedByThisProbe':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--round',type=int,choices=(1,2),required=True);p.add_argument('--release-sha256',required=True);p.add_argument('--prior-collection-sha256');args=p.parse_args()
    try:
        result=inspect(args.round,args.release_sha256,args.prior_collection_sha256)
        result.update(observedAtUnixNs=time.time_ns(),controlPlaneInputs=FILES,readOnly=True,networkOrSignalsOrWritesPerformed=False)
        print(json.dumps(result,sort_keys=True));raise SystemExit(0)
    except Exception as error:
        print(json.dumps({'state':'INSPECTION_INDETERMINATE','closedGate':False,'errorType':type(error).__name__,'error':str(error)[:1024],'controlPlaneInputs':FILES,'readOnly':True,'neverSignalOrResubmit':True},sort_keys=True));raise SystemExit(2)
