"""Pure local validation shared by the closed-round collector/auditors. No network at import."""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, re, sys
def valid_prep(value):return isinstance(value,str) and re.fullmatch(r'/opt/vectormatch-cpu/preparation/cpu-idle-cloud-abab-r1',value) is not None
WINDOWS=(8,)
def require(value,message):
    if not value: raise AssertionError(message)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
    return h.hexdigest()
def hexsha(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None
def relative(value):
    p=PurePosixPath(value)
    require(isinstance(value,str) and value and bool(p.parts) and str(p)==value and not p.is_absolute() and '..' not in p.parts and '.' not in p.parts,'Unsafe noncanonical relative path')
    return value
def load_config(path):
    c=json.loads(Path(path).read_text())
    require(c['schemaVersion']==2 and type(c['arm']) is int and c['arm'] in (1,2,3,4),'Idle arm/config version')
    prep=c['remotePrep'];require(valid_prep(prep) and c['host']=='ed6c0673f5cb','Fixed idle PREP/host')
    for key,h in [('releaseLocal','releaseSha256'),('stagingReceipt','stagingReceiptSha256'),('protectedReference','protectedReferenceSha256')]:
        require(hexsha(c[h]) and sha(c[key])==c[h], 'Frozen local input differs: '+key)
    release=json.loads(Path(c['releaseLocal']).read_text())
    from cpu_idle_abab import validate_release, selection, PARK_ORDER
    validate_release(release)
    require(c['maximumParkNs']==PARK_ORDER[c['arm']-1], 'Canonical ABAB arm order required')
    require(release['arms'][str(c['arm'])]=={'job':prep+'/arm-'+str(c['arm']),
            'armRoot':prep+'/arm-'+str(c['arm'])+'/idle-arm','maximumParkNs':c['maximumParkNs']},'Fixed idle arm roots differ')
    staged=json.loads(Path(c['stagingReceipt']).read_text())
    require(staged['passed'] is True and isinstance(staged['stagedFiles'],dict), 'Successful explicit stage required')
    require(staged['releaseSha256']==c['releaseSha256'] and staged['controllerSha256']==release['controllerSha256'], 'Stage release/controller differs')
    require(staged['applicationStarted'] is False and staged['resourceCreated'] is False,
            'Collection source binding requires metadata-only stage receipt')
    expected=dict(staged['stagedFiles']);require(8<=len(expected)<=64,'Bounded explicit stage allowlist')
    for name,row in expected.items():
        relative(name);require(not name.startswith(('arm-1','arm-2','arm-3','arm-4')), 'Cannot tar a job tree as source')
        require(type(row['bytes']) is int and 0<=row['bytes']<=32*1024**2 and hexsha(row['sha256']), 'Frozen source bytes/SHA')
    require(expected['release/release.json']['sha256']==c['releaseSha256'], 'Source release binding differs')
    require(expected['cpu_idle_abab.py']['sha256']==release['controllerSha256']
            and expected['owned_linux_base_8eeb.py']['sha256']=='8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87',
            'Stage must contain the exact controller and reviewed owned-process helper')
    for name in ['idle_attestation.py','common.py','read_phase_audit.py','shutdown_warning.py']:
        require(expected[name]['sha256']==sha(Path(__file__).with_name(name)),
                'Staged/independent local schema source differs: '+name)
    require(c['protectedReferenceSha256']==release['protectedOriginalState']['manifestSha256'], 'Protected57/PG989 reference differs')
    gates=c.get('priorGates',{})
    require(set(gates)=={str(n) for n in range(1,c['arm'])}, 'Exact preceding collected-arm prefix required')
    for key,row in gates.items():
        n=int(key);require(set(row)=={'local','sha256'} and hexsha(row['sha256']) and sha(row['local'])==row['sha256'], 'Prior gate file differs')
        gate=json.loads(Path(row['local']).read_text())
        require(gate['schemaVersion']==2 and gate['scope']=='ROOT_VERIFIED_CLOSED_CPU_IDLE_ARM_COLLECTION'
                and gate['collectionComplete'] is True and gate['arm']==n and gate['maximumParkNs']==PARK_ORDER[n-1]
                and gate['frozenReleaseSha256']==c['releaseSha256'] and gate['controllerSha256']==release['controllerSha256']
                and gate['localFullMemberShaBytesModesOwnersEmptyDirsVerified'] is True
                and gate['allRawInputsAndFailuresRetained'] is True
                and hexsha(gate['independentLocalCollectionReceiptSha256']), 'Root prior-arm collection gate differs')
        name='release/arm-%d-collection-gate.json'%n
        require(name not in expected,'Prior gates are separately explicit inputs')
        expected[name]={'bytes':Path(row['local']).stat().st_size,'sha256':row['sha256']}
    metadata=c['executionMetadata']
    require(isinstance(metadata,list) and len(metadata)==3 and len(set(metadata))==3, 'Exactly3 opaque execution metadata names')
    require(metadata==['arm-%d-execution-register.json'%c['arm'],
            'arm-%d-execution.stdout'%c['arm'],'arm-%d-execution.stderr'%c['arm']],
            'Exact current-arm opaque execution metadata allowlist required')
    for name in metadata:relative(name);require('/' not in name and name not in expected, 'Explicit root metadata only')
    allow=sorted(set(expected)|set(metadata));require(len(allow)==len(expected)+3, 'Source whitelist collision')
    return c,release,expected,allow

def audit_arguments(description):
    p=argparse.ArgumentParser(description=description);p.add_argument('--config',required=True,type=Path);p.add_argument('--collection',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();c,r,e,allow=load_config(a.config);require(a.collection.is_dir(),'Closed local collection missing');a.out.mkdir(parents=True,exist_ok=False)
    (a.out/'executed-auditor.py').write_bytes(Path(sys.argv[0]).read_bytes());(a.out/'common.py').write_bytes(Path(__file__).read_bytes());(a.out/'collector-config.json').write_bytes(a.config.read_bytes())
    return a,c,r

def egress(bounds):
    require(bounds['requiredApplicationReplyBytes']==6919 and bounds['aeronSessionHeaderBytes']==32 and bounds['requiredCompleteMessageBytes']==6951,'Common supported complete reply envelope')
    require(bounds['defaultMetadataSubstituted'] is False and bounds['sameOwnerThreadRequired'] is True and bounds['actualImageObservations']>=1,'Actual owner Image observations required')
    require(bounds['maximumEverObservedImages']==16 and bounds['maximumLifecycleEvents']==256,'Fixed bounded actual Image lifecycle policy')
    geometry={};count=0;limits=[]
    require(1<=len(bounds['images'])<=16,'Bounded actual Images')
    for row in bounds['images']:
        term=row['actualTermBufferLength'];require(type(term) is int and term>=65536 and term&(term-1)==0 and row['actualMtuLength']==1248,'Actual receiver geometry invalid')
        maximum=min(term//8,16*1024**2);require(row['derivedMaxMessageLength']==maximum and maximum>=6951,'Actual receiver cannot fit common complete reply')
        key=row['imageCorrelationId'];require(type(key) is int and key>=0 and key not in geometry,'Duplicate Image correlation')
        geometry[key]={k:row[k] for k in ['imageCorrelationId','publicationSessionId','streamId','actualTermBufferLength','actualMtuLength','derivedMaxMessageLength']}
        n=row['associatedApplicationReplies'];largest=row['largestObservedApplicationReplyBytes'];require(type(n) is int and n>=0 and type(largest) is int and 0<=largest<=8192 and largest+32<=maximum,'Per-Image association/size bounds')
        count+=n;limits.append(maximum)
    active=bounds['activeImageCorrelations'];events=bounds['lifecycleEvents']
    require(isinstance(active,list) and active and active==sorted(set(active)) and set(active)=={r['imageCorrelationId'] for r in bounds['images'] if r['activeAtLastObservation'] is True} and all(type(r['activeAtLastObservation']) is bool for r in bounds['images']),'Active actual Image set/flags')
    require(isinstance(events,list) and len(events)<=256,'Bounded actual lifecycle event list')
    seen=set();event_active=set();previous_at=None
    for n,event in enumerate(events,1):
        require(set(event)=={'sequence','event','imageCorrelationId','observedAtMonotonicNs','source'} and event['sequence']==n and event['source']=='actual owner-thread egress subscription Image observation' and type(event['observedAtMonotonicNs']) is int and (previous_at is None or event['observedAtMonotonicNs']>=previous_at),'Lifecycle source/order')
        previous_at=event['observedAtMonotonicNs'];key=event['imageCorrelationId'];require(type(key) is int and key in geometry,'Lifecycle unknown actual Image')
        if event['event']=='ADDED':require(key not in seen,'Seen/retired Image cannot return');seen.add(key);event_active.add(key)
        else:require(event['event']=='REMOVED' and key in event_active,'Invalid Image removal');event_active.remove(key)
    require(seen==set(geometry) and event_active==set(active),'Ever-seen/active lifecycle closure')
    require(count==bounds['replyHeaderImageAssociations'] and min(limits)==bounds['minimumActualDerivedMaxMessageLength'],'Image aggregate count/geometry mismatch')
    return geometry

def egress_progress(previous,current):
    old,new=egress(previous),egress(current)
    require(all(key in new and new[key]==row for key,row in old.items()),'Historical Image geometry removed/changed')
    require(current['lifecycleEvents'][:len(previous['lifecycleEvents'])]==previous['lifecycleEvents'] and current['actualImageObservations']>=previous['actualImageObservations'] and current['replyHeaderImageAssociations']>=previous['replyHeaderImageAssociations'],'Lifecycle prefix/aggregate counters regressed')
    before={row['imageCorrelationId']:row for row in previous['images']}
    for row in current['images']:
        prior=before.get(row['imageCorrelationId'])
        require(prior is None or (row['associatedApplicationReplies']>=prior['associatedApplicationReplies'] and row['largestObservedApplicationReplyBytes']>=prior['largestObservedApplicationReplyBytes']),'Per-Image association/maximum counters regressed')
    return new
