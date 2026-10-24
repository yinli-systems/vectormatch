"""Pure local validation shared by the closed-round collector/auditors. No network at import."""
from pathlib import Path, PurePosixPath
import argparse, hashlib, json, re, sys
def valid_prep(value):return isinstance(value,str) and re.fullmatch(r'/opt/vectormatch-cpu/preparation/window-cloud-abab-r[1-9][0-9]*',value) is not None
WINDOWS=(1,8)
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
    c=json.loads(Path(path).read_text());require(c['schemaVersion']==1 and type(c['round']) is int and c['round'] in (1,2),'Round/config version')
    prep=c['remotePrep'];require(valid_prep(prep) and c['host']=='ed6c0673f5cb','Root-frozen owned preparation path/host')
    require(hexsha(c['releaseSha256']) and hexsha(c['stagingReceiptSha256']) and hexsha(c['protectedReferenceSha256']),'Explicit frozen input SHA values required')
    for key,h in [('releaseLocal','releaseSha256'),('stagingReceipt','stagingReceiptSha256'),('protectedReference','protectedReferenceSha256')]:require(sha(c[key])==c[h],'Frozen local input differs: '+key)
    release=json.loads(Path(c['releaseLocal']).read_text());require(release['releaseReady'] is True and release['host']==c['host'],'Final root-frozen release required')
    require(hexsha(release['codeFingerprint']) and hexsha(release['profileFingerprint']) and hexsha(release['controllerSha256']) and re.fullmatch('[0-9a-f]{40}',release['sourceCommit']),'Frozen actual source/artifact fingerprints')
    require(release['rounds'][str(c['round'])]=={'job':prep+'/round-'+str(c['round']),'pairRoot':prep+'/round-'+str(c['round'])+'/read-window-pair'},'Release round paths differ')
    fixed=release['configuration'];require(all(fixed[k]==v for k,v in {'arrivals':6400,'ratePerSecond':500,'batchCap':4,'eventFetchCount':16,'appointedLeader':0,'sync':2,'workers':128,'queuePerWorker':64,'preparedArchiveCache':True,'samePortsAcrossArms':True,'fixedBasePorts':42000,'archiveChunkBytes':6144,'commonChunkEnvelope':False,'commonReadWindowEnvelope':True,'mtu':1248}.items()),'Fixed experiment configuration differs')
    require(fixed['readWindowOrder']==[1,8,1,8],'Registered ABAB order differs')
    staged=json.loads(Path(c['stagingReceipt']).read_text());require(staged['passed'] is True and isinstance(staged['stagedFiles'],dict),'Successful exact staged receipt required')
    expected=dict(staged['stagedFiles']);require(8<=len(expected)<=64,'Bounded explicit source allowlist required')
    for name,row in expected.items():
        relative(name);require(not name.startswith(('round-1/','round-2/')) and name not in ('round-1','round-2'),'Cannot allow source job tree')
        require(type(row['bytes']) is int and 0<=row['bytes']<=32*1024**2 and hexsha(row['sha256']),'Invalid frozen source file row')
    require('release/release.json' in expected and expected['release/release.json']['sha256']==c['releaseSha256'],'Actual source release binding differs')
    if c['round']==2:
        require(hexsha(c.get('round1GateSha256')) and sha(c['round1GateLocal'])==c['round1GateSha256'],'Explicit root-approved round-1 gate SHA required')
        gate=json.loads(Path(c['round1GateLocal']).read_text())
        require(gate['collectionComplete'] is True and gate['round']==1 and gate['scope']=='ROOT_VERIFIED_CLOSED_WINDOW_ROUND_1_COLLECTION' and gate['frozenReleaseSha256']==c['releaseSha256'] and gate['controllerSha256']==release['controllerSha256'],'Root round-1 gate release/controller approval differs')
        name='release/round-1-collection-gate.json';require(name not in expected,'Round-1 gate must be a separate exact frozen file')
        expected[name]={'bytes':Path(c['round1GateLocal']).stat().st_size,'sha256':c['round1GateSha256']}
    else:require(c.get('round1GateLocal') is None and c.get('round1GateSha256') is None,'Round-1 collection cannot include a future gate')
    metadata=c['executionMetadata'];require(isinstance(metadata,list) and len(metadata)==3 and len(set(metadata))==3,'Exactly three execution metadata names')
    for name in metadata:relative(name);require('/' not in name and name not in expected,'Execution metadata must be explicit root file names')
    allow=sorted(set(expected)|set(metadata));require(len(allow)==len(expected)+3,'Source whitelist collision')
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
