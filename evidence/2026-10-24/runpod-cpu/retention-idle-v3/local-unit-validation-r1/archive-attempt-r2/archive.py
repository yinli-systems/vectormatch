#!/usr/bin/env python3
"""Offline closed-unit archive. No process launch, Git, network or native inputs."""
from pathlib import Path, PurePosixPath
import collections, datetime, hashlib, io, json, os, re, shutil, stat, zipfile
import xml.etree.ElementTree as ET

WORK=Path('/Users/kevin/Documents/ChatGPT/App 2')
BASE=WORK/'runtime/cloud/cpu-20261024'
TREE=BASE/'latency-idle-v3-worktree'
UNIT=TREE/'runtime/latency-idle-local-validation'
OWN=BASE/'idle-unit-proof-archive-r2'
DEST=WORK/'evidence/2026-10-24/runpod-cpu/retention-idle-v3/local-unit-validation-r1'
MAX_FILE=64*1024*1024

def need(value,reason):
    if not value: raise AssertionError(reason)
def sha(value): return hashlib.sha256(value).hexdigest()
def read(path):
    need(path.is_file() and not path.is_symlink() and path.stat().st_size<=MAX_FILE,'unsafe/big input '+str(path))
    return path.read_bytes()
def js(path): return json.loads(read(path))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as out:json.dump(value,out,indent=2,sort_keys=True);out.write('\n')
def state(path):
    s=path.lstat();need(stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode),'special input '+str(path))
    out={'type':'directory' if stat.S_ISDIR(s.st_mode) else 'file','mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
    if out['type']=='file':
        value=read(path);out.update(bytes=len(value),sha256=sha(value))
    return out
def inventory(root):
    out={'.':state(root)}
    for current,dirs,files in os.walk(root,followlinks=False):
        for name in sorted(dirs+files):
            p=Path(current)/name;out[p.relative_to(root).as_posix()]=state(p)
    need(len(out)<5000,'finite path limit')
    return out

need(DEST.is_dir() and not DEST.is_symlink(),'existing preserved first-attempt copy required; verify before reuse')
need(shutil.disk_usage(WORK).free>1024**3,'disk floor')
groups={**{'units/'+n:UNIT/n for n in ['units-r1','units-r2','units-r3','units-r4']},
        'supplier-correction':UNIT/'idle-supplier-fix-r1',
        'peer-review/historical-r1':BASE/'window-idle-source-review-r1',
        'peer-review/corrected-r2':BASE/'window-idle-supplier-review-r1',
        'root-review/original-r1':BASE/'idle-root-source-review-r1',
        'archive-attempt-r1':BASE/'idle-unit-proof-archive-r1'}
before={label:inventory(path) for label,path in groups.items()}
singles={}
for name in ['SOURCE_FROZEN_R1.json','SOURCE_FROZEN_R2.json','SOURCE_COMMIT.json','SOURCE_COMMIT_R2.json',
             'LOCAL_VALIDATION_COMPLETE.json','run_units.py','run_regression.py','run_regression_r2.py']:
    singles['source-metadata/'+name]=UNIT/name
for attempt in ['units-r1','units-r2','units-r3','units-r4']:
    need('exitCode' in js(UNIT/attempt/'completion.json'),'attempt not closed')
for name,expected in [('SOURCE_FROZEN_R1.json','b51f86fda939539c38001de9c0226f8c42c8b495735889ef797065c6369c6f9d'),
                      ('SOURCE_FROZEN_R2.json','1a41894090a15d8bbcda60442115c55938401849da37966f3c47d78e0c9cdd1d')]:
    need(sha(read(UNIT/name))==expected,'source freeze differs')

# Current complete source materialization is explicitly after-run, not a retroactive capture.
oldroot=js(BASE/'idle-root-source-review-r1/ROOT_SOURCE_REVIEW.json')
fullsource=[]
for pin in oldroot['sourceFiles']:
    path=TREE/pin['path'];value=read(path)
    singles['current-source-after-unit-run/'+pin['path']]=path
    fullsource.append({'path':pin['path'],'bytes':len(value),'sha256':sha(value),'matchesOriginalRootReview':sha(value)==pin['sha256']})
need(len(fullsource)==104,'expected complete104 core/cluster Java source paths')
need({r['path'] for r in fullsource if not r['matchesOriginalRootReview']}=={
    'cluster/src/main/java/io/vectormatch/cluster/RetentionIdlePolicyV3.java',
    'cluster/src/test/java/io/vectormatch/cluster/RetentionIdlePolicyV3Test.java'},'unexpected current source drift')

single_before={name:state(path) for name,path in singles.items()}
need(sum(s.get('bytes',0) for inv in before.values() for s in inv.values())+sum(s.get('bytes',0) for s in single_before.values())<128*1024*1024,'copy bound')
write(OWN/'REGISTRATION.json',{'atUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'helperSha256':sha(read(Path(__file__))),
    'groups':{k:str(v) for k,v in groups.items()},'groupInventories':{k:sha(json.dumps(v,sort_keys=True,separators=(',',':')).encode()) for k,v in before.items()},
    'explicitSingleFiles':{k:{'source':str(singles[k]),**v} for k,v in single_before.items()},
    'scope':'Only closed units/source/reviews, no native-r1 body or native-r2 path walk/read/copy; startup failure referenced separately.'})
DEST.mkdir(parents=True,exist_ok=True)
bindings=[]
for label,root in groups.items():
    target=DEST/label
    for name,pin in sorted(before[label].items(),key=lambda item:(item[0].count('/'),item[0])):
        src=root if name=='.' else root/name;dst=target if name=='.' else target/name
        if dst.exists():need(state(dst)==pin,'preserved first-copy bytes/state differ')
        elif pin['type']=='directory':dst.mkdir(parents=True,exist_ok=True);os.chmod(dst,pin['mode'])
        else:shutil.copy2(src,dst)
        need(state(dst)==pin,'copy state mismatch')
        bindings.append({'source':str(src),'destination':str(dst.relative_to(DEST)),**pin})
    need(inventory(target)==before[label],'exact copied directory/empty-directory closure differs')
for name,src in singles.items():
    dst=DEST/name;dst.parent.mkdir(parents=True,exist_ok=True)
    if dst.exists():need(state(dst)==single_before[name],'preserved single differs')
    else:shutil.copy2(src,dst)
    need(state(dst)==single_before[name],'single copy differs')
    bindings.append({'source':str(src),'destination':name,**single_before[name]})

attempts=[];aux={};jar_reviews=[];classpath_reviews=[]
for attempt in ['units-r1','units-r2','units-r3','units-r4']:
    root=DEST/'units'/attempt;reg=js(root/'registration.json');completion=js(root/'completion.json')
    for pin in reg['inputs']:
        value=read(root/'source'/pin['path']);need(len(value)==pin['bytes'] and sha(value)==pin['sha256'],'captured registered source differs')
    xmlfiles=sorted(root.rglob('TEST-*.xml'));suites=[];totals=collections.Counter()
    for path in xmlfiles:
        value=read(path);suite=ET.fromstring(value);cases=suite.findall('testcase')
        counts={'tests':len(cases),'failures':sum(c.find('failure') is not None for c in cases),
                'errors':sum(c.find('error') is not None for c in cases),'skipped':sum(c.find('skipped') is not None for c in cases)}
        need(all(int(suite.attrib.get(k,0))==v for k,v in counts.items()),'XML counter differs')
        totals.update(counts);suites.append({'path':str(path.relative_to(DEST)),'suite':suite.attrib['name'],'sha256':sha(value),**counts})
    if attempt=='units-r1':
        need(completion['exitCode']==1 and not xmlfiles,'first compile failure must have no new execution XML')
        log=read(root/'stderr.txt');need(b'cannot be applied to given types' in log or b'cannot find symbol' in log,'unsupported-getter compilation failure not observed')
    else:
        need(completion['exitCode']==0 and totals==collections.Counter(completion['totals']),'actual XML versus closed completion differs')
    report={'attempt':attempt,'completion':completion,'registeredSourceInputs':len(reg['inputs']),'actualXmlFiles':len(xmlfiles),'actualXmlTotals':dict(totals),'suites':suites,
            'sourceCaptureScope':'Only modified registered inputs are before-run copies; full104 source materialization elsewhere is after-run.'}
    if attempt in ['units-r3','units-r4']:
        need(b'11 actionable tasks: 11 executed' in read(root/'stdout.txt'),'all forced task transcript missing')
        capture=js(root/'artifact-capture.json');pins={r['path']:r for r in capture['files']}
        actual={p.relative_to(root).as_posix() for p in (root/'artifact-state').rglob('*') if p.is_file()}
        need(actual==set(pins),'artifact-capture exact file closure differs')
        for name,pin in pins.items():
            value=read(root/name);need(len(value)==pin['bytes'] and sha(value)==pin['sha256'],'captured artifact SHA differs')
        for module in ['core','cluster']:
            classes={p.relative_to(root/'artifact-state/classes-main'/module).as_posix():sha(read(p)) for p in (root/'artifact-state/classes-main'/module).rglob('*.class')}
            jar=root/'artifact-state/distribution/lib'/(module+'-0.1.0-SNAPSHOT.jar')
            with zipfile.ZipFile(jar) as z:entries={n:sha(z.read(n)) for n in z.namelist() if n.endswith('.class')}
            need(classes==entries,'main class bytes do not equal installed JAR entries')
            jar_reviews.append({'attempt':attempt,'module':module,'mainClassCount':len(classes),'jarSha256':sha(read(jar)),'fullMainClassesEqualJarEntries':True})
            cp=js(root/(module+'-test-classpath.json'));bound=0
            for source,pin in cp['actualClasspath'].items():
                entries={str(Path(source)/n):v for n,v in pin['files'].items()} if 'files' in pin else {source:pin}
                for original,expected in entries.items():
                    rel=Path(original).relative_to(TREE) if str(original).startswith(str(TREE)+'/') else None
                    mapped=None
                    if rel and len(rel.parts)>=6 and rel.parts[1:4]==('build','classes','java'):
                        mapped=root/'artifact-state'/('classes-main' if rel.parts[4]=='main' else 'classes-test')/rel.parts[0]/Path(*rel.parts[5:])
                    if mapped is None and rel is not None and Path(original).suffix=='.jar':
                        historical=root/'artifact-state/distribution/lib'/Path(original).name
                        if historical.is_file():mapped=historical
                    if mapped is not None:
                        value=read(mapped)
                    else:
                        src=Path(original);value=read(src);name='supplementary-test-inputs/'+expected['sha256']+'/'+src.name
                        if name not in aux:
                            dst=DEST/name;dst.parent.mkdir(parents=True,exist_ok=True)
                            if dst.exists():need(state(dst)==state(src),'preserved supplementary input differs')
                            else:shutil.copy2(src,dst)
                            need(state(dst)==state(src),'supplementary input copy state differs')
                            aux[name]={'source':str(src),'destination':name,**state(src)};bindings.append(aux[name])
                    need(len(value)==expected['bytes'] and sha(value)==expected['sha256'],'configured test input bytes differ: '+original)
                    bound+=1
            classpath_reviews.append({'attempt':attempt,'module':module,'configuredClasspathEntries':len(cp['actualClasspath']),'fileBindings':bound,
                'configuredMembershipAndBytesVerified':True,'actualClassLoadOrderAttested':False,'supplementaryInputBodiesCopiedAfterRunAgainstPreTaskHash':True})
        report['capturedArtifactsFullyRehashed']=len(pins)
    attempts.append(report)
need([r['actualXmlTotals'].get('tests',0) for r in attempts]==[0,29,166,168],'actual execution counts must be0/29/166/168')

startup=WORK/'evidence/2026-10-24/runpod-cpu/retention-idle-v3/startup-failure-r1'
external={}
for name in ['ARCHIVE_REVIEW.json','native-failure.json','closed-failure-originals/completion.json','closed-failure-originals/manifest.json','closed-failure-originals/failed-native-originals.tar.gz']:
    p=startup/name;value=read(p);external[name]={'absolutePath':str(p),'bytes':len(value),'sha256':sha(value)}
need(external['closed-failure-originals/failed-native-originals.tar.gz']['sha256']=='c89f808630724f429f97b4f70a65127f8b3c5d4ecbc730bc75afc515931247db','previous pushed startup failure archive differs')
write(DEST/'STARTUP_FAILURE_REFERENCE.json',{'scope':'SHA-bound reference to existing separately archived/pushed failed native-r1; no native bodies recopied and no native-r2 observation','files':external,'oldSourceCommit':'93ca0f11b64647c2ef1da1aa1e67c7fa1e86fa1a','nativeR1Passed':False,'hundredMicrosecondArmLaunched':False})
write(DEST/'AFTER_RUN_SOURCE_MATERIALIZATION.json',{'scope':'Current104 Java bodies copied after unit runs;102 match old root93 source hash list,2 corrected files match frozenR2. Not a historical full precompile source snapshot.','files':fullsource})
write(DEST/'VALIDATION.json',{'passed':True,'scope':'Closed local unit/source/class/JAR/XML proof only. No native/cloud success or performance claim.',
    'attempts':attempts,'installedJarClassBindings':jar_reviews,'configuredClasspathBindings':classpath_reviews,'supplementaryTestInputFiles':len(aux),
    'latestSourceCommit':js(UNIT/'SOURCE_COMMIT_R2.json')['sourceCommit'],'oldSourceCommit':js(UNIT/'SOURCE_COMMIT.json')['sourceCommit'],
    'oldRootReviewSourceCount':len(oldroot['sourceFiles']),'oldRootReviewActualTests':oldroot['actualFrozenXmlTestcases'],
    'nativeR1FailureReferencedSeparately':True,'nativeR2ReadCopiedOrHashedByArchiveHelper':False})

patterns={'private-key-header':re.compile(rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED) PRIVATE KEY-----'),
    'github-token':re.compile(rb'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b'),
    'aws-access-key-id':re.compile(rb'\bAKIA[A-Z0-9]{16}\b'),
    'runpod-token':re.compile(rb'\b(?:rpa|rp)_[A-Za-z0-9]{30,}\b'),
    'credential-dsn':re.compile(rb'(?i)(?:postgres(?:ql)?|mysql)://[^/\s:@]+:[^@\s]+@')}
scan={'filesAndMembers':0,'bytes':0,'hits':[],'scope':'Known credential-marker review only, not a general absence-of-secrets proof.'};nested=[]
def markers(label,value):
    scan['filesAndMembers']+=1;scan['bytes']+=len(value);need(scan['bytes']<=512*1024*1024,'scan bound')
    for kind,pattern in patterns.items():
        found=list(pattern.finditer(value))
        if found:scan['hits'].append({'path':label,'kind':kind,'count':len(found),'offsets':[m.start() for m in found[:16]]})
def zip_review(label,value):
    with zipfile.ZipFile(io.BytesIO(value)) as z:
        need(len(z.infolist())==len(set(z.namelist())) and len(z.infolist())<10000,'ZIP closure bound')
        entries=[]
        for item in z.infolist():
            path=PurePosixPath(item.filename);need(not path.is_absolute() and '..' not in path.parts and not stat.S_ISLNK(item.external_attr>>16),'ZIP unsafe path')
            need(item.file_size<=MAX_FILE,'ZIP member bound');body=z.read(item);need(len(body)==item.file_size,'ZIP CRC/full byte read')
            entries.append({'path':item.filename,'bytes':len(body),'sha256':sha(body),'directory':item.is_dir(),'mode':stat.S_IMODE(item.external_attr>>16),'crc32':item.CRC,'externalAttributes':item.external_attr,'createSystem':item.create_system})
            if not item.is_dir():markers(label+'!/'+item.filename,body)
        nested.append({'path':label,'bytes':len(value),'sha256':sha(value),'entries':entries,'uidGidAvailable':False,'allMemberBytesCrcShaRead':True})

tools=DEST/'tools';tools.mkdir();shutil.copy2(Path(__file__),tools/'archive.py')
write(DEST/'COPY_BINDINGS.json',bindings)
for p in sorted(DEST.rglob('*')):
    if p.is_file():
        value=read(p);label=p.relative_to(DEST).as_posix();markers(label,value)
        if p.suffix in ['.jar','.zip']:zip_review(label,value)
write(DEST/'ZIP_MEMBER_INVENTORIES.json',nested)
scan.update(passed=not scan['hits'],manualClassificationRequired=bool(scan['hits']),selfReportExcluded=True)
write(DEST/'CREDENTIAL_MARKER_REVIEW.json',scan)
for label,root in groups.items():need(inventory(root)==before[label],'closed input changed during archive '+label)
for name,pin in single_before.items():need(state(singles[name])==pin,'single input changed during archive')
for pin in aux.values():need(state(Path(pin['source']))=={k:v for k,v in pin.items() if k not in ['source','destination']},'supplementary input changed')
write(OWN/'COMPLETION.json',{'passed':True,'destination':str(DEST),'copiedSourceFiles':sum(r['type']=='file' for r in bindings),'copiedBytes':sum(r.get('bytes',0) for r in bindings),
    'xmlTests':[r['actualXmlTotals'].get('tests',0) for r in attempts],'markerHits':len(scan['hits']),'zipArchives':len(nested),'freeBytes':shutil.disk_usage(WORK).free})
print(json.dumps(js(OWN/'COMPLETION.json'),sort_keys=True))
