from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET,importlib.util,tarfile
b=Path(__file__).resolve().parent;s=b/'interbank-v4-worktree';d=b/'v4-sealed-owner-local-closure-r1';d.mkdir()
spec=importlib.util.spec_from_file_location('scope_tar',b/'dispatch-capacity-scope-tar-preparation-r1/scope_tar.py');scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(scope)
assert scope.sha(b/'dispatch-capacity-scope-tar-preparation-r1/scope_tar.py')=='e37566983b9dff56203344441103bae901d4196a783f5c2fc4141d5c82ef3759'
xmls=sorted((s/'cluster/build/test-results/test').glob('TEST-*.xml'));counts={k:sum(int(ET.parse(p).getroot().get(k,'0')) for p in xmls)for k in ['tests','failures','errors','skipped']}
assert len(xmls)==12 and counts==dict(tests=75,failures=0,errors=0,skipped=0),(len(xmls),counts)
for p in xmls:shutil.copy2(p,d/p.name)
roots=sorted((s/'cluster/build/sealed-read-native-attempts').iterdir());assert len(roots)==2
inventories={}
for root in roots:
 assert root.is_dir() and json.loads((root/'completion.json').read_text())['passed'] and json.loads((root/'completion.json').read_text())['allOwnedStopped']
 route=json.loads((root/'sealed-read-selection.json').read_text())['readRoute'];assert route in ['CLUSTER','DIRECT_UDP'] and route not in inventories
 inventories[route]=scope.tree(root)
 archive=d/(route.lower()+'-complete-original.tar.gz')
 with tarfile.open(archive,'w:gz',compresslevel=6)as t:t.add(root,arcname='original/'+route,recursive=True)
 proof=scope.verify(archive,{route:inventories[route]});assert scope.tree(root)==inventories[route]
 (d/(route.lower()+'-archive-verification.json')).write_text(json.dumps(proof,indent=2)+'\n')
 print(json.dumps(dict(route=route,compressedBytes=archive.stat().st_size,sha256=scope.sha(archive),proof=proof)),flush=True)
(d/'ORIGINAL_SCOPE_INVENTORIES.json').write_text(json.dumps(inventories,indent=2)+'\n')
for p in b.glob('v4-sealed-owner-local-r*.*'):shutil.copy2(p,d/p.name)
shutil.copytree(b/'v4-sealed-owner-compile-failure-r2',d/'compile-failure-r2')
shutil.copy2(__file__,d/'close.py')
paths=sorted(set(list((s/'cluster/src/main/java/io/vectormatch/cluster').glob('RetentionSealed*V4.java'))+list((s/'cluster/src/test/java/io/vectormatch/cluster').glob('RetentionSealed*V4Test.java'))+[s/'cluster/src/main/java/io/vectormatch/cluster'/n for n in ['RetentionNodeMainV3.java','RetentionBatchAeronTransportV3.java','RetentionAsyncAeronSmokeV4.java','RetentionClusteredServiceV3.java']]))
(d/'RESULT.json').write_text(json.dumps(dict(passed=True,testCounts=counts,newTests=69,legacyCacheTests=6,actualThreeJvmRoutes=['CLUSTER','DIRECT_UDP'],sameFinancialFinalStateWithinEachRun=True,allThreeSnapshotsAndColdRestore=True,notLatencyBenchmark=True,notFreshLinuxCIQualification=True,sourcePins=[dict(path=str(p.relative_to(s)),bytes=p.stat().st_size,sha256=scope.sha(p))for p in paths]),indent=2)+'\n')
e=s/'evidence/2026-10-26/runpod-cpu/v4-sealed-read-export-r1/local-owner-three-jvm-r1';shutil.copytree(d,e)
files=[dict(path=str(p.relative_to(e)),bytes=p.stat().st_size,sha256=scope.sha(p))for p in sorted(e.rglob('*'))if p.is_file()];assert max(x['bytes'] for x in files)<=10*1024*1024
(e/'FILE_INVENTORY.json').write_text(json.dumps(dict(files=files),indent=2)+'\n');print(json.dumps(dict(passed=True,evidence=str(e),counts=counts,files=len(files))),flush=True)
