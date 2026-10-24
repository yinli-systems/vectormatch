from pathlib import Path
import json,hashlib,shutil,ast,difflib
P=Path(__file__).resolve().parent;B=P.parent;S=B/'cpu-read-window32-collection-preparation-r1';C=B/'current-read-window32-controller-preparation-r1';sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
shutil.copytree(S,P/'baseline')
for q in S.glob('*.py'):shutil.copy2(q,P/q.name)
for name in ['fixtures','long_parser']:shutil.copytree(S/name,P/name)
oldroot='/opt/vectormatch-cpu/preparation/cpu-read-window32-cloud-abab-r1';newroot='/opt/vectormatch-cpu/experiments/read-window32-current-abab-r1';oldf='3c08ef18ecb9599ccce4a7e6d03c8afeea760cdf66297f422520e5708ec1a9f0';newf=sha(C/'LOCAL_PREPARATION_FROZEN_R2.json')
for q in list(P.glob('*.py'))+list((P/'fixtures').glob('*.json')):
 if q.name=='adapt.py':continue
 q.write_text(q.read_text().replace(oldroot,newroot).replace('ed6c0673f5cb','33ace3d92505').replace(oldf,newf).replace('current-stopped-original-state.json','current-container-baseline.json'))
for name in ['cpu_read_window32_abab.py','idle_attestation.py','owner_poll_attestation.py','owned_linux_base_8eeb.py','shutdown_warning.py']:shutil.copy2(C/name,P/name)
shutil.copy2(C/'LOCAL_PREPARATION_FROZEN_R2.json',P/'controller-preparation-frozen.json')
for name in ['actual-linux-distribution-observation.json','actual-local-distribution-observation.json']:shutil.copy2(C/'fixtures'/name,P/'fixtures'/name)
shutil.copy2(C/'release.template.json',P/'fixtures/release.template.json')
remote=(B/'remote.py').read_text().replace('PORT=13658','PORT=40184').replace("EXPECTED_HOSTNAME='ed6c0673f5cb'","EXPECTED_HOSTNAME='33ace3d92505'")
remote=remote.replace("'-o','StrictHostKeyChecking=yes',", "'-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=\\\"'+str(BASE.parent/'current-cpu-connection-r1/known_hosts')+'\\\"',")
(P/'remote_current.py').write_text(remote);remote_sha=sha(P/'remote_current.py')
q=P/'collect_and_audit.py';q.write_text(q.read_text().replace('0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73',remote_sha))
protected_sha=sha(C/'current-container-baseline.json');close=(B/'cpu-read-window32-close-preparation-r1/inspect_closed_read_window32_arm.py').read_text().replace(oldroot,newroot).replace('ed6c0673f5cb','33ace3d92505').replace('6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753',protected_sha).replace('d0dbd4c5051ab328e94102e151382d358aa1c5dee115fbc991ad2e0d41fe8c04',sha(C/'cpu_read_window32_abab.py'))
old="sum(v['files'] for v in protected['nativeTrees'])==57 and protected['postgres']['files']==989";new="protected['scope']=='CURRENT_CPU_CONTAINER_ABSENT_OLD_STATE_AND_FRESH_SYNTHETIC_NAMESPACE' and protected['host']=='33ace3d92505' and protected['bootId']=='8d765c71-dbfa-4354-8db0-6c392e701e6f' and protected['absentProtectedPaths']==['/opt/vectormatch-cpu/restorations/original-native-r1','/opt/vectormatch-cpu/preparation'] and protected['old57AndPg989RestorationClaimed'] is False";assert old in close;close=close.replace(old,new).replace("'protectedNative57Pg989ReceiptsExact':True","'protectedCurrentContainerAbsenceReceiptsExact':True").replace('protected57/PG989 receipt','current-container absence baseline receipt')
(P/'inspect_closed_current_read32.py').write_text(close);q=P/'collect_and_audit.py';q.write_text(q.read_text().replace('9aaa3d135b735ef0d5ef159ef295d50743096501219c45b1f9300eea806c3b2a',sha(P/'inspect_closed_current_read32.py')))
q=P/'audit_native_artifacts.py';text=q.read_text();start=text.index("    for x,y in zip(protected['nativeTrees']");end=text.index('    for key,previous in c[\'priorGates\']',start)
replacement='''    require(protected==original,'Actual collected current-container baseline body differs')
    validate_absence_protection(protected,before['protectedOriginal'],after['protectedOriginal'],sha(protected_path))
''';text=text[:start]+replacement+text[end:];text=text.replace("'protectedNativeFiles':sum(len(x['files']) for x in protected['nativeTrees']),'protectedPgFiles':after['protectedOriginal']['postgres']['files']", "'old57AndPg989RestorationClaimed':False,'protectedCurrentContainerAbsenceReceiptsExact':True").replace('Full protected-original checks performed by wrapper before/after','Fresh-container absence/boot/cgroup protection checks performed by wrapper before/after')
insert='''def validate_absence_protection(manifest,before,after,manifest_sha):
    require(before==after and before['passed'] is True and before['manifestSha256']==manifest_sha,'Exact before/after current-container baseline receipt required')
    require(manifest['scope']==before['scope']=='CURRENT_CPU_CONTAINER_ABSENT_OLD_STATE_AND_FRESH_SYNTHETIC_NAMESPACE' and before['host']==manifest['host']=='33ace3d92505' and before['bootId']==manifest['bootId']=='8d765c71-dbfa-4354-8db0-6c392e701e6f','Current host/boot scope differs')
    expected=['/opt/vectormatch-cpu/restorations/original-native-r1','/opt/vectormatch-cpu/preparation']
    require(before['absentProtectedPaths']==manifest['absentProtectedPaths']==expected and before['old57AndPg989RestorationClaimed'] is False and manifest['old57AndPg989RestorationClaimed'] is False and manifest['newSyntheticNamespaceOnly'] is True,'Cannot inherit original57/PG989 or omit protected absent roots')
    return True

''';text=text.replace('def audit(a,c,release):',insert+'def audit(a,c,release):');q.write_text(text)
(P/'SOURCE_DIFF.patch').write_text(''.join(''.join(difflib.unified_diff((S/n).read_text().splitlines(True),(P/n).read_text().splitlines(True),fromfile='old-container/'+n,tofile='current-container/'+n))for n in ['common.py','audit_native_artifacts.py','collect_and_audit.py','build_config.py']))
print('remote_sha',remote_sha,'close_sha',sha(P/'inspect_closed_current_read32.py'))
