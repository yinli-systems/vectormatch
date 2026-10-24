from pathlib import Path
import json,subprocess,shlex,hashlib,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=Path(__file__).resolve().parent
program='''from pathlib import Path
import socket,json,os,hashlib
assert socket.gethostname()=='33ace3d92505'
roots=['/opt/vectormatch-cpu/restorations/original-native-r1','/opt/vectormatch-cpu/preparation','/opt/vectormatch-cpu/experiments/read-window32-current-abab-r1']
for name in roots:
 p=Path(name)
 assert not p.exists() and not p.is_symlink(), 'Fresh protected absence differs: '+name
print(json.dumps(dict(schemaVersion=1,scope='CURRENT_CPU_CONTAINER_ABSENT_OLD_STATE_AND_FRESH_SYNTHETIC_NAMESPACE',host=socket.gethostname(),bootId=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),absentProtectedPaths=roots,old57AndPg989RestorationClaimed=False,newSyntheticNamespaceOnly=True,affinity=sorted(os.sched_getaffinity(0)),cpuMax=Path('/sys/fs/cgroup/cpu.max').read_text(),memoryMax=Path('/sys/fs/cgroup/memory.max').read_text()),sort_keys=True,indent=2))
'''
(O/'remote_readonly.py').write_text(program);args=['ssh','-i',str(Path.home()/'.ssh/id_ed25519'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile=runtime/cloud/cpu-20261024/current-cpu-connection-r1/known_hosts','-p','40184','root@185.226.156.243','python3 -B -c '+shlex.quote(program)];(O/'REGISTRATION.json').write_text(json.dumps(dict(command=args,readOnly=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n');r=subprocess.run(args,capture_output=True,timeout=45);(O/'baseline.json').write_bytes(r.stdout);(O/'stderr').write_bytes(r.stderr);(O/'EXECUTION.json').write_text(json.dumps(dict(exitCode=r.returncode,baselineSha256=hashlib.sha256(r.stdout).hexdigest()),indent=2)+'\n');assert r.returncode==0;print(r.stdout.decode())
