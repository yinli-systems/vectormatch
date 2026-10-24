from pathlib import Path
import json,hashlib,stat,ast,zipfile,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
def tree(p):
 f={};d={}
 for q in [p,*sorted(p.rglob('*'))]:
  assert not q.is_symlink();s=q.stat();n=q.relative_to(p).as_posix();m=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
  if q.is_dir():d[n]=m
  else:f[n]=dict(m,bytes=s.st_size,sha256=sha(q))
 return dict(files=f,directories=d)
def closure(p,count):
 i=load(p/'INVENTORY.json');c=load(p/'CLOSED.json');t=tree(p);assert sha(p/'INVENTORY.json')==c['inventorySha256']
 for n in ['INVENTORY.json','CLOSED.json']:t['files'].pop(n)
 assert t['files']==i['files'] and len(t['files'])==count
 if isinstance(i['directories'],list):
  expected={x['path']:{k:v for k,v in x.items() if k not in ['path','empty']} for x in i['directories']}
  assert {k:v for k,v in t['directories'].items() if k!='.'}==expected
  for row in i['directories']:assert row['empty']==(not any((p/row['path']).iterdir()))
 else:assert t['directories']==i['directories']
 return dict(payloadFiles=count,inventorySha256=sha(p/'INVENTORY.json'),closedSha256=sha(p/'CLOSED.json'))
p=B/'read-window32-long-parser-preparation-r1';parser=closure(p,76);frozen=load(p/'SOURCE_FROZEN.json')
assert sha(p/'SOURCE_FROZEN.json')=='766ef61f32b8c0dfe8010749795637969b319ddcd19e05d8351830d0e02836ad'
a=load(p/'UNCHANGED_AST_BINDINGS.json')
for n in a['unchangedWholeFiles']:assert (p/'source'/n).read_bytes()==(p/'baseline/source'/n).read_bytes()
for n,names in a['identicalTopLevelFunctionsOrClasses'].items():
 nodes=[]
 for base in ['source','baseline/source']:
  nodes.append({x.name:ast.dump(x,include_attributes=False) for x in ast.parse((p/base/n).read_text()).body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))})
 for name in names:assert nodes[0][name]==nodes[1][name]
g=p/'guards-r1';c=load(g/'completion.json');reg=load(g/'registration.json')
assert c['passed'] and c['exitCode']==0 and c['actualDistinctGuards']==51 and c['allInputsUnchanged'] and not c['actualRawAuditOrJavaNativeSshGitExecuted']
for name in ['stdout','stderr']:assert sha(g/name)==c[name+'Sha256']
assert 'Ran 51 tests' in (g/'stderr').read_text() and (g/'stderr').read_text().rstrip().endswith('OK')
assert sha(g/'source.zip')==c['sourceZipSha256']==reg['sourceZipSha256']
with zipfile.ZipFile(g/'source.zip') as z:
 for name,row in reg['inputs'].items():
  q=p/name;assert q.stat().st_size==row['bytes'] and sha(q)==row['sha256'];raw=z.read(name);assert raw==q.read_bytes()
e=R/'evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/linux-metadata-r1';metadata=closure(e,104)
before=load(e/'SOURCE_BEFORE_COPY.json');after=load(e/'SOURCE_AFTER_COPY.json');assert len(before)==9 and after['passed']
for name,row in before.items():
 for q in [Path(row['source']),e/name]:
  t=tree(q);assert t['files']==row['inventory']['files'] and t['directories']==row['inventory']['directories']
 assert after['sourceTrees'][name]==row['inventory']
bind=load(e/'ACTUAL_METADATA_ROOT_INPUT_PORTABLE_BINDINGS.json');assert len(bind['inputs'])==9
for name,row in bind['inputs'].items():
 q=e/row['archivedAt'];pin=row['pin'];assert q.stat().st_size==pin['bytes'] and sha(q)==pin['sha256'] and q.read_bytes()==Path(row['originalAbsolutePath']).read_bytes()
r=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),reviewer='root; independent of parser and archive authors',parser=parser,metadataArchive=metadata,allRegisteredGuardInputsAndZipBodiesVerified=True,actual51PureGuardsPassed=True,allDeclaredUnchangedAstAndWholeFilesRecomputed=True,allNineMetadataScopeOriginalAndCopiedMirrorsEqual=True,allNineMetadataInputBodiesVerified=True,directSourceReview=['Explicit page32/read8|32 only; invalid input before IO','common32 finite exact actual Plan inventories and physical registry129 preserved','constructed owner1ms/driver100us and actualFPd0/source605 enforced','full original/callback/correlation and strict scheduler path retained','phase order/ranges and force/readback-before-ACK retained','completed-unconsumed runtime attestation limitations remain explicit','failure originals bounded selected8|32; no ACK or independent durability claim','local4Plan containers remain local; Linux2Plan requires separate complete equivalence adapter'],nativeQualification=False,rawPerformanceAuditExecuted=False,newTestsJvmOrSshExecuted=False)
with (O/'ROOT_REVIEW.json').open('x') as out:json.dump(r,out,indent=2,sort_keys=True);out.write('\n')
print(json.dumps(r))
