from pathlib import Path
import sys,json,tarfile,shutil,datetime,subprocess
B=Path(__file__).resolve().parent.parent;W=B/'interbank-v4-worktree';sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import tree,verify,sha
A=W/'evidence/2026-10-26/runpod-cpu/interbank-dispatch-v4/local-qualification-r1';assert not A.exists();A.mkdir(parents=True)
r=json.loads((B/'interbank-local-qualification-r6/RESULT.json').read_text());assert r==dict(exitCode=0,tests=29,failures=0,errors=0,skipped=0,suites=6)
log=(B/'interbank-local-qualification-r6/python-tests-final.stderr').read_text();assert 'Ran 202 tests' in log and 'OK (skipped=4)' in log
names=[f'interbank-local-qualification-r{n}'for n in range(1,7)]+['exact-cut-runtime-cache-retirement-preparation-r2','exact-cut-runtime-cache-retirement-r2','completed-ci-jdk-cache-retirement-preparation-r3','completed-ci-jdk-cache-retirement-r3','v4-owner-poll-report-private-proof-r1']
scopes={n:B/n for n in names};inv={n:tree(p)for n,p in scopes.items()};archive=A/'complete-local-qualification-and-workspace-maintenance.tar.gz'
with tarfile.open(archive,'x:gz')as t:
 for n,p in scopes.items():t.add(p,arcname='original/'+n)
review=verify(archive,inv)
def write(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
write(A/'ORIGINAL_SCOPE_INVENTORIES.json',inv);shutil.copy2(__file__,A/'publish.py')
paths=subprocess.check_output(['git','-C',str(W),'diff','--name-only'],text=True).splitlines()+['cluster/src/main/java/io/vectormatch/cluster/RetentionReadYieldPolicyV4.java','cluster/src/test/java/io/vectormatch/cluster/RetentionReadYieldPolicyV4Test.java','scripts/retention_read_yield_audit_v4.py','scripts/tests/test_retention_read_yield_audit_v4.py','docs/INTERBANK_DISPATCH_V4.md']
source=A/'qualified-sources';source.mkdir();pins={}
for name in paths:
 p=W/name;target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);pins[name]=dict(bytes=p.stat().st_size,sha256=sha(p))
write(A/'SOURCE_PINS.json',pins)
(A/'README.md').write_text('# Local inter-bank candidate qualification\n\n29 Java tests across six suites pass with zero failure/error/skip. Both original20-second arrival-clock fixtures are included. The complete Python suite has202 tests,198 pass and four actual Linux-only process/signal cases skip on macOS;all historical fixture checks pass. Linux regression,native candidate audit/cold recovery and controlled performance comparisons remain pending. No default/performance promotion.\n\nAll six local attempts and exact qualified sources are preserved. Test fixture/exception-name/semantic errors and the actual disk refusal are retained;runtime guards are unchanged. Full compressed closed native archives remain on CPU/local/private assets after retiring only fully verified uncompressed runtime duplicates. Cleanup R2 verified20 scopes before deleting their duplicate state directories and preserved every compressed archive. The JDK cache retirement label still says17 originals,while its executed selection actually checks all18 closed CI archives;the raw record is unchanged. Main HTTP evidence has103 runs/38 cohorts.\n')
write(A/'INVENTORY.json',tree(A));write(A/'CLOSED.json',dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=sha(A/'INVENTORY.json'),archiveBytes=archive.stat().st_size,archiveSha256=sha(archive),everyOriginalMemberVerified=review,javaTests=29,pythonTests=202,pythonMacSkips=4,linuxAndNativePending=True,performanceClaim=False))
print(json.dumps(dict(passed=True,originalFiles=review['originalFiles'],archiveBytes=archive.stat().st_size,qualifiedSourceFiles=len(pins))))
