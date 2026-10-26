from pathlib import Path
import sys,json,hashlib,subprocess,importlib.util,time,socket,tarfile,os,shutil,traceback
c=json.load(sys.stdin);root=Path(c['root']);assert root.parent==Path('/opt/vectormatch-cpu/experiments')and root.name=='v4-sealed-bounded-'+c['freeze']['factor']+'-'+str(c['rate'])+'-'+c['arm']+'-r1'
assert socket.gethostname()=='33ace3d92505';freeze=json.loads((root/'SOURCE_FREEZE.json').read_text());assert freeze==c['freeze']
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
for name,pin in freeze['files'].items():assert(root/name).is_file()and not(root/name).is_symlink()and(root/name).stat().st_size==pin['bytes']and sha(root/name)==pin['sha256']
spec=importlib.util.spec_from_file_location('qualified_base',root/'owned_linux_base_8eeb.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
launched=json.loads((root/'LAUNCHED.json').read_text());controller=launched['controller'];deadline=time.monotonic()+210
while base.matching_identity(controller)is not None:
 assert time.monotonic()<deadline,'original controller still active;retain evidence,do not retry'
 time.sleep(1)
assert(root/'SUCCESS.json').is_file()or(root/'FAILED.json').is_file()
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 row=base.process_identity(int(proc.name))
 if row is not None:assert Path(row['arguments'][0]).name not in('java','javaw','postgres','postmaster'),'refuse audit/collection while JVM/SQL workload active'
passed=(root/'SUCCESS.json').is_file();audit_passed=False;analysis_passed=False
if passed:
 assert not(root/'AUDIT_INTENT.json').exists(),'one audit attempt only'
 base.save(root/'AUDIT_INTENT.json',dict(qualifiedSource=freeze['sourceCommit'],auditSha256=sha(root/'audit-async-capacity-v4.py'),analysisSha256=sha(root/'analyze.py'),outsideArrivalWindow=True,noBusinessCommandsIssued=True))
 try:
  with(root/'independent-audit.stdout').open('xb')as out,(root/'independent-audit.stderr').open('xb')as err:r=subprocess.run([sys.executable,'-B',str(root/'audit-async-capacity-v4.py'),str(root/'state'),str(root/'independent-audit')],stdin=subprocess.DEVNULL,stdout=out,stderr=err,timeout=120)
  assert r.returncode==0,'independent audit failed;retain originals'
  audit_passed=json.loads((root/'independent-audit/RESULT.json').read_text())['passed'];assert audit_passed
  with(root/'analysis.stdout').open('xb')as out,(root/'analysis.stderr').open('xb')as err:r=subprocess.run([sys.executable,'-B',str(root/'analyze.py'),str(root),str(root/'independent-audit'),str(root/'analysis')],stdin=subprocess.DEVNULL,stdout=out,stderr=err,timeout=120)
  assert r.returncode==0,'analysis failed;retain originals'
  analysis_passed=json.loads((root/'analysis/RESULT.json').read_text())['passed'];assert analysis_passed
 except BaseException as error:base.save(root/'AUDIT_FAILED.json',dict(passed=False,error=repr(error),traceback=traceback.format_exc(),noAutomaticRetry=True,noBusinessCommandsIssued=True))
for name,pin in freeze['files'].items():assert sha(root/name)==pin['sha256']
out=Path('/opt/vectormatch-cpu/collections')/root.name;assert not out.exists();assert shutil.disk_usage(root).free>=1024**3;out.mkdir(mode=0o700)
source=out/'collection-tools';source.mkdir();(source/'scope_tar.py').write_text(c['scopeSource']);(source/'remote.py').write_text(c['remoteSource'])
assert sha(source/'scope_tar.py')==c['scopeSha256']and sha(source/'remote.py')==c['remoteSha256']
namespace={'__name__':'scope_tar','__file__':str(source/'scope_tar.py')};exec(compile(c['scopeSource'],'scope_tar.py','exec'),namespace)
tree=namespace['tree'];verify=namespace['verify'];scopes={'point':root,'collection-tools':source};before={name:tree(path)for name,path in scopes.items()};archive=out/'complete-native-point-and-independent-audit.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=1)as tar:
 for name,path in scopes.items():tar.add(path,arcname='original/'+name)
review=verify(archive,before);assert all(tree(path)==before[name]for name,path in scopes.items());assert base.matching_identity(controller)is None
result=dict(passed=True,nativePassed=passed,independentAuditPassed=audit_passed,analysisPassed=analysis_passed,root=str(root),sourceCommit=freeze['sourceCommit'],artifactFingerprint=freeze['artifactFingerprint'],controllerNoLongerExecuting=True,controllerProcDirectoryAbsent=not Path('/proc',str(controller['pid'])).exists(),sourceScopes=before,everyOriginalMemberVerified=review,archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=sha(archive)),noBusinessCommandsIssued=True)
(out/'MANIFEST.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result))
