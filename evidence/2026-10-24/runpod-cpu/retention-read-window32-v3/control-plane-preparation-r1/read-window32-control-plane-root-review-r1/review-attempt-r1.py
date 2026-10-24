from pathlib import Path
import json,hashlib,stat,ast,zipfile,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();load=lambda p:json.loads(p.read_text())
def funcs(p):return{n.name:ast.dump(n,include_attributes=False)for n in ast.parse(p.read_text()).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
def closure(p):
 i=load(p/'INVENTORY.json');c=load(p/'CLOSED.json');f={};dirs={}
 for q in[p,*sorted(p.rglob('*'))]:
  assert not q.is_symlink();s=q.stat();n=q.relative_to(p).as_posix();m=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
  if q.is_dir():dirs[n]=m
  elif n not in['INVENTORY.json','CLOSED.json']:f[n]=dict(m,bytes=s.st_size,sha256=sha(q))
 assert f==i['files'] and sha(p/'INVENTORY.json')==c['inventorySha256']
 if isinstance(i['directories'],list):
  exp={r['path']:{k:v for k,v in r.items()if k not in['path','empty']}for r in i['directories']};assert{n:r for n,r in dirs.items()if n!='.'}==exp
  for r in i['directories']:assert r['empty']==(not any((p/r['path']).iterdir()))
 else:assert dirs==i['directories']
 return dict(path=str(p),payloadFiles=len(f),inventorySha256=sha(p/'INVENTORY.json'),closedSha256=sha(p/'CLOSED.json'))
names=['cpu-read-window32-cloud-preparation-r2','cpu-read-window32-stage-preparation-r1','cpu-read-window32-close-preparation-r1','cpu-read-window32-collection-preparation-r1'];closures=[closure(B/n)for n in names]
p=B/names[0];d=load(p/'SOURCE_DELTA.json');old=funcs(p/'baseline/cpu_event_fetch_abab.py');new=funcs(p/'cpu_read_window32_abab.py')
for n in d['unchangedFunctionOrClassNames']:assert old[n]==new[n]
s=B/names[1];delta=load(s/'SOURCE_DELTA.json')
for n,row in delta.items():
 old=funcs(s/'baseline'/row['baseline']);new=funcs(s/n)
 for f in row['unchanged']:assert old[f]==new[f]
c=B/names[3];d=load(c/'UNCHANGED_FUNCTION_AST_BINDINGS.json')
for name,definitions in d['bindings'].items():
 old=funcs(c/'baseline'/name);new=funcs(c/name)
 for n in definitions:assert old[n]==new[n]
p=B/names[2];d=load(p/'UNCHANGED_FUNCTION_AST_BINDINGS.json');old=funcs(p/'baseline/inspect_closed_event_arm.py');new=funcs(p/'inspect_closed_read_window32_arm.py')
for n in d['unchangedDefinitions']:assert old[n]==new[n]
for n in['cpu_read_window32_abab.py','idle_attestation.py','owner_poll_attestation.py','owned_linux_base_8eeb.py','shutdown_warning.py']:
 assert(B/names[0]/n).read_bytes()==(c/n).read_bytes()
parser=B/'read-window32-long-parser-preparation-r1'
for q in parser.rglob('*'):
 if q.is_file():assert q.read_bytes()==(c/'long_parser'/q.relative_to(parser)).read_bytes()
r=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),reviewer='root; independent of controller/stage/collector/close authors',closures=closures,allDeclaredUnchangedAstRecomputed=True,correctedR2SharedHelpersByteIdenticalInCollector=True,entire766efParserCopyUnmodified=True,directSourceReview=['fixedpage32/read8|32 and distinct605/d0 identity','new schema release3/collector6/arm selected roles','realLinux2Plan vs actualLocal4Plan exact corresponding row equivalence','strict scheduler false diagnostic default and full raw/canonical/callback/ACK gates','31unchanged controller definitions preserve lifecycle and foreign-JVM refusal','bounded exclusive staging/source SHA and unchanged2116076873 reserve','strict PID/start/NULargv/executable and genuine absence close','oldwindow8 helper blocked R1 remains retained'],actualNewLinuxGuardsOrStageOrNativeExecuted=False,executionAllowedOnDifferentHost=False,oldHostNowUnavailable=True,newContainerObservedRequiresFreshEnvironmentQualification=True)
with(O/'ROOT_REVIEW.json').open('x')as f:json.dump(r,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(r))
