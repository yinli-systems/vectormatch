from pathlib import Path
import json,shutil,importlib.util,tarfile,re,xml.etree.ElementTree as ET
b=Path(__file__).resolve().parent;s=b/'interbank-v4-worktree';d=b/'v4-sealed-capacity-source-closure-r1';d.mkdir()
spec=importlib.util.spec_from_file_location('scope',b/'dispatch-capacity-scope-tar-preparation-r1/scope_tar.py');scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(scope)
spec=importlib.util.spec_from_file_location('route',s/'scripts/verify_sealed_read_route.py');route=importlib.util.module_from_spec(spec);spec.loader.exec_module(route)
xml=b/'v4-sealed-capacity-local-validation-r2/TEST-io.vectormatch.cluster.RetentionSealedThreeJvmV4Test.xml';r=ET.parse(xml).getroot();assert int(r.get('tests'))==2 and int(r.get('failures'))==0
roots=[Path(x.strip())for x in re.findall(r'VECTOR_SEALED_THREE_JVM_TEST_EVIDENCE ([^\n]+)',''.join(r.itertext()))];assert len(roots)==2
inventories={};proofs=[]
for root in roots:
 mode=json.loads((root/'sealed-read-selection.json').read_text())['readRoute'];proof=route.verify(root,mode);assert proof['passed'];proofs.append(proof)
 assert json.loads((root/'completion.json').read_text())['allOwnedStopped']
 inventory=scope.tree(root);inventories[mode]=inventory;archive=d/(mode.lower()+'-complete-original.tar.gz')
 with tarfile.open(archive,'w:gz',compresslevel=6)as t:t.add(root,arcname='original/'+mode)
 reviewed=scope.verify(archive,{mode:inventory});assert scope.tree(root)==inventory
 (d/(mode.lower()+'-archive-and-route-verification.json')).write_text(json.dumps(dict(route=proof,archive=reviewed,archiveBytes=archive.stat().st_size,archiveSha256=scope.sha(archive)),indent=2)+'\n')
(d/'ORIGINAL_SCOPE_INVENTORIES.json').write_text(json.dumps(inventories,indent=2)+'\n')
shutil.copytree(b/'v4-sealed-capacity-local-validation-r2',d/'local-suite-including-disk-admission-refusal')
for name in ['verify_sealed_read_route.py','test_verify_sealed_read_route.py']:shutil.copy2(s/'scripts'/name,d/name)
shutil.copy2(__file__,d/'close.py')
source=[*sorted((s/'core/src/main/java').rglob('*.java')),*sorted((s/'cluster/src/main/java').rglob('*.java')),*sorted((s/'cluster/src/test/java').glob('io/vectormatch/cluster/RetentionSealed*Test.java'))]
(d/'RESULT.json').write_text(json.dumps(dict(overallLocalSuitePassed=False,tests=83,failures=1,errors=0,skipped=0,onlyFailure='Existing capacity experiment initialFreeBytes admission refused on local disk;no threshold changed',bothActualThreeJvmFinancialReplaySnapshotColdRestorePassed=True,bothIndependentRouteAuditsPassed=True,noCapacityMeasurement=True,noFreshLinuxCIQualification=True,sourcePins=[dict(path=str(p.relative_to(s)),bytes=p.stat().st_size,sha256=scope.sha(p))for p in source]),indent=2)+'\n')
e=s/'evidence/2026-10-26/runpod-cpu/v4-sealed-read-export-r1/local-capacity-adapter-r1';shutil.copytree(d,e)
files=[dict(path=str(p.relative_to(e)),bytes=p.stat().st_size,sha256=scope.sha(p))for p in sorted(e.rglob('*'))if p.is_file()];assert max(x['bytes']for x in files)<10*1024*1024
(e/'FILE_INVENTORY.json').write_text(json.dumps(dict(files=files),indent=2)+'\n');print(json.dumps(dict(closed=True,files=len(files),proofs=proofs)),flush=True)
