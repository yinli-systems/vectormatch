from pathlib import Path
import json,hashlib,shutil,ast,difflib
B=Path(__file__).resolve().parent.parent;P=Path(__file__).resolve().parent;S=B/'cpu-read-window32-cloud-preparation-r2';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
shutil.copytree(S,P/'baseline');f=json.loads((S/'LOCAL_PREPARATION_FROZEN.json').read_text())
for name in f['files']:
 q=P/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(S/name,q)
for n in ['release.template.json','run_source_guards.py']:shutil.copy2(S/n,P/n)
oldroot='/opt/vectormatch-cpu/preparation/cpu-read-window32-cloud-abab-r1';newroot='/opt/vectormatch-cpu/experiments/read-window32-current-abab-r1'
for q in P.rglob('*'):
 if not q.is_file() or q.is_relative_to(P/'baseline') or q.name=='adapt.py' or q.suffix not in ['.json','.py']:continue
 text=q.read_text();q.write_text(text.replace(oldroot,newroot).replace('ed6c0673f5cb','33ace3d92505'))
raw=B/'current-cpu-metadata-execution-r1';ob=(raw/'actual-linux-observation.json').read_bytes();response=json.loads((raw/'ssh.stdout.json').read_text());receipt={k:v for k,v in response.items() if not k.endswith('Base64')}
(P/'fixtures/actual-linux-distribution-observation.json').write_bytes(ob);(P/'fixtures/remote-receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
actual=json.loads((B/'current-cpu-baseline-preparation-r1/baseline.json').read_text());assert actual['absentProtectedPaths'][-1]==newroot
manifest=dict(actual);manifest['initialSyntheticNamespaceObservedAbsent']=manifest['absentProtectedPaths'].pop();manifest['observationSourceSha256']=sha(B/'current-cpu-baseline-preparation-r1/baseline.json');(P/'current-container-baseline.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n');protected_sha=sha(P/'current-container-baseline.json')
q=P/'cpu_read_window32_abab.py';text=q.read_text();lines=text.splitlines(True)
for i,line in enumerate(lines):
 if line.startswith('PREREQUISITE_PINS = '):lines[i]='PREREQUISITE_PINS = '+repr({k:dict(bytes=(P/'fixtures'/n).stat().st_size,sha256=sha(P/'fixtures'/n))for k,n in [('linuxMetadataObservation','actual-linux-distribution-observation.json'),('linuxMetadataReceipt','remote-receipt.json')]})+'\n'
text=''.join(lines).replace('/opt/vectormatch-cpu/preparation/cpu-read-window32-release-metadata-r1','/opt/vectormatch-cpu/tools/cpu-read-window32-current-container-metadata-r1').replace('6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753',protected_sha)
node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)and n.name=='protected_state');lines=text.splitlines(True)
new='''def validate_current_container_baseline(manifest, *, host, boot_id, affinity, cpu_max, memory_max, absent_paths):
    require(manifest['schemaVersion']==1 and manifest['scope']=='CURRENT_CPU_CONTAINER_ABSENT_OLD_STATE_AND_FRESH_SYNTHETIC_NAMESPACE', 'Explicit fresh-container absence baseline required')
    require(manifest['host']==host==HOST and manifest['bootId']==boot_id, 'Host/container boot identity changed')
    expected=[str(ROOT/'restorations/original-native-r1'),str(ROOT/'preparation')]
    require(manifest['absentProtectedPaths']==expected and absent_paths==expected, 'Old restoration/preparation appeared; preserve and requalify')
    require(manifest['initialSyntheticNamespaceObservedAbsent']==str(PREP) and manifest['old57AndPg989RestorationClaimed'] is False and manifest['newSyntheticNamespaceOnly'] is True, 'Do not inherit old57/PG989 state')
    require(manifest['affinity']==affinity and len(affinity)==32 and manifest['cpuMax']==cpu_max and manifest['memoryMax']==memory_max, 'CPU affinity or cgroup budget changed')
    return True

def protected_state(base, release):
    row=release['protectedOriginalState'];path=Path(row['manifest']);base.no_links(path)
    require(digest(path)==row['manifestSha256'], 'Current-container baseline body differs')
    manifest=json_bounded(base,path,4*1024**2);absent=[]
    for name in manifest['absentProtectedPaths']:
        p=Path(name);base.no_links(p)
        require(not p.exists(), 'Unexpected old-state tree must be preserved: '+name);absent.append(name)
    validate_current_container_baseline(manifest,host=socket.gethostname(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),affinity=sorted(os.sched_getaffinity(0)),cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text(),memory_max=Path('/sys/fs/cgroup/memory.max').read_text(),absent_paths=absent)
    return dict(passed=True,manifestSha256=row['manifestSha256'],scope=manifest['scope'],host=manifest['host'],bootId=manifest['bootId'],absentProtectedPaths=absent,old57AndPg989RestorationClaimed=False,newSyntheticNamespaceOnly=True)
'''
text=''.join(lines[:node.lineno-1])+new+'\n'+''.join(lines[node.end_lineno:]);q.write_text(text)
r=json.loads((P/'release.template.json').read_text());r['host']='33ace3d92505';r['protectedOriginalState']['manifestSha256']=protected_sha
for key,n in [('linuxMetadataObservation','actual-linux-distribution-observation.json'),('linuxMetadataReceipt','remote-receipt.json')]:r['evidenceReferences'][key].update(bytes=(P/'fixtures'/n).stat().st_size,sha256=sha(P/'fixtures'/n))
(P/'release.template.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
t=P/'test_read_window32_delta.py';t.write_text(t.read_text().replace("'strict_idle','protected_state','clean_all'","'strict_idle','clean_all'"))
(P/'SOURCE_DIFF.patch').write_text(''.join(difflib.unified_diff((S/'cpu_read_window32_abab.py').read_text().splitlines(True),q.read_text().splitlines(True),fromfile='old-container/controller',tofile='current-container/controller')))
(P/'REBINDING.json').write_text(json.dumps(dict(sourceOnly=True,oldControllerSha256=sha(S/'cpu_read_window32_abab.py'),newControllerSha256=sha(q),actualNewMetadataSha256=sha(P/'fixtures/actual-linux-distribution-observation.json'),actualNewMetadataReceiptSha256=sha(P/'fixtures/remote-receipt.json'),freshAbsenceBaselineSha256=protected_sha,old57Pg989NotAssumed=True,foreignJavaStillRejected=True,gradleMustExitNaturally=True,nativeNotExecuted=True),indent=2,sort_keys=True)+'\n')
print('adapted',sha(q))
