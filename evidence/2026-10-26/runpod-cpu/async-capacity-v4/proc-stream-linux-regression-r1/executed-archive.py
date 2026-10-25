from pathlib import Path
import importlib.util,json,tarfile,xml.etree.ElementTree as E,datetime,shutil
B=Path(__file__).resolve().parent.parent;W=B/'async-maintenance-v4-worktree'
S=B/'dispatch-capacity-scope-tar-preparation-r1/scope_tar.py';spec=importlib.util.spec_from_file_location('scopes',S);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
O=W/'evidence/2026-10-26/runpod-cpu/async-capacity-v4/proc-stream-linux-regression-r1';assert not O.exists();O.mkdir()
ci=B/'production-ci-attempt-17-collection-r1';failed=[]
with tarfile.open(ci/'complete-code-compiled-tests-and-public-logs.tar.gz')as t:
 summary=json.load(t.extractfile('original/ci-results/SUMMARY.json'));assert summary['totals']==dict(tests=441,failures=13,errors=0,skipped=0)
 for member in t:
  if member.name.endswith('.xml')and'/test-results/'in member.name:
   x=E.parse(t.extractfile(member)).getroot()
   for case in x.findall('testcase'):
    fail=case.find('failure')
    if fail is not None:
     assert 'Expected two ephemeral port bounds'in fail.get('message','');failed.append(dict(suite=x.get('name'),test=case.get('name'),message=fail.get('message')))
assert len(failed)==13
local=B/'async-v4-proc-stream-local-tests-r1';assert json.loads((local/'RESULT.json').read_text())['passed']
x=E.parse(local/'junit/TEST-io.vectormatch.cluster.RetentionThreeJvmV3Test.xml').getroot();native=Path(next(line.split('VECTOR_V3_TEST_EVIDENCE ',1)[1]for line in x.find('system-out').text.splitlines()if line.startswith('VECTOR_V3_TEST_EVIDENCE '))).parent
linux=B/'async-v4-proc-stream-linux-qualification-r1';assert json.loads((linux/'EXECUTION.json').read_text())['exitCode']==0
scopes=dict(ci17=ci,diagnostic=B/'async-v4-ci17-proc-range-diagnostic-r1',local=local,native=native,linux=linux,localController=B/'async-v4-proc-stream-local-qualification-preparation-r1')
inventories={name:m.tree(path)for name,path in scopes.items()};archive=O/'complete-ci17-failure-and-proc-stream-qualification.tar.gz'
with tarfile.open(archive,'w:gz')as t:
 for name,path in scopes.items():t.add(path,arcname='original/'+name)
verified=m.verify(archive,inventories)
for name,path in scopes.items():assert m.tree(path)==inventories[name]
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),ci17Passed=False,ci17Source=summary['sourceCommit'],ci17RunId=40241337345,ci17JUnit=summary['totals'],failedTests=failed,ci17PythonFailoverWebNotExecuted=True,
 fixedSourceSha256=m.sha(W/'cluster/src/main/java/io/vectormatch/cluster/RetentionLoopbackPortsV4.java'),localJUnit=dict(tests=5,failures=0,errors=0,skipped=0),linuxDirectProbePassed=True,
 actualProcReadStringByteValues=[51],actualProcStreamByteValues=[51,50,55,54,56,9,54,48,57,57,57,10],fullLinuxCiStillRequired=True,noCapacityOrProductionClaim=True,archive=dict(bytes=archive.stat().st_size,sha256=m.sha(archive)),memberVerification=verified)
(O/'ORIGINAL_SCOPE_INVENTORIES.json').write_text(json.dumps(inventories,indent=2,sort_keys=True)+'\n');(O/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
shutil.copy2(__file__,O/'executed-archive.py');shutil.copy2(S,O/'scope_tar.py')
(O/'README.md').write_text('# Linux procfs port-range regression\n\nCI17 failed 13 of 441 Java tests before those tests could start their cluster: the JDK readString path returned only byte 51 from a zero-size procfs file. The unchanged failure record is preserved. The fix uses a bounded stream read. Five local tests and the direct Linux source probe pass; complete Linux CI remains required before any new capacity test. No latency, production or funded-trading certification.\n')
print(json.dumps(dict(passed=True,archiveBytes=archive.stat().st_size,originalFiles=verified['originalFiles'],package=str(O))))
