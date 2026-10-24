#!/usr/bin/env python3
"""One fixed read-only inspector invocation; owned JVM timeout and PG stop request."""
from pathlib import Path
import hashlib,importlib.util,json,os,signal,subprocess
S=Path('/opt/vectormatch-cpu/preparation/pg-readonly-source-r2')
assert hashlib.sha256((S/'pg_recovery.py').read_bytes()).hexdigest()=='e8223d9bdd5a33319002d4567856c072e7f68801b554089bad2e4a6be7d59315'
spec=importlib.util.spec_from_file_location('m',S/'pg_recovery.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
J=m.JOB;m.job_privacy();m.enable_pidfd()
layout=json.loads((S/'root-java-layout.json').read_text())
for n,h in layout['classpath'].items():assert m.sha(S/'lib'/n)==h
for n,e in layout['binaryInventory'].items():assert m.sha(S/'classes'/n)==e['sha256']
assert (J/'start-ready.json').exists() and not (J/'automatic-stop.json').exists()
m.matching_identity(json.loads(m.RECORD.read_text()))
args=['/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java','-Xms16m','-Xmx256m','-cp',
      str(S/'classes')+':'+':'.join(str(S/'lib'/n) for n in layout['classpath']),
      'PgReadonlyInspect',str(J/'sql-inspection-r2')]
m.save_new(J/'sql-intent.json',{'arguments':args,'startedAtUtc':m.now(),'noRetry':True,'timeoutSeconds':75,
    'scope':'Fixedreadonlyrepeatable-readSQL;noapplicationwrites/noAeronACK;PGinternalwritespossible'})
fd=None
try:
    with (J/'sql.stdout').open('xb') as out,(J/'sql.stderr').open('xb') as err:
        child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True,
            env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC'})
        identity=m.process_identity(child.pid);assert identity and identity['arguments']==args
        fd=os.pidfd_open(child.pid);assert m.process_identity(child.pid)==identity
        m.save_new(J/'sql-process.json',identity)
        timed_out=False
        try:code=child.wait(timeout=75)
        except subprocess.TimeoutExpired:
            timed_out=True
            assert m.process_identity(child.pid)==identity,'OwnedJVMidentitychanged;no signal'
            signal.pidfd_send_signal(fd,signal.SIGTERM)
            code=child.wait(timeout=10)
        result={'exitCode':code,'timedOut':timed_out,'ownedInspectorAbsent':m.process_identity(child.pid) is None,'finishedAtUtc':m.now()}
        report=J/'sql-inspection-r2/inspection.json'
        if report.exists():
            d=json.loads(report.read_text())
            result.update(inspectionPassed=d.get('passed'),events=d.get('ledgerEventCount'),marketEvents=d.get('ledgerMarketCount'),
                          trades=d.get('ledgerTradeCount'),framedLedgerSha256=d.get('framedLedgerSha256'))
        m.save_new(J/'sql-result.json',result);print(json.dumps(result))
finally:
    if fd is not None:os.close(fd)
    # Request the existing attached supervisor's normal owned SIGINT fast-clean shutdown.
    m.save_new(J/'STOP-REQUEST.json',{'requestedAtUtc':m.now(),'reason':'Onefixedreadonlyinspectionattemptfinished;successnotassumed'})
