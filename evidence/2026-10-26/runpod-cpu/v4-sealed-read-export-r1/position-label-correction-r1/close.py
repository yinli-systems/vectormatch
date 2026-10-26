from pathlib import Path
import json,hashlib,shutil,importlib.util,tarfile,xml.etree.ElementTree as ET,re
B=Path(__file__).resolve().parent;S=B/'interbank-v4-worktree';E=S/'evidence/2026-10-26/runpod-cpu/v4-sealed-read-export-r1/position-label-correction-r1';assert not E.exists();E.mkdir()
s=importlib.util.spec_from_file_location('scope',B/'dispatch-capacity-scope-tar-preparation-r1/scope_tar.py');scope=importlib.util.module_from_spec(s);s.loader.exec_module(scope)
xml=S/'cluster/build/test-results/test/TEST-io.vectormatch.cluster.RetentionSealedThreeJvmV4Test.xml';suite=ET.parse(xml).getroot();assert int(suite.get('tests'))==2 and int(suite.get('failures'))==0
proof=json.loads((B/'v4-sealed-position-label-route-r1.stdout').read_text());assert proof['passed']
roots=[Path(x.strip())for x in re.findall(r'VECTOR_SEALED_THREE_JVM_TEST_EVIDENCE ([^\n]+)',''.join(suite.itertext()))];assert len(roots)==2
inventories={}
for root in roots:
 mode=json.loads((root/'sealed-read-selection.json').read_text())['readRoute'];assert mode not in inventories and json.loads((root/'completion.json').read_text())['allOwnedStopped'];inventories[mode]=scope.tree(root)
archive=E/'complete-corrected-both-three-jvm-originals.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=6)as t:
 for root in roots:t.add(root,arcname='original/'+json.loads((root/'sealed-read-selection.json').read_text())['readRoute'])
review=scope.verify(archive,inventories);assert all(scope.tree(root)==inventories[json.loads((root/'sealed-read-selection.json').read_text())['readRoute']]for root in roots)
(E/'ORIGINAL_SCOPE_INVENTORIES.json').write_text(json.dumps(inventories,indent=2)+'\n');shutil.copy2(xml,E/xml.name)
for pattern in ['v4-sealed-position-label-native-r1.*','v4-sealed-position-label-python-r*.*','v4-sealed-position-label-route-r1.*']:
 for p in B.glob(pattern):shutil.copy2(p,E/p.name)
shutil.copy2(__file__,E/'close.py')
source=['cluster/src/main/java/io/vectormatch/cluster/RetentionSealedOwnerTransportV4.java','scripts/verify_sealed_read_route.py','scripts/tests/test_verify_sealed_read_route.py']
(E/'RESULT.json').write_text(json.dumps(dict(passed=True,measurementOnlyCorrection=True,actualThreeJvmTests=2,pythonUnitTests=5,bothOriginalRouteAudits=proof,fullOriginalArchive=review,sourcePins=[dict(path=p,sha256=scope.sha(S/p))for p in source],ci25OldLabelPreservedAndSuperseded=True,noCapacityPointEverRunForOldLabel=True,newFullLinuxQualificationRequired=True,primarySource='https://raw.githubusercontent.com/aeron-io/aeron/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/client/AeronCluster.java'),indent=2)+'\n')
(E/'FILE_INVENTORY.json').write_text(json.dumps(dict(files=[dict(path=str(p.relative_to(E)),bytes=p.stat().st_size,sha256=scope.sha(p))for p in sorted(E.rglob('*'))if p.is_file()]),indent=2)+'\n');print(json.dumps(dict(passed=True,archiveBytes=archive.stat().st_size,scope=review)),flush=True)
E=S/'evidence/2026-10-26/runpod-cpu/v4-sealed-read-export-r1/ci25-validation-superseded-position-label-r1';assert not E.exists();E.mkdir()
for name in ['production-ci-attempt-25-collection-r1','v4-sealed-ci-native-collection-r1','v4-sealed-forced-correctness-r1','v4-sealed-linux-metadata-execution-r1']:shutil.copytree(B/name,E/name)
for name in ['JAR_INPUTS.json','JDK_IMAGE_EQUIVALENCE.json','JDK_REGISTRATION.json','JDK_EXECUTION.json','jdk.stdout.json','jdk.stderr']:shutil.copy2(B/'v4-sealed-artifact-preparation-r1'/name,E/name)
(E/'MEASUREMENT_LABEL_NOTE.json').write_text(json.dumps(dict(ciPassed=True,sourceCommit='d1b222bc58361071d131c7abcc5358b85b4d8c18',ciRun=40267396741,javaTests=544,pythonTests=206,postgresTests=11,zeroFailuresErrorsSkips=True,originalScopeInventoriesUnchanged=True,notCapacityEvidence=True,notQualificationOfCorrectedSource=True,supersededField='ROUTED_OFFER.clusterLogPosition was true on CLUSTER route;actual code was ingress Publication.offer result;all originals retained'),indent=2)+'\n')
files=[dict(path=str(p.relative_to(E)),bytes=p.stat().st_size,sha256=scope.sha(p))for p in sorted(E.rglob('*'))if p.is_file()];assert max(x['bytes']for x in files)<10*1024*1024
(E/'FILE_INVENTORY.json').write_text(json.dumps(dict(files=files),indent=2)+'\n');print(json.dumps(dict(ci25Archived=True,files=len(files))),flush=True)
