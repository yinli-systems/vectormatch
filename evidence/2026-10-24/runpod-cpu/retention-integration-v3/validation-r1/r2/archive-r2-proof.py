#!/usr/bin/env python3
"""r2 complete input/native capture using the exact reviewed r1 byte-preserving primitive."""
from pathlib import Path
import importlib.util,json,hashlib
WORK=Path.cwd();R2=WORK/'build/integration-validation/r2';OUT=R2/'archives'
assert (R2/'execution.json').is_file(), 'No capture until Gradle has exited'
assert json.loads((R2/'execution.json').read_text())['exitCode']==0,'Successful r2 required; failed attempts need separate preserved capture'
assert not OUT.exists();OUT.mkdir()
source=WORK/'build/integration-validation/r1/archives/archive-r1-proof.py'
EXPECTED='ac6f688435b377d86751840fb3b65e73e1dfae642fc73151a14c7a89f0519049'
assert hashlib.sha256(source.read_bytes()).hexdigest()==EXPECTED
spec=importlib.util.spec_from_file_location('frozen_integration_archive',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.HERE=OUT;m.R1=R2;m.WORK=WORK
roots=[];expected={}
for record in sorted(R2.glob('*-test-classpath.json')):
 for raw,entry in json.loads(record.read_text())['actualClasspath'].items():
  path=m.checked(raw)
  if 'files' in entry:
   assert {str(p.relative_to(path)) for p in path.rglob('*') if p.is_file()}==set(entry['files'])
   entries=[(path/rel,info) for rel,info in entry['files'].items()]
  else: entries=[(path,entry)]
  for p,info in entries:
   actual={'bytes':p.stat().st_size,'sha256':m.sha(p)}
   assert actual=={'bytes':info['bytes'],'sha256':info['sha256']},str(p)
   expected[str(p)]=actual
  item=('classpath/'+raw.lstrip('/'),path)
  if item not in roots:roots.append(item)
for module in ['core','cluster','server','projector','bench']:
 for folder in ['test-results/test','reports/tests/test']:
  roots.append((module+'/'+folder,WORK/module/'build'/folder))
roots.extend(('r2/'+p.name,p) for p in sorted(R2.iterdir()) if p.is_file())
roots.append(('dedicated-test-database',WORK/'build/integration-validation/test-db-r1'))
artifact=m.archive('artifacts-after-forced-tests',roots,{'allRecordedClasspathFilesMatched':True,'exactClasspathFiles':expected,'frozenArchivePrimitiveSha256':EXPECTED})
previous=json.loads((WORK/'build/integration-validation/r1/archives/native-closure-inventory.json').read_text())
old={v['source'] for v in previous['roots']}
original_roots=m.native_roots
m.native_roots=lambda:[(label,path) for label,path in original_roots() if str(path) not in old]
m.natives()
receipt={'frozenArchivePrimitiveSha256':EXPECTED,'adapterSha256':m.sha(Path(__file__)),'artifactManifestSha256':m.sha(OUT/'artifacts-after-forced-tests/manifest.json'),'nativeClosureManifestSha256':m.sha(OUT/'native-archives-complete.json'),'freeBytesAfter':m.guard(),'r1PreservedUnchanged':True,'nativeSourcesNotDeleted':True}
with (OUT/'capture-complete.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
print(json.dumps(receipt))
