"""LOCAL read-only original logs/source/JAR investigation. No Java/subprocess/network."""
import datetime
import hashlib
import json
from pathlib import Path
import struct
import zipfile
from shutdown_warning import classify

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
WORK = ROOT / 'runtime/cloud/cpu-20261024/latency-idle-v3-worktree'
VALIDATION = WORK / 'runtime/latency-idle-local-validation'
NATIVE = VALIDATION / 'native-r2'
FROZEN_PREP = ROOT / 'runtime/cloud/cpu-20261024/cpu-idle-cloud-preparation-r1'
INPUTS = {}


def read(path, cap=4*1024**2):
    path = Path(path)
    assert path.is_file() and not path.is_symlink() and path.stat().st_size <= cap
    data = path.read_bytes()
    INPUTS[str(path)] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    return data


def js(path):return json.loads(read(path))


class Reader:
    def __init__(self, data):self.data=data;self.pos=0
    def take(self, n):
        out=self.data[self.pos:self.pos+n];self.pos+=n;assert len(out)==n;return out
    def u1(self):return self.take(1)[0]
    def u2(self):return struct.unpack('>H',self.take(2))[0]
    def u4(self):return struct.unpack('>I',self.take(4))[0]


def class_methods(data):
    """Read class-file structures only. No class loading or Java execution."""
    r=Reader(data);assert r.u4()==0xcafebabe;r.u2();r.u2();count=r.u2();cp=[None]*count;i=1
    while i<count:
        tag=r.u1()
        if tag==1:cp[i]=('utf',r.take(r.u2()).decode('utf8'))
        elif tag in [7,8,16,19,20]:cp[i]=(tag,r.u2())
        elif tag in [9,10,11,12,17,18]:cp[i]=(tag,r.u2(),r.u2())
        elif tag in [3,4]:cp[i]=(tag,r.take(4).hex())
        elif tag in [5,6]:cp[i]=(tag,r.take(8).hex());i+=1
        elif tag==15:cp[i]=(tag,r.u1(),r.u2())
        else:raise ValueError('Unknown class constant')
        i+=1
    def value(index):
        item=cp[index]
        if item[0]=='utf':return item[1]
        if item[0] in [7,8,16,19,20]:return value(item[1])
        if item[0] in [9,10,11]:return value(item[1])+'.'+value(item[2])
        if item[0]==12:return value(item[1])+value(item[2])
        return repr(item)
    def attrs():
        out={}
        for _ in range(r.u2()):name=value(r.u2());out[name]=r.take(r.u4())
        return out
    r.u2();typ=value(r.u2());parent=value(r.u2())
    for _ in range(r.u2()):r.u2()
    for _ in range(r.u2()):r.u2();r.u2();r.u2();attrs()
    methods={}
    for _ in range(r.u2()):
        r.u2();name=value(r.u2());desc=value(r.u2());attributes=attrs()
        if 'Code' in attributes:
            code=Reader(attributes['Code']);code.u2();code.u2();raw=code.take(code.u4())
            methods[name+desc]=raw.hex()
    return {'class':typ,'superClass':parent,'methods':methods,
            'constantPool':{str(n):value(n) for n in range(1,len(cp)) if cp[n] is not None}}


def investigate():
    frozen = js(FROZEN_PREP / 'LOCAL_PREPARATION_FROZEN.json')
    for name,row in frozen['sourceFiles'].items():
        assert hashlib.sha256(read(FROZEN_PREP/name)).hexdigest()==row['sha256']
    pins_path=VALIDATION/'idle-supplier-fix-r1/PRIMARY_SOURCE_PINS.json';pins=js(pins_path)
    source_row=next(row for row in pins['files'] if row['path'].endswith('/ConsensusModuleAgent.java'))
    source_path=pins_path.parent/source_row['path'];source=read(source_path)
    assert hashlib.sha256(source).hexdigest()==source_row['sha256']
    source_lines=source.decode().splitlines()
    anchors={name:[{'line1Based':n,'text':line.strip()} for n,line in enumerate(source_lines,1) if needle in line]
        for name,needle in {'recordingStop':'RecordingSignal.STOP == signal && recordingId == logRecordingId',
            'activeNoElection':'null == election && ConsensusModule.State.ACTIVE == state',
            'endOfStreamCheck':'logAdapter.isLogEndOfStreamAt(position)',
            'eosElection':'enterElection(isEos, "log recording stopped: eos=" + isEos)',
            'event':'ctx.countedErrorHandler().onError(new ClusterEvent(reason))'}.items()}
    assert all(anchors.values())
    app_sources={}
    for name in ['RetentionNodeMainV3.java','RetentionCapacityAeronPilotV3.java','RetentionClusteredServiceV3.java']:
        path=WORK/'cluster/src/main/java/io/vectormatch/cluster'/name;data=read(path)
        app_sources[name]={'path':str(path),'sha256':hashlib.sha256(data).hexdigest()}
    node_source=(WORK/'cluster/src/main/java/io/vectormatch/cluster/RetentionNodeMainV3.java').read_text()
    pilot_source=(WORK/'cluster/src/main/java/io/vectormatch/cluster/RetentionCapacityAeronPilotV3.java').read_text()
    assert 'System.err.println("VECTOR_V3_ERROR node=" + node); e.printStackTrace(System.err);' in node_source
    assert 'for(int member=0;member<3;member++)' in pilot_source and 'for(Owned record:owned)' in pilot_source
    assert 'child.destroy();' in pilot_source and 'child.waitFor(50,TimeUnit.MILLISECONDS)' in pilot_source
    jar=VALIDATION/'units-r4/artifact-state/distribution/lib/aeron-all-1.53.3.jar';jar_bytes=read(jar,32*1024**2)
    assert hashlib.sha256(jar_bytes).hexdigest()=='4c6c8a5014a2b67424051170392a005daa9a998ac963302d2819d0f3db749ef2'
    classes={}
    with zipfile.ZipFile(jar) as archive:
        for name in ['io/aeron/cluster/client/ClusterEvent.class','io/aeron/exceptions/AeronEvent.class','io/aeron/cluster/LogAdapter.class']:
            data=archive.read(name);parsed=class_methods(data)
            parsed['sha256']=hashlib.sha256(data).hexdigest();parsed['bytes']=len(data)
            parsed['methods']={k:v for k,v in parsed['methods'].items() if k.startswith(('<init>','fillInStackTrace','isLogEndOfStreamAt'))}
            classes[name]=parsed
    cluster=classes['io/aeron/cluster/client/ClusterEvent.class']
    assert cluster['superClass']=='io/aeron/exceptions/AeronEvent'
    assert cluster['methods']['<init>(Ljava/lang/String;)V']=='2a2bb20001b70007b1'
    assert cluster['constantPool']['1']=='io/aeron/exceptions/AeronException$Category.WARNLio/aeron/exceptions/AeronException$Category;'
    assert cluster['constantPool']['7']=='io/aeron/exceptions/AeronEvent.<init>(Ljava/lang/String;Lio/aeron/exceptions/AeronException$Category;)V'
    # Exact bytecode is retained rather than guessing a full decompiler.
    arms=[]
    failure=js(NATIVE/'native-failure.json')
    assert failure['type']=='AssertionError' and 'Node checkpoint/error log differs' in failure['traceback']
    for maximum in [1000000,100000]:
        arm=NATIVE/'arms'/('park-'+str(maximum));reg=js(arm/'registration.json');final=js(arm/'final-position.json')
        cfg=js(arm/'load/configuration.json');summary=js(arm/'load/load-result.json')
        completion=js(arm/'completion.json');stop=js(arm/'owned-stop.json');functional=js(arm/'functional-result.json')
        reference=js(arm/'physical-reference-reconciliation.json');exit_receipt=js(NATIVE/('arm-%d-process'%maximum)/'exit.json')
        assert exit_receipt['returnCode']==0 and completion['passed'] is True and completion['allOwnedStopped'] is True
        assert functional['passed'] is True and functional['allThreeSnapshotLogsMatched'] is True and reference['passed'] is True
        assert summary['confirmedAcceptedUniqueOrders']==6400 and summary['maintenanceCycles']==3
        assert stop['allOwnedStopped'] is True and stop['forcedKill'] is False and len(stop['reports'])==3
        assert summary['notSent']==summary['unknownFinal']==0
        logs=[];node_pids=[]
        for node in range(3):
            identity=js(arm/('node-%d-identity.json'%node));node_pids.append(identity['pid'])
            idle=js(arm/('node-%d/idle-observations/idle-000.actual.json'%node))
            logs.append(classify(read(arm/('node-%d.log'%node)),node=node,pid=identity['pid'],profile=reg['profileSha256'],
                lineage=reg['lineage'],code=reg['codeSha256'],final_hash=final['combinedSha256'],idle_actual=idle))
        assert [r['pid'] for r in stop['reports']]==node_pids
        arms.append({'maximumParkNs':maximum,'codeFingerprint':cfg['actualCodeSha256'],'logs':logs,
            'recordedParentExitCode':exit_receipt['returnCode'],'recordedOwnedStop':True,
            'recordedAcceptedOrders':summary['confirmedAcceptedUniqueOrders'],'recordedMaintenanceCycles':summary['maintenanceCycles'],
            'recordedSchedulerTimingValid':summary['schedulerTimingValid'],
            'rawFunctionalFullClosureIndependentlyRecomputedHere':False})
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==row['sha256'] for path,row in INPUTS.items())
    return {'schemaVersion':1,'createdAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status':'INDEPENDENT_LOCAL_WARNING_TAXONOMY_REVIEW_NOT_A_NATIVE_PASS_OVERRIDE',
        'sourceCommit':'7aa3e98ccc77c4be89f9f4b98c98d688c18e5d23','pinnedAeronVersion':'1.53.3',
        'primarySource':{'path':str(source_path),'url':source_row['url'],'sha256':source_row['sha256'],'anchors':anchors},
        'applicationSources':app_sources,'actualJarBytecode':classes,'arms':arms,
        'originalNativeFailureSha256':INPUTS[str(NATIVE/'native-failure.json')]['sha256'],
        'originalStrictFailurePreserved':True,'frozenPreparationUnchanged':True,'inputFiles':INPUTS,
        'taxonomy':'Project prefix VECTOR_V3_ERROR is unconditional for all errorHandler callbacks; this exact actual ClusterEvent is categoryWARN by its actual JAR constructor.',
        'sourcePath':'Matching archive STOP signal at logRecordingId while ACTIVE/no election -> compare Image.endOfStreamPosition with recording position -> enterElection -> countedErrorHandler(ClusterEvent(reason)). It may initiate election, not a harmless-no-op guarantee.',
        'shutdownOrder':'Owned nodes are created in0,1,2 order; stopOwned iterates the same list and destroys/waits node0 before proceeding to1 then2. Consistent with followerEOS during teardown, not unique causal proof.',
        'timestampLimit':'Only node log byte/line order after the matching final checkpoint is proven. No per-signal clock exists; afterSIGTERM/event-generation walltime is NOT proven.',
        'candidateRuleRequiresSeparateFullRawFunctionalAndStopProof':True,'nextRunAuthorized':False,
        'javaOrSshExecuted':False,'originalDataOrSourceMutated':False}


if __name__=='__main__':
    result=investigate()
    with (HERE/'REVIEW.json').open('x') as stream:json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps({'status':result['status'],'warningPairs':sum(log['warningPairCount'] for arm in result['arms'] for log in arm['logs']),
                      'inputFiles':len(INPUTS),'frozenPreparationUnchanged':True}))
