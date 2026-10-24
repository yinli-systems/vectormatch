#!/usr/bin/env python3
"""Offline native archive readback. Never walks arms or restart preparation."""
from pathlib import Path, PurePosixPath
import csv, datetime, hashlib, io, json, os, re, shutil, stat, tarfile, zipfile

WORK=Path('/Users/kevin/Documents/ChatGPT/App 2');BASE=WORK/'runtime/cloud/cpu-20261024'
NATIVE=BASE/'latency-idle-v3-worktree/runtime/latency-idle-local-validation/native-r2'
OWN=BASE/'idle-native-proof-archive-r2'
DEST=WORK/'evidence/2026-10-24/runpod-cpu/retention-idle-v3/local-native-validation-r2'
UNIT=WORK/'evidence/2026-10-24/runpod-cpu/retention-idle-v3/local-unit-validation-r1'
MAX_FILE=64*1024*1024
def need(v,s):
    if not v:raise AssertionError(s)
def sha(v):return hashlib.sha256(v).hexdigest()
def read(p):
    need(p.is_file() and not p.is_symlink() and p.stat().st_size<=MAX_FILE,'unsafe/big outer file '+str(p))
    return p.read_bytes()
def js(p):return json.loads(read(p))
def write(p,o):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x')as f:json.dump(o,f,indent=2,sort_keys=True);f.write('\n')
def state(p):
    s=p.lstat();need(stat.S_ISREG(s.st_mode)or stat.S_ISDIR(s.st_mode),'special input')
    r={'type':'directory'if stat.S_ISDIR(s.st_mode)else'file','mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
    if r['type']=='file':v=read(p);r.update(bytes=len(v),sha256=sha(v))
    return r

need(not DEST.exists(),'fresh destination required')
need(shutil.disk_usage(WORK).free>1024**3,'disk floor')
names=['registration.json','run_native.py','native-failure.json','capture_closed.py','FINAL_LOCAL_NATIVE_EVIDENCE.json',
    'closed-originals/native-originals.tar.gz','closed-originals/manifest.json','closed-originals/completion.json',
    'post-close-audit-r1/result.json','post-close-audit-r1/INPUT_CLOSURE.json','post-close-audit-r1/SOURCE_PROVENANCE.json','post-close-audit-r1/run_audit.py',
    'post-close-audit-r1/source/audit_raw.py','post-close-audit-r1/source/common.py','post-close-audit-r1/source/read_phase_audit.py','post-close-audit-r1/source/adaptation.diff',
    'post-close-audit-r1/frozen-baseline/audit_raw.py','post-close-audit-r1/frozen-baseline/common.py','post-close-audit-r1/frozen-baseline/read_phase_audit.py']
for park in [1000000,100000]:
    for name in ['before.json','parent-identity.json','exit.json','stdout.txt','stderr.txt']:
        names.append('arm-%d-process/%s'%(park,name))
names.append('arm-1000000-process/functional-inspection.json')
sources={'native-metadata/'+name:NATIVE/name for name in names}
sources['root-source-review/ROOT_SOURCE_REVIEW.json']=BASE/'idle-root-source-review-r2/ROOT_SOURCE_REVIEW.json'
warning=BASE/'cpu-idle-shutdown-warning-review-r1';wc=js(warning/'CLOSED_REVIEW.json')
for name,pin in wc['sourceFilesAndProof'].items():
    value=read(warning/name);need(len(value)==pin['bytes']and sha(value)==pin['sha256']and state(warning/name)['mode']==pin['mode'],'warning review freeze differs')
    sources['shutdown-warning-review/'+name]=warning/name
sources['shutdown-warning-review/CLOSED_REVIEW.json']=warning/'CLOSED_REVIEW.json'
before={name:state(p)for name,p in sources.items()}
need(sha(read(NATIVE/'FINAL_LOCAL_NATIVE_EVIDENCE.json'))=='2e96d1c45049a08115e72491aeb2c264e955091101ebdb7548ccb6cf4c93aec6','final receipt differs')
need(sha(read(sources['root-source-review/ROOT_SOURCE_REVIEW.json']))=='0b4cbeb28859b41a0ef821ffd222552a0b2f76b2156294cbcf8de9a51873c027','root source review differs')
completion=js(NATIVE/'closed-originals/completion.json');manifest=js(NATIVE/'closed-originals/manifest.json')
need(sha(read(NATIVE/'closed-originals/manifest.json'))==completion['manifestSha256']=='18915c6842d0df2a9b6a2462579f12460c3b97ad86c9bd17eb40d92de06dea8f','native manifest pin')
closure=js(NATIVE/'post-close-audit-r1/INPUT_CLOSURE.json');final=js(NATIVE/'FINAL_LOCAL_NATIVE_EVIDENCE.json');audit=js(NATIVE/'post-close-audit-r1/result.json')
need(closure['inputCount']==len(closure['inputs'])==89 and closure['frozenManifestSha256']==completion['manifestSha256'],'89 input closure')
need(sha(read(NATIVE/'post-close-audit-r1/INPUT_CLOSURE.json'))==final['inputClosureSha256'],'closure receipt pin')
need(sha(read(NATIVE/'post-close-audit-r1/result.json'))==final['readOnlyAuditSha256'],'audit receipt pin')
need(final['originalStrictOuterGate']=='FAILED_PRESERVED'and audit['originalStrictOuterGateStillFailed']is True,'strict failure must remain')
need(final['warnings']['count']==len(audit['warningsRetained'])==2 and not audit['warningAfterSigtermTimestampIndependentlyProven'],'warning scope')
need(not final['capacityOrSpeedupClaimed']and not final['hardRealtimeGuaranteed']and final['programFunctionalResultsPassed'],'qualified scope')

write(OWN/'REGISTRATION.json',{'atUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'helperSha256':sha(read(Path(__file__))),
    'explicitFiles':{k:{'source':str(sources[k]),**v}for k,v in before.items()},
    'scope':'Only explicit closed metadata files and frozen compressed originals. No arms/restart filesystem recursion or native execution.'})
DEST.mkdir(parents=True);bindings=[]
for name,p in sources.items():
    target=DEST/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);need(state(target)==before[name],'outer copied state mismatch')
    bindings.append({'source':str(p),'destination':name,**before[name]})

patterns={'private-key-header':re.compile(rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED) PRIVATE KEY-----'),
    'github-token':re.compile(rb'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b'),
    'aws-access-key-id':re.compile(rb'\bAKIA[A-Z0-9]{16}\b'),'runpod-token':re.compile(rb'\b(?:rpa|rp)_[A-Za-z0-9]{30,}\b'),
    'credential-dsn':re.compile(rb'(?i)(?:postgres(?:ql)?|mysql)://[^/\s:@]+:[^@\s]+@')}
scan={'scope':'Known markers only; TAR files streamed with512byte cross-chunk overlap. Entirely zero chunks are examined as zeros and cannot contain a printable marker. Not a general arbitrary-secret absence proof.',
    'observedBytes':0,'zeroBytesExamined':0,'regexInputBytes':0,'hits':[]}
def markers(label,value,baseoffset=0):
    scan['regexInputBytes']+=len(value)
    for kind,pattern in patterns.items():
        found=list(pattern.finditer(value))
        if found:scan['hits'].append({'path':label,'kind':kind,'count':len(found),'offsets':[baseoffset+m.start()for m in found[:16]]})

pins={r['path']:r for r in manifest['entries']};need(len(pins)==len(manifest['entries'])==234,'native manifest exact entry closure')
for name,pin in closure['inputs'].items():
    need('native/'+name in pins,'audit input omitted from frozen original manifest')
    original=pins['native/'+name];need(original['bytes']==pin['bytes']and original['sha256']==pin['sha256'],'audit input versus frozen original')
small={name for name in closure['inputs']if not name.endswith('.bin')}
extra_small={'native/arms/park-%d/artifact-inventory.json'%park for park in [1000000,100000]}
jar_buffers={};small_values={};seen=set();native_reports=[];inputseen=set();logical=0
tarpath=DEST/'native-metadata/closed-originals/native-originals.tar.gz'
need(sha(read(tarpath))==completion['archiveSha256']=='8b1aaca6f0771f084f3c14bb56f892cbcf4b184e6140bb83da373e5b0f0a8028','compressed originals SHA')
with tarfile.open(tarpath,mode='r|gz')as stream:
    for member in stream:
        name=member.name;parts=PurePosixPath(name)
        need(not parts.is_absolute()and'..'not in parts.parts and name in pins and name not in seen,'TAR path/closure')
        seen.add(name);pin=pins[name];directory=member.isdir()
        need(directory==(pin['type']=='directory')and(directory or member.isfile()),'TAR type/hardlink/symlink')
        need((member.mode,member.uid,member.gid)==(pin['mode'],pin['uid'],pin['gid']),'TAR exact mode/owner')
        row={'path':name,'type':pin['type'],'mode':member.mode,'uid':member.uid,'gid':member.gid,'bytes':member.size,'tarMtime':member.mtime}
        if not directory:
            need(member.size==pin['bytes'],'TAR bytes')
            body=stream.extractfile(member);digest=hashlib.sha256();n=0;carry=b''
            capture=name.startswith('input-distribution/lib/')or name.startswith('input-source/')or name.startswith('input-proofs/')or name in extra_small or(name.startswith('native/')and name[7:]in small)
            buffer=io.BytesIO()if capture else None
            while True:
                chunk=body.read(1024*1024)
                if not chunk:break
                digest.update(chunk);scan['observedBytes']+=len(chunk)
                if chunk.count(0)==len(chunk):
                    scan['zeroBytesExamined']+=len(chunk);markers(name,carry+chunk[:512],max(0,n-len(carry)))
                else:markers(name,carry+chunk,max(0,n-len(carry)))
                carry=(carry+chunk)[-512:];n+=len(chunk)
                if buffer is not None:buffer.write(chunk)
            need(n==pin['bytes']and digest.hexdigest()==pin['sha256'],'full logical TAR payload SHA')
            row['sha256']=digest.hexdigest();logical+=n
            if name.startswith('native/')and name[7:]in closure['inputs']:inputseen.add(name[7:])
            if capture:
                value=buffer.getvalue();need(len(value)<=MAX_FILE,'bounded selective materialization')
                if name.startswith('input-distribution/lib/'):jar_buffers[Path(name).name]=value
                else:
                    small_values[name]=value;target=DEST/'selected-small-inputs'/name;target.parent.mkdir(parents=True,exist_ok=True)
                    with target.open('xb')as out:out.write(value)
                    os.chmod(target,pin['mode']);need(state(target)['sha256']==pin['sha256'],'selected materialization differs')
        native_reports.append(row)
need(seen==set(pins)and inputseen==set(closure['inputs']),'complete archive/input89 closure')
need(logical==completion['logicalFileBytes']==2492259516,'full logical native byte total')

unitinv=js(UNIT/'FINAL_LOCAL_INVENTORY.json')['paths'];jar_entries=[]
for name,value in jar_buffers.items():
    pin=unitinv['units/units-r4/artifact-state/distribution/lib/'+name]
    need(len(value)==pin['bytes']and sha(value)==pin['sha256'],'native runtime JAR versus closed unit exact bytes')
    with zipfile.ZipFile(io.BytesIO(value))as z:
        need(len(z.namelist())==len(set(z.namelist())),'JAR duplicate names')
        entries=[]
        for item in z.infolist():
            p=PurePosixPath(item.filename);need(not p.is_absolute()and'..'not in p.parts and not stat.S_ISLNK(item.external_attr>>16),'JAR path')
            value2=z.read(item);need(len(value2)==item.file_size,'JAR CRC/full bytes')
            entries.append({'path':item.filename,'bytes':len(value2),'sha256':sha(value2),'directory':item.is_dir(),'mode':stat.S_IMODE(item.external_attr>>16),'crc32':item.CRC})
            if not item.is_dir():markers('TAR!input-distribution/lib/'+name+'!/'+item.filename,value2)
        jar_entries.append({'file':name,'bytes':len(value),'sha256':sha(value),'entries':entries,'uidGidAvailable':False})
anchors=[('io.vectormatch.cluster.RetentionNodeMainV3','cluster-0.1.0-SNAPSHOT.jar'),('io.vectormatch.core.MatchingEngine','core-0.1.0-SNAPSHOT.jar'),('io.aeron.driver.MediaDriver','aeron-all-1.53.3.jar'),('org.agrona.DirectBuffer','aeron-all-1.53.3.jar')]
fingerprint=hashlib.sha256()
for name,jar in anchors:fingerprint.update(name.encode());fingerprint.update(jar_buffers[jar])
need(fingerprint.hexdigest()==final['actualCodeFingerprint']=='f78025f91f9e43ad634840b400ab04ed4ae422597c35800984e434dbd1844c8f','actual loaded artifact fingerprint binding')
for park in [1000000,100000]:
    inv=json.loads(small_values['native/arms/park-%d/artifact-inventory.json'%park])
    for item in inv['actualFiles']:
        need(item['type']in dict(anchors),'unknown loaded code anchor')
        value=jar_buffers[dict(anchors)[item['type']]]
        need(item['bytes']==len(value)and item['sha256']==sha(value),'actual code-source artifact inventory differs')

scheduler=[]
for park in [1000000,100000]:
    prefix='native/arms/park-%d/'%park;table=list(csv.DictReader(small_values[prefix+'load/arrivals.csv'].decode('ascii').splitlines()));need(len(table)==6400,'6400 arrivals')
    late=0;orders=set()
    for i,row in enumerate(table):
        need(int(row['arrival_index'])==i and int(row['scheduled_offset_ns'])==i*2_000_000,'raw schedule identity')
        need(row['status']=='APPLIED'and row['result_code']=='ACCEPTED'and not row['unknown_observed_offset_ns']and row['not_sent_reason']=='0','functional result/UNKNOWN/notSent')
        late+=int(row['arrival_offset_ns'])-int(row['scheduled_offset_ns'])>20_000_000;orders.add(int(row['order_id']))
    need(orders==set(range(2,6402)),'6400 unique accepted order IDs')
    result=json.loads(small_values[prefix+'load/load-result.json']);expected=249 if park==1000000 else 4
    need(late==expected==result['schedulerLatenessOver20ms']and result['schedulerTimingValid']is False,'invalid scheduler must remain explicit')
    scheduler.append({'maximumParkNs':park,'actualAcceptedDistinctOrders':6400,'unknownObserved':0,'notSent':0,'schedulerLatenessOver20ms':late,'schedulerTimingValid':False,'performanceComparisonAdmissible':False})

write(DEST/'TAR_READBACK.json',{'passed':True,'compressedSha256':sha(read(tarpath)),'exactManifestEntries':len(seen),'logicalFileBytesReadAndFullShaVerified':logical,'all89AuditInputShaVerified':True,
    'explicitDirectoriesAndEmptyDirectoryClosureVerified':True,'exactModesUidGidVerified':True,'sourceDirectoryAncestorsNotExplicitTarMembersNotAttested':True,'entries':native_reports})
write(DEST/'RUNTIME_SOURCE_BINDING.json',{'passed':True,'actualCodeFingerprint':fingerprint.hexdigest(),'actualAnchors':anchors,'allFourJarsEqualUnitR4CapturedBodies':True,
    'jarBodiesDuplicatedOutsideTar':False,'jarEntries':jar_entries,'unitProofInventorySha256':sha(read(UNIT/'FINAL_LOCAL_INVENTORY.json'))})
write(DEST/'FUNCTIONAL_SCOPE.json',{'qualifiedFunctionalCanonicalOnly':True,'originalStrictOuterGatePassed':False,'originalFailureBytesPreserved':True,'warningCount':2,
    'warningSigtermCausalityIndependentlyProven':False,'bothSchedulerTimingValid':False,'schedulerRawRecomputation':scheduler,'speedupCapacityOrRealtimeClaimed':False,
    'all89OriginalAuditInputsShaBound':True,'postCloseAuditIndependentNewExecution':False,'nativeRestartProofIncluded':False})
write(DEST/'COPY_BINDINGS.json',bindings)
tool=DEST/'tools';tool.mkdir();shutil.copy2(Path(__file__),tool/'archive.py')
for p in sorted(DEST.rglob('*')):
    if p.is_file()and p.suffix not in ['.gz']:
        value=read(p);markers(p.relative_to(DEST).as_posix(),value)
        if p.suffix=='.zip':
            with zipfile.ZipFile(io.BytesIO(value))as z:
                for item in z.infolist():
                    if not item.is_dir():markers(p.relative_to(DEST).as_posix()+'!/'+item.filename,z.read(item))
scan.update(passed=not scan['hits'],manualClassificationRequired=bool(scan['hits']));write(DEST/'CREDENTIAL_MARKER_REVIEW.json',scan)
for name,pin in before.items():need(state(sources[name])==pin,'closed outer source changed while copying')
need(not scan['hits'],'known marker findings need classification before final close')
write(OWN/'COMPLETION.json',{'passed':True,'destination':str(DEST),'outerExplicitFiles':len(sources),'selectedSmallFiles':len(small_values),'fullNativeLogicalBytesVerified':logical,
    'tarEntries':len(seen),'auditInputCount':len(inputseen),'knownMarkerHits':0,'schedulerTimingValidBoth':False,'performanceClaimed':False,'freeBytes':shutil.disk_usage(WORK).free})
print(json.dumps(js(OWN/'COMPLETION.json'),sort_keys=True))
