"""Seal already-tested source/fixture history only; no remote or process probes."""
from pathlib import Path
import ast,datetime,difflib,hashlib,json,stat
HERE=Path(__file__).resolve().parent;BASE=HERE.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def row(p):
 s=p.lstat();assert stat.S_ISREG(s.st_mode)and not p.is_symlink();return dict(bytes=s.st_size,sha256=sha(p),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
def save(p,v):
 with p.open('x')as f:json.dump(v,f,sort_keys=True,indent=2);f.write('\n')
original=BASE/'cpu-event-fetch-close-preparation-r1';baseline=HERE/'baseline'
source_rows={str(p.relative_to(original)):row(p)for p in original.rglob('*')if p.is_file()}
assert source_rows=={str(p.relative_to(baseline)):row(p)for p in baseline.rglob('*')if p.is_file()}
save(HERE/'BASELINE_PROVENANCE.json',dict(original=str(original),files=source_rows,fullOriginalTreeCopiedWithoutExclusions=True))
old=ast.parse((baseline/'inspect_closed_event_arm.py').read_text());new=ast.parse((HERE/'inspect_closed_read_window32_arm.py').read_text())
def functions(tree):return {n.name:ast.dump(n,include_attributes=False)for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
a,b=functions(old),functions(new);unchanged=[n for n in a if a[n]==b.get(n)]
assert {'require','argv_sha','bounded','js','process','identity_state','live_jvm_pg','expected_node'}<=set(unchanged)
save(HERE/'UNCHANGED_FUNCTION_AST_BINDINGS.json',dict(unchangedDefinitions=unchanged,originalSourceSha256=sha(baseline/'inspect_closed_event_arm.py'),newSourceSha256=sha(HERE/'inspect_closed_read_window32_arm.py'),processIdentityAndBoundedReadFunctionsUnchanged=True))
diff=''.join(difflib.unified_diff((baseline/'inspect_closed_event_arm.py').read_text().splitlines(True),(HERE/'inspect_closed_read_window32_arm.py').read_text().splitlines(True),fromfile='baseline/inspect_closed_event_arm.py',tofile='inspect_closed_read_window32_arm.py'))
diff+=''.join(difflib.unified_diff((baseline/'test_inspect_closed_event_arm.py').read_text().splitlines(True),(HERE/'test_inspect_closed_read_window32_arm.py').read_text().splitlines(True),fromfile='baseline/test_inspect_closed_event_arm.py',tofile='test_inspect_closed_read_window32_arm.py'))
(HERE/'SOURCE_DIFF.patch').open('x').write(diff)
completion=json.loads((HERE/'guards-r1/completion.json').read_text());assert completion['passed']and completion['actualTestsRun']==20 and completion['allInputSourcesUnchanged']
source=HERE/'inspect_closed_read_window32_arm.py';assert '__NEW_CONTROLLER_SHA__'not in source.read_text()
active={str(p.relative_to(HERE)):row(p)for p in HERE.rglob('*')if p.is_file()and'baseline'not in p.relative_to(HERE).parts}
save(HERE/'SOURCE_FROZEN.json',dict(schemaVersion=1,scope='CPU_READ_WINDOW32_CLOSED_CONTROL_PLANE_PROBE_SOURCE',sourceCommit='605eb43fcafd8fa0a6287304387c93c4d1bbddf6',controllerSha256='d0dbd4c5051ab328e94102e151382d358aa1c5dee115fbc991ad2e0d41fe8c04',controllerPreparationSha256='3c08ef18ecb9599ccce4a7e6d03c8afeea760cdf66297f422520e5708ec1a9f0',executedSourceSha256=sha(source),sourceFiles=active,baselineSourceFiles={'baseline/'+n:r for n,r in source_rows.items()},guardsCompletionSha256=sha(HERE/'guards-r1/completion.json'),actualPureGuards20=True,closedControllerGateScope='ROOT_VERIFIED_CLOSED_CPU_READ_WINDOW32_CONTROLLER',closedControllerGateSchemaVersion=3,actualRemoteExecutionPerformed=False,performanceClaimed=False))
files={str(p.relative_to(HERE)):row(p)for p in HERE.rglob('*')if p.is_file()};dirs={}
for p in[HERE]+sorted(HERE.rglob('*')):
 assert not p.is_symlink()
 if p.is_dir():s=p.stat();dirs[str(p.relative_to(HERE))]=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
save(HERE/'INVENTORY.json',dict(schemaVersion=1,files=files,directories=dirs,payloadFiles=len(files),payloadBytes=sum(r['bytes']for r in files.values())))
save(HERE/'CLOSED.json',dict(schemaVersion=1,passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='CLOSED_SOURCE_ONLY_READ_WINDOW32_CONTROL_PLANE_PROBE',inventorySha256=sha(HERE/'INVENTORY.json'),sourceFrozenSha256=sha(HERE/'SOURCE_FROZEN.json'),executedSourceSha256=sha(source),pureSyntheticGuards=20,fullBaselineUnchanged=True,noSshJvmGitRealProcessOrRawAuditExecuted=True,rootIndependentReviewRequired=True))
print(json.dumps(dict(passed=True,sourceSha256=sha(source),freezeSha256=sha(HERE/'SOURCE_FROZEN.json'),closedSha256=sha(HERE/'CLOSED.json'),payloadFiles=len(files),directories=len(dirs))))
