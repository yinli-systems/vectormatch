import hashlib,importlib.util,json,pathlib,shlex,subprocess
BASE=pathlib.Path(__file__).resolve().parent;SOURCE=BASE/'capacity-cloud-pilot-preparation';FIRST=BASE/'capacity-cloud-pilot-staging-r1';OUT=BASE/'capacity-cloud-pilot-staging-r2';OUT.mkdir(exist_ok=False)
spec=importlib.util.spec_from_file_location('remote',BASE/'remote.py');remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
fixture=SOURCE/'release.template.json';frozen=json.loads((SOURCE/'LOCAL_PREPARATION_FROZEN.json').read_text());raw=fixture.read_bytes();assert hashlib.sha256(raw).hexdigest()==frozen['files']['release.template.json']['sha256']
prep='/opt/vectormatch-cpu/preparation/capacity-cloud-pilot-r1';target=prep+'/release.template.json'
program='target_name='+repr(target)+'\nexpected_sha='+repr(hashlib.sha256(raw).hexdigest())+'\n'+"import pathlib,sys,hashlib;raw=sys.stdin.buffer.read();assert hashlib.sha256(raw).hexdigest()==expected_sha\nwith pathlib.Path(target_name).open('xb') as out:out.write(raw)\nprint(expected_sha)"
r=subprocess.run(remote.sshargs()+['python3 -c '+shlex.quote(program)],input=raw,capture_output=True,timeout=60);(OUT/'fixture-upload.stdout').write_bytes(r.stdout);(OUT/'fixture-upload.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr
rows=json.loads((FIRST/'stage.stdout.json').read_text())['stagedFiles'];rows['release.template.json']={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
program='rows='+repr(rows)+'\nprep_name='+repr(prep)+'\n'+"import pathlib,hashlib,json;prep=pathlib.Path(prep_name)\nfor name,row in rows.items():\n raw=(prep/name).read_bytes();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']\nprint(json.dumps({'passed':True,'files':len(rows)}))"
r=remote.run('python3 -c '+shlex.quote(program));(OUT/'all-staged-readback.stdout').write_text(r.stdout);(OUT/'all-staged-readback.stderr').write_text(r.stderr);assert r.returncode==0,r.stderr
release_sha=hashlib.sha256((FIRST/'release.json').read_bytes()).hexdigest()
for label,command,timeout in [('linux-guards','python3 -B '+shlex.quote(prep+'/test_capacity_cloud_pilot.py'),60),('preflight','python3 -B '+shlex.quote(prep+'/capacity_cloud_pilot.py')+' --release-sha256 '+release_sha,240)]:
 r=remote.run(command,timeout=timeout);(OUT/(label+'.stdout')).write_text(r.stdout);(OUT/(label+'.stderr')).write_text(r.stderr);assert r.returncode==0,r.stderr
(OUT/'receipt.json').write_text(json.dumps({'passed':True,'releaseSha256':release_sha,'stagedFiles':rows,'linuxGuards':42,'readOnlyPreflightPassed':True,'javaStartedDuringPreparation':False,'firstAttemptFailure':'Guard fixture release.template.json omitted; source/JARs/release unchanged; no application JVM or attempt started'},indent=2)+'\n')
program='prep_name='+repr(prep)+'\nrelease_sha='+repr(release_sha)+'\n'+r'''
import hashlib,json,os,pathlib,subprocess,time
source=pathlib.Path(prep_name);controller=source/'capacity_cloud_pilot.py'
assert hashlib.sha256(controller.read_bytes()).hexdigest()=='ca5d29fef52bbb63c4968b96affd5bad8494495612ada5af368242782ca3818a'
assert hashlib.sha256((source/'release/release.json').read_bytes()).hexdigest()==release_sha
args=['/usr/bin/python3','-B',str(controller),'--release-sha256',release_sha,'--start-new']
with (source/'execution-register.json').open('x') as register:
 with (source/'execution.stdout').open('xb') as out,(source/'execution.stderr').open('xb') as err:
  child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=str(source),start_new_session=True,close_fds=True)
 proc=pathlib.Path('/proc')/str(child.pid);raw=(proc/'cmdline').read_bytes();fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
 row={'pid':child.pid,'startTicks':int(fields[19]),'observedCommandSha256':hashlib.sha256(raw).hexdigest(),'expectedArguments':args,'startUnixNs':time.time_ns(),'noRerun':True}
 json.dump(row,register,indent=2);register.write('\n');register.flush();os.fsync(register.fileno())
print(json.dumps(row),flush=True)
'''
r=remote.run('python3 -c '+shlex.quote(program),timeout=45);(OUT/'launch.stdout.json').write_text(r.stdout);(OUT/'launch.stderr').write_text(r.stderr);assert r.returncode==0,r.stderr
print(r.stdout)
