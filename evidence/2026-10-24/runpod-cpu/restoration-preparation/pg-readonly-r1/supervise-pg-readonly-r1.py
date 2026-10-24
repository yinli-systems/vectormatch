#!/usr/bin/env python3
"""Attached outer supervisor for exactly one reviewed PG-only probe."""
from pathlib import Path
import hashlib,importlib.util,json,os,signal,subprocess,time
S=Path('/opt/vectormatch-cpu/preparation/pg-readonly-source-r1')
PG_CONTROLLER_SHA='0a12ad7dd7aed6866c58e6c0fd46e068b82721144872584880965d7cfb13d9f8'
assert hashlib.sha256((S/'pg_recovery.py').read_bytes()).hexdigest()==PG_CONTROLLER_SHA
spec=importlib.util.spec_from_file_location('m',S/'pg_recovery.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.host_check();m.job_privacy();m.enable_pidfd()
args=['/usr/bin/python3','-B',str(S/'pg_recovery.py'),'start','--execute']
assert not (m.JOB/'start-intent.json').exists()
m.save_new(m.JOB/'outer-supervisor.json',dict(m.process_identity(os.getpid()),sourceSha256=m.sha(Path(__file__)),
    pgControllerSha256=PG_CONTROLLER_SHA,startedAtUtc=m.now(),scope='OnePG-onlyboundedprobe; noSQLinthissupervisor'))
fd=None
with (m.JOB/'controller.stdout').open('xb') as out,(m.JOB/'controller.stderr').open('xb') as err:
    child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC'})
    try:
        owned=m.process_identity(child.pid)
        assert owned and owned['arguments']==args
        fd=os.pidfd_open(child.pid)
        assert m.process_identity(child.pid)==owned
        m.save_new(m.JOB/'pg-controller-process.json',owned)
        try:code=child.wait(timeout=235)
        except subprocess.TimeoutExpired:
            actual=m.process_identity(child.pid)
            assert actual==owned,'Controller identitychanged; no signal'
            signal.pidfd_send_signal(fd,signal.SIGTERM)
            code=child.wait(timeout=40)
            m.save_new(m.JOB/'outer-timeout.json',{'timeoutSeconds':235,'ownedControllerSignalled':'SIGTERM','exitCode':code,
                'notAHardLifetimeGuarantee':True})
        m.save_new(m.JOB/'outer-result.json',{'controllerExitCode':code,'finishedAtUtc':m.now(),
            'ownedControllerAbsent':m.process_identity(child.pid) is None,'postgresStopRequiresSeparateReceipt':True})
        print(json.dumps({'controllerExitCode':code,'controllerStopped':True,'probeSQLSuccessNotAssumed':True}))
    finally:
        if fd is not None:os.close(fd)
