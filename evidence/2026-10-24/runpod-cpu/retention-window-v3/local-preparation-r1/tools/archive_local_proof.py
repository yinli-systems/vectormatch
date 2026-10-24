#!/usr/bin/env python3
"""Offline, allowlisted copies and byte-level validation. Never launches Java, Git or cloud tools."""
from pathlib import Path, PurePosixPath
import datetime, hashlib, io, json, os, re, shutil, stat, zipfile
import xml.etree.ElementTree as ET

WORK = Path('/Users/kevin/Documents/ChatGPT/App 2')
RUNTIME = WORK/'runtime/cloud/cpu-20261024'
OWN = RUNTIME/'window-local-proof-archive-r1'
DEST = WORK/'evidence/2026-10-24/runpod-cpu/retention-window-v3/local-preparation-r1'
UNIT_ROOT = RUNTIME/'retention-window-v3-worktree/build/window-validation'
PREP = RUNTIME/'window-cloud-preparation-r1'
HELPER = RUNTIME/'window-cloud-release-observation-r1'
MAX_FILE = 64*1024*1024
MAX_SCAN = 512*1024*1024

def require(value, message):
    if not value: raise AssertionError(message)

def sha(data): return hashlib.sha256(data).hexdigest()
def read(path):
    require(path.is_file() and not path.is_symlink(), 'not a regular input: '+str(path))
    require(path.stat().st_size<=MAX_FILE, 'file bound: '+str(path))
    return path.read_bytes()
def js(path): return json.loads(read(path))
def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f: json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def state(path):
    s=path.lstat();require(stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode),'special/symlink refused: '+str(path))
    result={'type':'directory' if stat.S_ISDIR(s.st_mode) else 'file','mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
    if result['type']=='file':
        b=read(path);result.update(bytes=len(b),sha256=sha(b))
    return result
def inventory(root, exclude_cache=False):
    out={'.':state(root)}
    for current,dirs,files in os.walk(root,followlinks=False):
        if exclude_cache: dirs[:]=[d for d in dirs if d!='__pycache__']
        for name in sorted(dirs+files):
            p=Path(current)/name;out[p.relative_to(root).as_posix()]=state(p)
    require(len(out)<=1000,'outer path count bound')
    return out

require(not DEST.exists(),'fresh destination required')
require(shutil.disk_usage(WORK).free>1024**3,'local disk floor')
frozen=js(PREP/'LOCAL_PREPARATION_FROZEN.json')
prep_allow=set(frozen['files'])|set(frozen['localOnlyHistoricalFiles'])|set(frozen['preservedGuardAttempts'])|{'LOCAL_PREPARATION_FROZEN.json'}
for group in ('files','localOnlyHistoricalFiles','preservedGuardAttempts'):
    for name,expected in frozen[group].items():
        actual=state(PREP/name)
        require(all(actual[k]==expected[k] for k in ('bytes','sha256','mode')),'frozen preparation changed: '+name)
prep_inv=inventory(PREP,True)
require({n for n,s in prep_inv.items() if s['type']=='file'}==prep_allow,'preparation closure differs from frozen allowlist')
require(len(frozen['files'])==16,'expected sixteen stageable preparation files')
for attempt in ('units-r1','units-r2','units-r3'):
    e=js(UNIT_ROOT/attempt/'execution.json')
    require(e['completedAtUTC'] and e['sourceUnchanged'] and e['cancelled'] is None,'attempt not closed: '+attempt)
for name in ('java.execution.json','javac.execution.json'):
    require(js(HELPER/name)['exitCode']==0,'helper not completed successfully: '+name)
helper_reg=js(HELPER/'REGISTRATION.json')
for name,pin in helper_reg['inputPins'].items():
    b=read(Path(name));require(len(b)==pin['bytes'] and sha(b)==pin['sha256'],'helper input changed: '+name)
root_helper=RUNTIME/'WindowReleaseObservationV3.java'
require(read(root_helper)==read(HELPER/'WindowReleaseObservationV3.java'),'root helper differs from executed helper source')

groups={**{'units/'+a:UNIT_ROOT/a for a in ('units-r1','units-r2','units-r3')},'release-observation':HELPER,'cloud-preparation':PREP}
before={n:inventory(p,n=='cloud-preparation') for n,p in groups.items()}
require(sum(s.get('bytes',0) for inv in before.values() for s in inv.values())<128*1024*1024,'copy volume bound')
registration={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scriptSha256':sha(read(Path(__file__))),
              'sourceRoots':{n:str(p) for n,p in groups.items()},'sourceInventorySha256':{n:sha(json.dumps(v,sort_keys=True,separators=(',',':')).encode()) for n,v in before.items()},
              'destination':str(DEST),'freeBytesBefore':shutil.disk_usage(WORK).free,'scope':'Offline closed local preparation only; no running native tree, Java, Git, SSH, SQL, cloud or original-state inputs.'}
write(OWN/'REGISTRATION.json',registration)
DEST.mkdir(parents=True)
bindings=[]
for label,source in groups.items():
    target=DEST/label
    for name,expected in sorted(before[label].items(),key=lambda x:(x[0].count('/'),x[0])):
        src=source if name=='.' else source/name;dst=target if name=='.' else target/name
        if expected['type']=='directory': dst.mkdir(parents=True,exist_ok=True);os.chmod(dst,expected['mode'])
        else: shutil.copy2(src,dst)
        require(state(dst)==expected,'copy mismatch: '+str(dst))
        bindings.append({'source':str(src),'destination':str(dst.relative_to(DEST)),**expected})
    require(inventory(target)==before[label],'copied directory/empty-directory closure differs: '+label)
extra=DEST/'root-helper-source/WindowReleaseObservationV3.java';extra.parent.mkdir();shutil.copy2(root_helper,extra)
require(state(extra)==state(root_helper),'root helper copy mismatch')
bindings.append({'source':str(root_helper),'destination':str(extra.relative_to(DEST)),**state(extra),'identicalExecutedSource':True})

patterns={
 'private-key-header':re.compile(rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED) PRIVATE KEY-----'),
 'github-token':re.compile(rb'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b'),
 'aws-access-key-id':re.compile(rb'\bAKIA[A-Z0-9]{16}\b'),
 'runpod-token':re.compile(rb'\b(?:rpa|rp)_[A-Za-z0-9]{30,}\b'),
 'credential-dsn':re.compile(rb'(?i)(?:postgres(?:ql)?|mysql)://[^/\s:@]+:[^@\s]+@'),
}
scan={'filesAndArchiveMembers':0,'bytes':0,'hits':[],'scope':'Bounded known credential markers, not a general proof that arbitrary secrets are absent.'}
nested=[]
def markers(label,b):
    scan['filesAndArchiveMembers']+=1;scan['bytes']+=len(b);require(scan['bytes']<=MAX_SCAN,'credential scan byte bound')
    for kind,pattern in patterns.items():
        found=list(pattern.finditer(b))
        if found:scan['hits'].append({'path':label,'kind':kind,'count':len(found),'offsets':[m.start() for m in found[:16]]})
def archive(label,b,depth=0):
    require(depth<=2,'nested archive depth bound')
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        names=z.namelist();require(len(names)==len(set(names)) and len(names)<=10000,'ZIP entry closure: '+label)
        items=[]
        for x in z.infolist():
            p=PurePosixPath(x.filename);require(not p.is_absolute() and '..' not in p.parts,'unsafe ZIP member')
            mode=x.external_attr>>16;require(not stat.S_ISLNK(mode),'ZIP symlink refused')
            require(x.file_size<=MAX_FILE,'ZIP member byte bound')
            raw=z.read(x);require(len(raw)==x.file_size,'ZIP full-byte read')
            item={'path':x.filename,'type':'directory' if x.is_dir() else 'file','bytes':len(raw),'sha256':sha(raw),'mode':stat.S_IMODE(mode),'externalAttributes':x.external_attr,'createSystem':x.create_system,'crc32':x.CRC}
            items.append(item)
            if not x.is_dir():
                markers(label+'!/'+x.filename,raw)
                if x.filename.endswith(('.jar','.zip')):archive(label+'!/'+x.filename,raw,depth+1)
        nested.append({'path':label,'bytes':len(b),'sha256':sha(b),'entries':items,'entryCount':len(items),'explicitDirectoryCount':sum(x['type']=='directory' for x in items),'uidGidAvailable':False,'allBytesCrcAndSha256Read':True})
for p in sorted(DEST.rglob('*')):
    if p.is_file():
        b=read(p);label=p.relative_to(DEST).as_posix();markers(label,b)
        if p.suffix in ('.zip','.jar'):archive(label,b)

reports=[]
jar_states={}
for attempt in ('units-r1','units-r2','units-r3'):
    base=DEST/'units'/attempt;reg=js(base/'registration.json');execution=js(base/'execution.json');capture=js(base/'artifact-capture.json')
    require(sha(read(base/'source-before-run.zip'))==reg['sourceZipSha256'],'source ZIP SHA binding')
    require(sha(read(base/'run.py'))==reg['runnerSha256'] and sha(read(base/'capture-tests.gradle'))==reg['initScriptSha256'],'runner/init source SHA binding')
    require(sha(read(base/'gradle.log'))==execution['logSha256'],'execution log SHA binding')
    with zipfile.ZipFile(base/'source-before-run.zip') as z:
        require(set(z.namelist())==set(reg['sourceSha256']),'source ZIP registration closure')
        for name,h in reg['sourceSha256'].items(): require(sha(z.read(name))==h,'registered source SHA: '+name)
    actual_zip=base/'actual-classes-jars-results.zip';require(sha(read(actual_zip))==capture['archiveSha256'],'actual artifact ZIP SHA binding')
    with zipfile.ZipFile(actual_zip) as z:
        require(set(z.namelist())=={'actual/'+n.lstrip('/') for n in capture['files']},'actual artifact ZIP manifest closure')
        for name,pin in capture['files'].items():
            member='actual/'+name.lstrip('/');b=z.read(member);info=z.getinfo(member)
            require(len(b)==pin['bytes'] and sha(b)==pin['sha256'] and stat.S_IMODE(info.external_attr>>16)==pin['mode'],'actual ZIP member mismatch: '+name)
        cp_reports=[]
        for task in ('core','cluster'):
            cp=js(base/(task+'-test-classpath.json'))['actualClasspath'];files=0
            for path,pin in cp.items():
                entries={str(Path(path)/n):v for n,v in pin['files'].items()} if 'files' in pin else {path:pin}
                for name,expected in entries.items():
                    require(name in capture['files'],'configured test input absent from actual ZIP: '+name)
                    got=capture['files'][name];require(got['bytes']==expected['bytes'] and got['sha256']==expected['sha256'],'configured test input byte binding')
                    files+=1
            cp_reports.append({'task':task,'configuredClasspathEntries':len(cp),'fileBindings':files,'actualClassLoadOrderAttested':False})
        suites=[];total=failed=errors=skipped=0;failed_cases=[]
        for name in z.namelist():
            if '/test-results/test/TEST-' not in name or not name.endswith('.xml'):continue
            raw=z.read(name);suite=ET.fromstring(raw);cases=suite.findall('testcase');n=len(cases)
            f=sum(bool(c.findall('failure')) for c in cases);e=sum(bool(c.findall('error')) for c in cases);s=sum(bool(c.findall('skipped')) for c in cases)
            require(n==int(suite.attrib['tests']) and f==int(suite.attrib.get('failures',0)) and e==int(suite.attrib.get('errors',0)) and s==int(suite.attrib.get('skipped',0)),'actual XML count mismatch')
            total+=n;failed+=f;errors+=e;skipped+=s
            suites.append({'suite':suite.attrib['name'],'testcases':n,'failures':f,'errors':e,'skipped':s,'xmlSha256':sha(raw)})
            failed_cases += [{'suite':suite.attrib['name'],'name':c.attrib['name'],'message':((c.find('failure') if c.find('failure') is not None else c.find('error')).attrib.get('message',''))[:512]} for c in cases if c.findall('failure') or c.findall('error')]
        class_bindings=[]
        for module in ('core','cluster'):
            project=RUNTIME/'retention-window-v3-worktree';classroot=str(project/module/'build/classes/java/main')+'/'
            classes={name[len(classroot):]:pin['sha256'] for name,pin in capture['files'].items() if name.startswith(classroot) and name.endswith('.class')}
            candidates=[name for name in capture['files'] if name.endswith('/'+module+'/build/install/cluster/lib/'+module+'-0.1.0-SNAPSHOT.jar')]
            if module=='core': candidates=[name for name in capture['files'] if name.endswith('/cluster/build/install/cluster/lib/core-0.1.0-SNAPSHOT.jar')]
            if not candidates:
                class_bindings.append({'module':module,'capturedMainClassCount':len(classes),'installedJarPresent':False});continue
            require(len(candidates)==1,'ambiguous install JAR capture')
            jp=candidates[0];jar=z.read('actual/'+jp.lstrip('/'))
            with zipfile.ZipFile(io.BytesIO(jar)) as jz:jarclasses={n:sha(jz.read(n)) for n in jz.namelist() if n.endswith('.class')}
            different=[n for n in sorted(set(classes)|set(jarclasses)) if classes.get(n)!=jarclasses.get(n)]
            binding={'module':module,'capturedMainClassCount':len(classes),'installedJarPresent':True,'installedJarSha256':sha(jar),'installedJarClassCount':len(jarclasses),'allMainClassesMatchInstalledJar':not different,'differentOrMissingClassNames':different}
            class_bindings.append(binding);jar_states[(attempt,module)]=(sha(jar),jar)
            if attempt=='units-r3':require(not different,'final installed JAR/main class mismatch')
    require((execution['exitCode']==0)==(failed==errors==0),'execution and actual XML status mismatch')
    reports.append({'attempt':attempt,'execution':execution,'actualTestcases':total,'actualPassed':total-failed-errors-skipped,'actualFailures':failed,'actualErrors':errors,'actualSkipped':skipped,'suites':suites,'failedCases':failed_cases,'configuredTestInputBindings':cp_reports,'installedDistributionBindings':class_bindings,'sourceFileCount':len(reg['sourceSha256']),'sourceTreeLabel':reg['sourceTree']})
require(reports[-1]['actualTestcases']==133 and reports[-1]['actualPassed']==133,'final133 focused tests did not execute/pass')

observation=js(DEST/'release-observation/actual-distribution-observation.json')
digest=hashlib.sha256()
for row in observation['actualSources']:
    source=HELPER/'lib'/Path(row['path']).name;b=read(source)
    require(sha(b)==row['sha256'] and len(b)==row['bytes'],'actual helper source binding')
    digest.update(row['type'].encode());digest.update(b)
require(digest.hexdigest()==observation['codeFingerprint'],'actual loaded JAR code fingerprint mismatch')
require(observation['codeFingerprint']=='b148bbd416beca0c63ec10a2921a7709f1e82e8f3263604c930d5d901367117b','unexpected candidate code fingerprint')
for module in ('core','cluster'): require(jar_states[('units-r3',module)][0]==sha(read(HELPER/'lib'/(module+'-0.1.0-SNAPSHOT.jar'))),'helper/final installed JAR mismatch')
common1=dict(observation['plans']['1']);common8=dict(observation['plans']['8']);common1.pop('requestedReadWindow');common8.pop('requestedReadWindow');require(common1==common8,'common operational envelopes differ')
require(observation['codecShapeWitness']['encodedReplyBytes']==6727 and observation['codecShapeWitness']['genericSupportedMaximumBytes']==6919,'shape witness distinction changed')

changes=[]
for a,b in (('units-r1','units-r2'),('units-r2','units-r3')):
    x=js(DEST/'units'/a/'registration.json')['sourceSha256'];y=js(DEST/'units'/b/'registration.json')['sourceSha256']
    changed=[n for n in sorted(set(x)|set(y)) if x.get(n)!=y.get(n)]
    changes.append({'from':a,'to':b,'changedSourceFiles':changed,'changedProductionJavaFiles':[n for n in changed if '/src/main/java/' in n]})
guard_reports=[]
for folder in sorted((DEST/'cloud-preparation').glob('guards-attempt-*')):
    guard_reports.append({'attempt':folder.name,'completion':js(folder/'completion.json'),'completionSha256':sha(read(folder/'completion.json')),'stderrSha256':sha(read(folder/'stderr.txt'))})
for name,source in groups.items():require(inventory(source,name=='cloud-preparation')==before[name],'source changed while archiving: '+name)
require(read(root_helper)==read(extra),'root helper changed while archiving')

validation={'passed':True,'scope':'Closed local preparation/input/artifact validation only. No native workload result or cloud execution is included.',
 'unitAttempts':reports,'sourceChanges':changes,'pythonGuardAttempts':guard_reports,'frozenPrepSha256':sha(read(PREP/'LOCAL_PREPARATION_FROZEN.json')),
 'actualJarObservation':{'codeFingerprint':observation['codeFingerprint'],'actualSources':observation['actualSources'],'commonOperationalEnvelopesExact':True,'shapeReplyBytes':6727,'prospectivePlanLargestReplyBytes':observation['plans']['1']['largestReplyBytes'],'genericCodecSupportedMaxBytes':6919,'independentNativeNetworkObservation':False},
 'helperJdkPinsCurrentlyMatch':True,'helperJdkBinariesArchived':False,'testClasspathOrderOrActualLoadedSourcesIndependentlyAttested':False,
 'outerCopyClosureVerified':True,'sourceStatesUnchangedDuringCopy':True,'copyFiles':sum(x['type']=='file' for x in bindings),'copiedLogicalBytes':sum(x.get('bytes',0) for x in bindings),
 'excludedCompiledPycache':True,'pythonAttempt01OnlyHistoricalTranscriptSummary':frozen['priorAttempt01'],'freeBytesAfterCopies':shutil.disk_usage(WORK).free}
write(DEST/'COPY_BINDINGS.json',bindings);write(DEST/'VALIDATION.json',validation);write(DEST/'NESTED_ARCHIVE_INVENTORIES.json',nested)
tool=DEST/'tools/archive_local_proof.py';tool.parent.mkdir();shutil.copy2(Path(__file__),tool)
for path in (DEST/'COPY_BINDINGS.json',DEST/'VALIDATION.json',DEST/'NESTED_ARCHIVE_INVENTORIES.json',tool):markers(path.relative_to(DEST).as_posix(),read(path))
scan.update(passed=not scan['hits'],manualReviewRequired=bool(scan['hits']),maximumScannedBytes=MAX_SCAN,selfReportExcluded=True)
write(DEST/'CREDENTIAL_MARKER_REVIEW.json',scan)
write(OWN/'COMPLETION.json',{'passed':True,'destination':str(DEST),'copyFiles':validation['copyFiles'],'copiedLogicalBytes':validation['copiedLogicalBytes'],'actualTests':[{k:r[k] for k in ('attempt','actualTestcases','actualPassed','actualFailures','actualErrors','actualSkipped')} for r in reports],'markerHits':len(scan['hits']),'freeBytes':shutil.disk_usage(WORK).free})
print(json.dumps(js(OWN/'COMPLETION.json'),sort_keys=True))
