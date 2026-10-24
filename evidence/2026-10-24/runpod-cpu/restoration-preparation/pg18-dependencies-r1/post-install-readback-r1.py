import pathlib,platform,subprocess,json,importlib.util,hashlib
assert platform.node()=='ed6c0673f5cb'
root=pathlib.Path('/opt/vectormatch-cpu/preparation/pg18-dependencies-r1')
prior=json.loads((root/'install-result.json').read_text());assert not prior['passed'] and prior['error']['type']=='AssertionError'
assert len(prior['commands'])==3 and all(x['exitCode']==0 and not x['remainingProcessGroupMembers'] for x in prior['commands'])
assert prior['commands'][1]['name']=='apt-install-build-dependencies'
builder=root/'build-pg18-tools.py';assert hashlib.sha256(builder.read_bytes()).hexdigest()=='453555f88e563123d299609fa8e1bb88e0f5645e80c4cf51173da8040f1c98fc'
spec=importlib.util.spec_from_file_location('builder',builder);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);assert not m.benchmark_processes()
cmd=['/usr/bin/dpkg-query','-W','-f','${Package}\t${Version}\t${Architecture}\n']+sorted(prior['expectedVersions'])
r=subprocess.run(cmd,capture_output=True,text=True,timeout=10);assert r.returncode==0
rows=[line.split('\t') for line in r.stdout.strip().splitlines()];assert len(rows)==4 and len({x[0] for x in rows})==4
assert {x[0]:x[1] for x in rows}==prior['expectedVersions'] and all(x[2]=='amd64' for x in rows)
versions={n:subprocess.run(['/usr/bin/'+n,'--version'],capture_output=True,text=True,timeout=10).stdout for n in ('bison','flex')}
assert '3.5.1' in versions['bison'] and '2.6.4' in versions['flex']
out={'passed':True,'readOnly':True,'packageInstallRepeated':False,'priorInstallAllCommandsSucceeded':True,'priorGuardFailure':'${binary:Package} returns architecture-qualified libsigsegv2:amd64. Original assertion expected unqualified name;original failure retained. Independent ${Package}/${Architecture} readback verifies base package,exact version and amd64.','actualPackages':rows,'argv':cmd,'stdout':r.stdout,'versions':versions,'benchmarkIdleObserved':True,'databaseDataTouched':False}
with (root/'post-install-readback-r1.json').open('x') as f:json.dump(out,f,indent=2)
print(json.dumps(out))
