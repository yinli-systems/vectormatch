#!/usr/bin/env python3
"""Finish only the unattempted JOB ACL; never repeat the four completed ACL grants."""
import hashlib,importlib.util,json,stat,subprocess
from pathlib import Path
S=Path('/opt/vectormatch-cpu/preparation/pg-access-source-r1')
assert hashlib.sha256((S/'pg_recovery.py').read_bytes()).hexdigest()=='c2eb2ba8b96f30ebe09db5010cc4d7b23ab9cf7c7f0d78b289033bf31ab99c77'
spec=importlib.util.spec_from_file_location('m',S/'pg_recovery.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
J=m.JOB
def inspect(p):
    m.no_symlink(p);s=p.stat();assert stat.S_ISDIR(s.st_mode)
    r=subprocess.run(['/usr/bin/getfacl','-c','-p','-n',str(p)],capture_output=True,text=True,timeout=5)
    assert r.returncode==0 and not r.stderr
    return dict(path=str(p),uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode),inode=s.st_ino,device=s.st_dev,mtimeNs=s.st_mtime_ns,
                acl=sorted(x.strip() for x in r.stdout.splitlines() if x.strip()))
def main():
    assert m.sha('/usr/bin/setfacl')=='a58683007857270335b5ed78a969e16524b715dfab5ed2fe8b4be8a86e46af60'
    assert m.sha('/usr/bin/getfacl')=='416b8d800dd0ee9498c46c0446a97bacfa57459e233267d02ba2b357a90c0570'
    failure=json.loads((J/'acl-failure.json').read_text());assert failure['completedTargets']==4
    assert not (J/'acl-target-4.json').exists() and not (J/'acl-result.json').exists()
    # Every already-completed target must match its exact persisted postcondition, not be mutated again.
    completed=[]
    for i in range(4):
        d=json.loads((J/('acl-target-%d.json'%i)).read_text());assert d['exitCode']==0 and inspect(Path(d['after']['path']))==d['after']
        completed.append(d)
    pre=m.preflight(require_access=True,expected_owner=(0,0));assert pre['account']['exists']
    b=inspect(J);assert b['uid']==0 and b['gid']==0 and b['mode']==0o700 and set(b['acl'])=={'user::rwx','group::---','other::---'}
    # Store control receipts OUTSIDE JOB: r1 failed because creating receipts inside JOB changes its directory mtime.
    m.save_new(S/'job-acl-r2-intent.json',{'before':b,'noRetry':True,'onlyUnattemptedTarget':str(J),
       'rootCauseR1':'OwnreceiptcreationchangedJOBmtimebeforetarget5;targets0to3passedandnotrepeated','startedAtUtc':m.now()})
    assert inspect(J)==b
    args=['/usr/bin/setfacl','--no-mask','-m','u:963:--x,m::--x',str(J)]
    r=subprocess.run(args,capture_output=True,text=True,timeout=5);a=inspect(J)
    result={'arguments':args,'exitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'before':b,'after':a,
            'firstFourTargetsUntouched':True,'pgDataOwnershipUntouched':True,'postgresStarted':False}
    m.save_new(S/'job-acl-r2-result.json',result)
    assert r.returncode==0 and not r.stderr and a['mode']==0o710
    assert set(a['acl'])=={'user::rwx','user:963:--x','group::---','mask::--x','other::---'}
    assert all(a[k]==b[k] for k in ['path','uid','gid','inode','device','mtimeNs'])
    m.job_privacy()
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
