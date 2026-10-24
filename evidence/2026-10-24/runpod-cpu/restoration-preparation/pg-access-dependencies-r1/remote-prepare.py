import pathlib,platform,json,hashlib,importlib.util,shutil,re
assert platform.node()=='ed6c0673f5cb'
root=pathlib.Path('/opt/vectormatch-cpu/preparation/pg-access-dependencies-r1');assert not any(p.is_symlink() for p in [root]+list(root.parents)) and not root.exists()
b=pathlib.Path('/opt/vectormatch-cpu/preparation/pg18-builder-r3/build-pg18-tools.py');assert hashlib.sha256(b.read_bytes()).hexdigest()==EXPECTED
spec=importlib.util.spec_from_file_location('bounded_steps',b);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert not m.benchmark_processes() and shutil.disk_usage(root.parent).free>3*1024**3
assert shutil.which('getfacl') is None and shutil.which('setfacl') is None
root.mkdir(mode=0o700);logs=root/'logs';logs.mkdir();commands=[]
out={'passed':False,'commands':commands,'usersCreated':False,'aclChanged':False,'ownershipChanged':False,'databaseServerStarted':False,'builderSha256':EXPECTED}
env={'PATH':m.SAFE_PATH,'LANG':'C','LC_ALL':'C','TZ':'UTC','DEBIAN_FRONTEND':'noninteractive'}
try:
 sim=m.run_step('acl-install-simulation',['/usr/bin/apt-get','-s','--no-upgrade','--no-remove','--no-install-recommends','install','acl'],root,env,logs,commands,20)
 assert {x.split()[1] for x in sim.splitlines() if x.startswith('Inst ')}=={'acl'} and '0 upgraded, 1 newly installed, 0 to remove' in sim
 version=re.search(r'^Inst acl \(([0-9A-Za-z.+:~_-]+) ',sim,re.M).group(1)
 args=['/usr/bin/apt-get','--assume-yes','--no-upgrade','--no-remove','--no-install-recommends','-o','Acquire::Retries=0','-o','Acquire::http::Timeout=10','install','acl='+version]
 with (root/'install-attempted.json').open('x') as f:json.dump({'argv':args,'candidateVersion':version},f,indent=2)
 assert not m.benchmark_processes()
 m.run_step('acl-install',args,root,env,logs,commands,60)
 actual=m.run_step('acl-package-version',['/usr/bin/dpkg-query','-W','-f','${Version}','acl'],root,env,logs,commands,10);assert actual==version
 out['candidateVersion']=version;out['actualVersion']=actual
 for name in ('getfacl','setfacl'):
  path=pathlib.Path('/usr/bin')/name;assert path.is_file();out[name]={'path':str(path),'sha256':m.digest(path),'version':m.run_step(name+'-version',[str(path),'--version'],root,env,logs,commands,10)}
 out['passed']=True
except Exception as error:out['error']={'type':type(error).__name__,'message':str(error)}
finally:
 out['freeBytesAfter']=shutil.disk_usage(root).free
 with (root/'result.json').open('x') as f:json.dump(out,f,indent=2)
 out['logs']={p.name:p.read_text() for p in logs.glob('*.log')}
print(json.dumps(out))
