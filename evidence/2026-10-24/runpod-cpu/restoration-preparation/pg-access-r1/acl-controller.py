#!/usr/bin/env python3
"""Apply one narrow execute ACL to exactly five preregistered root-owned parents."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess

SRC=Path('/opt/vectormatch-cpu/preparation/pg-access-source-r1')
CONTROLLER_SHA='c2eb2ba8b96f30ebe09db5010cc4d7b23ab9cf7c7f0d78b289033bf31ab99c77'
TOOLS={'/usr/bin/getfacl':'416b8d800dd0ee9498c46c0446a97bacfa57459e233267d02ba2b357a90c0570',
       '/usr/bin/setfacl':'a58683007857270335b5ed78a969e16524b715dfab5ed2fe8b4be8a86e46af60'}
TARGETS=[Path(x) for x in ['/opt/vectormatch-cpu/restorations',
    '/opt/vectormatch-cpu/restorations/original-native-r1',
    '/opt/vectormatch-cpu/restorations/original-native-r1/node2',
    '/opt/vectormatch-cpu/restorations/original-native-r1/node2/runtime',
    '/opt/vectormatch-cpu/preparation/pg-readonly-recovery-r1']]
BEFORE={'user::rwx','group::---','other::---'}
AFTER={'user::rwx','user:963:--x','group::---','mask::--x','other::---'}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert sha(SRC/'pg_recovery.py')==CONTROLLER_SHA
spec=importlib.util.spec_from_file_location('access',SRC/'pg_recovery.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def observe(p):
    m.no_symlink(p)
    st=p.stat()
    assert stat.S_ISDIR(st.st_mode) and st.st_uid==0 and st.st_gid==0
    r=subprocess.run(['/usr/bin/getfacl','-c','-p','-n',str(p)],capture_output=True,text=True,timeout=5)
    assert r.returncode==0 and not r.stderr
    return {'path':str(p),'uid':st.st_uid,'gid':st.st_gid,'mode':stat.S_IMODE(st.st_mode),
        'mtimeNs':st.st_mtime_ns,'inode':st.st_ino,'device':st.st_dev,'acl':sorted(x.strip() for x in r.stdout.splitlines() if x.strip())}

def main():
    for p,h in TOOLS.items(): assert sha(p)==h
    pre=m.preflight()
    assert pre['account']['exists'] and not pre['access']['writableProtectedAncestors']
    assert {x['path'] for x in pre['access']['blocked']}=={str(x) for x in TARGETS[:4]}
    before=[observe(p) for p in TARGETS]
    assert all(x['mode']==0o700 and set(x['acl'])==BEFORE for x in before)
    job=m.JOB
    m.save_new(job/'acl-intent.json',{'before':before,'targetUid':963,'grant':'EXECUTE_ONLY',
        'targetCount':5,'pgDataIsNotAnAclTarget':True,'noRetry':True,'startedAtUtc':m.now()})
    results=[]
    try:
        for p,b in zip(TARGETS,before):
            assert observe(p)==b
            args=['/usr/bin/setfacl','--no-mask','-m','u:963:--x,m::--x',str(p)]
            r=subprocess.run(args,capture_output=True,text=True,timeout=5)
            a=observe(p)
            item={'arguments':args,'exitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'before':b,'after':a}
            m.save_new(job/('acl-target-%d.json'%len(results)),item)
            results.append(item)
            assert r.returncode==0 and not r.stderr
            assert a['mode']==0o710 and set(a['acl'])==AFTER
            assert all(a[k]==b[k] for k in ['uid','gid','mtimeNs','inode','device','path'])
        after=m.access_paths(m.load_baseline())
        assert after['allRequiredParentsAndBinaryResourcesAccessible']
        m.job_privacy()
        result={'passed':True,'targets':results,'dedicatedEffectiveAccess':after,
                'noPGDataAclOrOwnershipChange':True,'postgresStarted':False}
        m.save_new(job/'acl-result.json',result)
        print(json.dumps(result,indent=2))
    except BaseException as e:
        m.save_new(job/'acl-failure.json',{'type':type(e).__name__,'error':str(e),'completedTargets':len(results),'noRetry':True})
        raise

if __name__=='__main__': main()
