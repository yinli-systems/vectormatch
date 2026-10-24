#!/usr/bin/env python3
"""One local javac/java metadata execution. No build, driver, node, client or network."""
import datetime
import hashlib
import json
import os
import pathlib
import shutil
import stat
import subprocess
import time
import traceback

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[3]
WT=ROOT/'runtime/cloud/cpu-20261024/event-fetch-page-v3-worktree'
VALIDATION=WT/'runtime/event-fetch-local-validation'
SOURCE_COMMIT='d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'
PRIOR=ROOT/'evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/local-unit-validation-r1'

def require(ok,message):
    if not ok:raise AssertionError(message)
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def pin(path):
    st=path.stat()
    require(not path.is_symlink() and stat.S_ISREG(st.st_mode),'not regular no-symlink file: '+str(path))
    return {'bytes':st.st_size,'sha256':sha(path),'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}
def save(name,data):
    with (HERE/name).open('x') as f:json.dump(data,f,indent=2,sort_keys=True);f.write('\n')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def run(label,arguments,env):
    save(label+'-REGISTRATION.json',{'atUTC':now(),'arguments':arguments,'cwd':str(HERE),
        'environmentValuesNotCaptured':True,'actualKernelArgvIndependentlyDecoded':False})
    start=time.monotonic();child=None;timeout=False;status=None
    with (HERE/(label+'.stdout')).open('xb') as out,(HERE/(label+'.stderr')).open('xb') as err:
        child=subprocess.Popen(arguments,cwd=HERE,stdout=out,stderr=err,env=env)
        save(label+'-IDENTITY.json',{'atUTC':now(),'pid':child.pid,'expectedArguments':arguments,
            'identitySource':'direct unreaped Popen child handle; no independent kernel argv decoding on macOS',
            'actualKernelArgvIndependentlyDecoded':False})
        try:status=child.wait(timeout=40)
        except subprocess.TimeoutExpired:
            timeout=True;child.terminate()
            try:status=child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                save(label+'-EXECUTION.json',{'exitCode':None,'timedOut':True,'ownedChildPid':child.pid,
                    'ownedChildExited':False,'noEscalationOrRetry':True,'elapsedSeconds':time.monotonic()-start})
                raise RuntimeError('owned metadata child did not exit after TERM; no escalation/retry')
    row={'exitCode':status,'timedOut':timeout,'ownedChildPid':child.pid,'ownedChildExited':True,
         'elapsedSeconds':time.monotonic()-start,'completedAtUTC':now(),
         'stdout':pin(HERE/(label+'.stdout')),'stderr':pin(HERE/(label+'.stderr'))}
    save(label+'-EXECUTION.json',row)
    require(status==0 and not timeout,label+' failed; preserve exact attempt')
    return row

def main():
    require(not (HERE/'REGISTRATION.json').exists(),'one execution only; preserve existing attempt')
    materials=json.loads((VALIDATION/'DISTRIBUTION_MATERIALS.json').read_text())
    frozen=json.loads((VALIDATION/'SOURCE_FROZEN.json').read_text())
    unit=json.loads((VALIDATION/'units-r1/registration.json').read_text())
    files=[HERE/'EventFetchDistributionObservation.java',HERE/'run_local.py',VALIDATION/'DISTRIBUTION_MATERIALS.json',VALIDATION/'SOURCE_FROZEN.json',PRIOR/'INVENTORY.json',PRIOR/'CLOSED.json']
    files.extend(WT/name for name in frozen['sourceFiles'])
    for name,row in frozen['sourceFiles'].items():
        actual=pin(WT/name)
        require(all(actual[k]==row[k] for k in ['bytes','sha256','mode']),'frozen feature source differs: '+name)
    jars=[]
    for name,row in materials['installedJars'].items():
        path=pathlib.Path(row['path']);actual=pin(path)
        require(all(actual[k]==row[k] for k in ['bytes','sha256','mode']),'installed JAR differs: '+name)
        files.append(path);jars.append(path)
    jdk={}
    for raw,row in unit['jdk'].items():
        path=pathlib.Path(raw).resolve();actual=pin(path)
        require(all(actual[k]==row[k] for k in ['bytes','sha256','mode']),'unit-pinned JDK input differs')
        jdk[path.name]=path;files.append(path)
    require('JAVA_VERSION="21.0.13"' in jdk['release'].read_text(),'pinned JDK21 required')
    classes=HERE/'classes';require(not classes.exists(),'fresh helper classes directory required')
    classes.mkdir()
    cp=os.pathsep.join(map(str,jars))
    compile_args=[str(jdk['javac']),'--release','21','-encoding','UTF-8','-cp',cp,'-d',str(classes),str(HERE/'EventFetchDistributionObservation.java')]
    java_args=[str(jdk['java']),'-Xmx128m','--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','-cp',str(classes)+os.pathsep+cp,'io.vectormatch.cluster.EventFetchDistributionObservation',str(HERE/'actual-distribution-observation.json')]
    before={str(p):pin(p) for p in files}
    removed=[];env=os.environ.copy()
    for name in ['JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS']:
        if name in env:removed.append(name);env.pop(name)
    save('REGISTRATION.json',{'schemaVersion':1,'atUTC':now(),'sourceCommit':SOURCE_COMMIT,
        'scope':'Single local metadata helper compilation/execution; no project rebuild, owner, driver/client, native UDP, node, cluster, SQL or business session',
        'compilerArguments':compile_args,'javaArguments':java_args,'inputsBefore':before,
        'removedJavaOptionEnvironmentNames':removed,'environmentValuesNotCaptured':True,
        'priorClosedUnitArchiveSha256':sha(PRIOR/'CLOSED.json'),'priorUnitInventorySha256':sha(PRIOR/'INVENTORY.json'),
        'expectedCodeFingerprint':materials['prospectiveCodeFingerprintFromActualInstalledJarBytes'],
        'noNativeOrPerformanceClaim':True})
    shutil.copy2(jdk['release'],HERE/'jdk-release')
    javac=run('javac',compile_args,env)
    helper=classes/'io/vectormatch/cluster/EventFetchDistributionObservation.class'
    require(set(classes.rglob('*.class'))=={helper},'unexpected extra helper classes')
    helper_pin=pin(helper);save('COMPILED_HELPER.json',{'classFile':str(helper),'class':helper_pin,'source':pin(HERE/'EventFetchDistributionObservation.java'),'compilerArguments':compile_args})
    java=run('java',java_args,env)
    observed=json.loads((HERE/'actual-distribution-observation.json').read_text())
    require(observed['actualCodeFingerprint']==materials['prospectiveCodeFingerprintFromActualInstalledJarBytes'],'actual runtime code fingerprint differs')
    require(observed['sourceCommit']==SOURCE_COMMIT and observed['performanceEvidence'] is False and observed['selectionIntentOnly'] is True,'helper scope differs')
    expected_sources={
        'io.vectormatch.cluster.RetentionCapacityAeronPilotV3':'cluster-0.1.0-SNAPSHOT.jar',
        'io.vectormatch.cluster.RetentionNodeMainV3':'cluster-0.1.0-SNAPSHOT.jar',
        'io.vectormatch.cluster.RetentionBatchOwnerV3':'cluster-0.1.0-SNAPSHOT.jar',
        'io.vectormatch.cluster.RetentionOwnerPollPolicyV3':'cluster-0.1.0-SNAPSHOT.jar',
        'io.vectormatch.core.MatchingEngine':'core-0.1.0-SNAPSHOT.jar',
        'io.aeron.driver.MediaDriver':'aeron-all-1.53.3.jar',
        'org.agrona.DirectBuffer':'aeron-all-1.53.3.jar'}
    require(len(observed['actualCodeSources'])==7 and {r['class'] for r in observed['actualCodeSources']}==set(expected_sources),'actual seven-class set differs')
    for row in observed['actualCodeSources']:
        expected=materials['installedJars'][expected_sources[row['class']]]
        require(all(row[k]==expected[k] for k in ['path','bytes','sha256']),'actual class source differs: '+row['class'])
    for name,row in observed['distributionJars'].items():
        require(all(row[k]==materials['installedJars'][name][k] for k in ['path','bytes','sha256']),'actual distribution body differs')
    require(set(observed['distributionJars'])==set(materials['installedJars']),'actual four-JAR inventory differs')
    require(pin(helper)==helper_pin,'helper class changed during execution')
    after={str(p):pin(p) for p in files};save('INPUTS_AFTER.json',after)
    require(after==before,'registered inputs changed')
    save('VALIDATION.json',{'passed':True,'actualSevenCodeSourcesVerified':True,'uniqueRuntimeJarOrigins':len({r['path'] for r in observed['actualCodeSources']}),
        'allFourInstalledJarBodiesVerified':True,'actualCodeFingerprint':observed['actualCodeFingerprint'],
        'commonEnvelopeEqualExceptSelectedFields':True,'planDifferenceKeys':observed['planDifferenceKeys'],
        'allInputsUnchanged':True,'helperClassUnchanged':True,'driverOrOwnerConsumptionObserved':False,
        'sourceCommitIsExternalVersionBindingNotProofOfApplicationExecution':True,'performanceEvidence':False})
    readme='''This closed local metadata attempt compiled and executed only EventFetchDistributionObservation with the four frozen installed candidate JARs. It did not rebuild the project or construct an owner, MediaDriver, Aeron client, node, cluster or business session. Plan calculation uses temporary in-memory reference engines and codec derivation; it is a prospective resource bound, not a capacity result.\n\nSeven classes were actually loaded from three distinct JAR origins. DirectBuffer came from aeron-all, while the complete independent agrona JAR was separately hashed among all four distribution bodies. Both LONG configurations came from the actual eventFetchPageConfig entry and actual boundedPlan. All Plan fields match except eventFetchCount, selectedMaximumLogicalMaintenanceRpcs and selectedMaximumEventFetchRpcs. Owner default/explicit1ms and server-driver100us are pure selection intentions only. No CLI or agent consumption, sleep, hard real-time behavior or performance was observed.\n\nThe prerequisite closed unit archive is hash-bound in REGISTRATION.json; it contains the four JAR bodies and full source/unit captures. The source commit d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8 versioned the same twelve tested source paths after the unit build. All frozen source, installed JAR and JDK pins were checked before and after this attempt. Local process identity is the direct unreaped Popen handle, not independently decoded kernel argv. Java/javac commands, stdout/stderr, exits and helper class SHA are retained. JDK release bytes are copied; full JDK executables/distribution are hash-only.\n'''
    with (HERE/'README.md').open('x') as f:f.write(readme)
    rows={p.relative_to(HERE).as_posix():pin(p) for p in sorted(HERE.rglob('*')) if p.is_file()}
    dirs={p.relative_to(HERE).as_posix():{'mode':stat.S_IMODE(p.stat().st_mode),'uid':p.stat().st_uid,'gid':p.stat().st_gid} for p in sorted(HERE.rglob('*')) if p.is_dir()}
    save('MANIFEST.json',{'schemaVersion':1,'files':rows,'directories':dirs,'excluded':['MANIFEST.json','CLOSED.json'],'scope':'Complete local metadata preparation and one execution before closure'})
    save('CLOSED.json',{'schemaVersion':1,'passed':True,'atUTC':now(),'sourceCommit':SOURCE_COMMIT,
        'scope':'EVENT_FETCH_LOCAL_INSTALLED_JAR_METADATA_ONLY','manifestSha256':sha(HERE/'MANIFEST.json'),
        'observationSha256':sha(HERE/'actual-distribution-observation.json'),'helperSourceSha256':sha(HERE/'EventFetchDistributionObservation.java'),
        'helperClassSha256':sha(helper),'actualCodeFingerprint':observed['actualCodeFingerprint'],
        'javaExitCode':java['exitCode'],'javacExitCode':javac['exitCode'],'allInputsUnchanged':True,
        'commonEnvelopeEqualExceptSelectedFields':True,'metadataJvmExited':True,
        'nativeOrCloudOrOwnerConsumptionObserved':False,'performanceEvidence':False})
    print(json.dumps({'passed':True,'closedSha256':sha(HERE/'CLOSED.json'),'manifestSha256':sha(HERE/'MANIFEST.json'),'observationSha256':sha(HERE/'actual-distribution-observation.json'),'actualCodeFingerprint':observed['actualCodeFingerprint']}))

if __name__=='__main__':
    try:main()
    except BaseException as error:
        if not (HERE/'FAILED.json').exists():save('FAILED.json',{'passed':False,'atUTC':now(),'error':repr(error),'traceback':traceback.format_exc(),'originalInputsPreserved':True,'noAutomaticRetry':True})
        raise
