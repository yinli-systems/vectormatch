#!/usr/bin/env python3
"""Local full nested closure, actual JAR/class binding, process/config and protected-state reconciliation."""
from pathlib import Path,PurePosixPath
import hashlib,json,tarfile,zipfile,traceback
from common import WINDOWS,require,sha,audit_arguments
from shutdown_warning import classify as classify_node_log
import cpu_owner_poll_abab as controller
from owner_bundle import verify as verify_owner_bundle

def audit(a,c,release):
    controller.configure_arm(c['arm'])
    prep=c['remotePrep'];raw=a.collection/'raw-files';job=raw/'job';outer=json.loads((a.collection/'remote-inventory.stdout.json').read_text())
    before=json.loads((job/'before.json').read_text());after=json.loads((job/'after-clean-stop.json').read_text());completion=json.loads((job/'completion.json').read_text())
    require(completion['passed'] is True and completion['errors']==[] and completion['allOwnedStopped'] is True and completion['arm']==c['arm'] and completion['serverDriverMaximumParkNs']==100000 and completion['ownerPollMaximumParkNs']==c['ownerPollMaximumParkNs'] and completion['frozenReleaseSha256']==c['releaseSha256'],'Closed successful same-release round required for PASS')
    require(sha(raw/'source/release/release.json')==sha(job/'release.json')==c['releaseSha256'],'Actual release SHA differs')
    require(sha(job/'controller-source.py')==release['controllerSha256']==before['controllerSha256'],'Actual controller source differs')
    require(sha(job/'owned_linux_base_8eeb.py')==before['baseSha256']=='8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87','Actual ownership source differs')
    require(any(v['sha256']==release['controllerSha256'] for k,v in outer['files'].items() if k.startswith('source/')),'Frozen source whitelist omits actual controller')
    archive=a.collection/'pilot-after-clean-stop.tar.gz';inv=after['archive']['inventory']
    require(sha(archive)==after['archive']['archive']['sha256'] and archive.stat().st_size==after['archive']['archive']['bytes'],'Nested artifact SHA/size')
    seen=set();dirs=set()
    with tarfile.open(archive,'r|gz') as t:
        for member in t:
            name=member.name.rstrip('/');p=PurePosixPath(name);require(p.parts and p.parts[0]=='idle-arm' and not p.is_absolute() and '..' not in p.parts,'Unsafe nested path')
            rel=str(PurePosixPath(*p.parts[1:]));require(rel not in seen|dirs,'Duplicate nested member')
            if member.isdir():
                row=inv['directories'][rel];require((member.mode,member.uid,member.gid)==(row['mode'],row['uid'],row['gid']),'Nested directory owner/mode');dirs.add(rel);continue
            require(member.isfile(),'Nonregular nested member');row=inv['files'][rel]
            require((member.size,member.mode,member.uid,member.gid)==(row['bytes'],row['mode'],row['uid'],row['gid']),'Nested full metadata')
            h=hashlib.sha256();f=t.extractfile(member)
            for data in iter(lambda:f.read(1024**2),b''):h.update(data)
            require(h.hexdigest()==row['sha256'],'Nested full SHA: '+rel);seen.add(rel)
            require(all(outer['files']['job/idle-arm/'+rel][k]==row[k] for k in ['bytes','sha256','mode','uid','gid']),'Nested exact outer binding')
    require(seen==set(inv['files']) and dirs==set(inv['directories']),'Nested complete file/empty-directory closure')
    out=a.out/'actual-runtime-artifacts';out.mkdir();expected={Path(k).name:v for k,v in release['artifacts'].items()};require(len(expected)==len(release['artifacts']),'Unique exact artifact names')
    jars={}
    with tarfile.open(a.collection/'full-closed-round.tar.gz','r|gz') as t:
        for member in t:
            if member.isfile() and member.name.startswith('source/release/lib/'):
                name=Path(member.name).name;require(name in expected and name not in jars and member.size==expected[name]['bytes'],'Unexpected artifact')
                data=t.extractfile(member).read();require(hashlib.sha256(data).hexdigest()==expected[name]['sha256'],'Artifact full SHA');(out/name).write_bytes(data);jars[name]=data
    require(set(jars)==set(expected),'Actual artifact closure');actual_sources=[('io.vectormatch.cluster.RetentionNodeMainV3','cluster-0.1.0-SNAPSHOT.jar'),('io.vectormatch.core.MatchingEngine','core-0.1.0-SNAPSHOT.jar'),('io.aeron.driver.MediaDriver','aeron-all-1.53.3.jar'),('org.agrona.DirectBuffer','aeron-all-1.53.3.jar')]
    h=hashlib.sha256()
    for typ,name in actual_sources:h.update(typ.encode());h.update(jars[name])
    require(h.hexdigest()==release['codeFingerprint'],'Independent actual class-source fingerprint')
    jar_entries=[]
    for name in sorted(jars):
        with zipfile.ZipFile(out/name) as z:
            names=[n for n in z.namelist() if not n.endswith('/')];require(len(names)==len(set(names)),'Duplicate ZIP entries')
            jar_entries.append({'name':name,'bytes':len(jars[name]),'sha256':hashlib.sha256(jars[name]).hexdigest(),'entries':{n:{'bytes':len(z.read(n)),'sha256':hashlib.sha256(z.read(n)).hexdigest()} for n in names}})
    stop=json.loads((job/'python-owned-stop.json').read_text());require(stop['allOwnedStopped'] is True and stop['errors']==[] and stop['forcedKill'] is False and stop['numericPidSignalFallback'] is False,'Strict owned clean stop')
    reports=stop['reports'];require(len(reports)==3 and {r['role'] for r in reports}=={'window-%d-node-%d'%(v,n) for v in WINDOWS for n in range(3)} and all(r['stopped'] for r in reports),'Three actual node stop reports required')
    parent=json.loads((job/'identity-observation-000.json').read_text());launch=json.loads((job/'parent-launch-handle.json').read_text());require(parent['role']=='pilot-parent' and parent['origin']=='independent-direct-child-proc','Actual parent exec observation')
    record=parent['kernelIdentity'];require(record['pid']==launch['pid'] and record['arguments']==launch['expectedArguments'] and record['commandSha256']==launch['expectedCommandSha256'],'Parent launch/kernel binding')
    controller=(job/'controller-source.py').read_text()
    for fragment in ['require(parent.returncode == 0','parent.wait(timeout=',"require(base.matching_identity(row['identity']) is None"]:require(fragment in controller,'Normal parent exit/absence source basis missing')
    records=reports+[{'role':'pilot-parent','record':record}];identities=[];pair=prep+'/arm-'+str(c['arm'])+'/idle-arm'
    for r in records:
        rec=r['record'];args=rec['arguments'];require(hashlib.sha256(b''.join(x.encode()+b'\0' for x in args)).hexdigest()==rec['commandSha256'],'Actual argv SHA')
        require(args[0]==release['java'] and args[args.index('-cp')+1].split(':')==(release['classPath'] if r['role']=='pilot-parent' else release['nodeClassPath']),'Actual exact classpath')
        if r['role']=='pilot-parent':require(args==controller.parent_argv(release),'Parent exact owner/server-driver/classpath arguments')
        identities.append({'role':r['role'],**rec})
    arms=[]
    for chunk in WINDOWS:
        arm=job/'idle-arm';reg=json.loads((arm/'registration.json').read_text());art=json.loads((arm/'artifact-inventory.json').read_text())
        require(reg['batchCap']==4 and reg['archiveChunkBytes']==6144 and reg['readWindow']==chunk and reg['appointedLeader']==0 and reg['ports']==42000 and reg['sync']==2 and reg['arrivals']==33792 and reg['rate']==500,'Actual fixed registration')
        require(reg['workloadPreset']=='long-cuts-33792-v1' and reg['expectedFullCommandCuts']==11
            and reg['expectedTrailingCommands']==3 and reg['equivalentFullLoadCutNumbers']==list(range(2,12)),
            'Explicit actual long workload/cut registration required')
        require(reg['codeSha256']==release['codeFingerprint'] and reg['profileSha256']==release['profileFingerprint'] and art['codeFingerprint']==release['codeFingerprint'],'Actual source/profile fingerprints')
        require([(x['type'],Path(x['path']).name) for x in art['actualFiles']]==actual_sources,'Actual runtime type-to-JAR binding')
        for x in art['actualFiles']:require(all(x[k]==release['artifacts'][x['path']][k] for k in ['bytes','sha256']),'Actual JAR inventory differs')
        require(json.loads((arm/'load/admission-plan.json').read_text())==release['derivedPlan'],'Actual common admission plan differs')
        for n in range(3):
            rec=next(x for x in identities if x['role']=='window-%d-node-%d'%(chunk,n));args=rec['arguments'];i=args.index('io.vectormatch.cluster.RetentionNodeMainV3')
            expected=[release['java'],'-Dvectormatch.retention.idleMaxParkNs='+str(c['maximumParkNs']),
                '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED',
                '-Xmx256m','-Daeron.cluster.appointed.leader.id=0','-cp',':'.join(release['nodeClassPath']),
                'io.vectormatch.cluster.RetentionNodeMainV3',str(n),pair,'42000','2',release['profileId'],reg['lineage'],
                release['profileFingerprint'],release['codeFingerprint'],'bounded-maintenance-v1']
            require(args==expected,'Exact actual node idle/full argv differs')
        arms.append({'archiveChunkBytes':6144,'readWindow':chunk,'batchCap':4,'ports':reg['ports'],'lineage':reg['lineage']})
    import types
    from idle_attestation import validate_idle_artifacts
    from cpu_owner_poll_abab import load_base
    registry=types.SimpleNamespace(records={(rec['pid'],rec['startTicks']):{'role':rec['role'],'identity':rec} for rec in identities})
    idle=validate_idle_artifacts(load_base(),job/'idle-arm',registry,c['maximumParkNs'])
    identity_map={v['role']:v for v in identities}
    owner_actual=verify_owner_bundle(c,release,job/'idle-arm',lambda p:json.loads(p.read_text()),identity_map)
    final=json.loads((job/'idle-arm/final-position.json').read_text()); log_reports=[]
    for n in range(3):
        rec=next(v for v in identities if v['role']=='window-8-node-'+str(n))
        actual_idle=json.loads((job/('idle-arm/node-%d/idle-observations/idle-000.actual.json'%n)).read_text())
        log_reports.append(classify_node_log((job/('idle-arm/node-%d.log'%n)).read_bytes(), node=n,pid=rec['pid'],
            profile=release['profileFingerprint'],lineage=arms[0]['lineage'],code=release['codeFingerprint'],
            final_hash=final['combinedSha256'],idle_actual=actual_idle))
    protected_path=raw/'source/release/current-stopped-original-state.json';require(sha(protected_path)==release['protectedOriginalState']['manifestSha256'],'Frozen protected state SHA')
    protected=json.loads(protected_path.read_text());original=json.loads(Path(c['protectedReference']).read_text())
    for x,y in zip(protected['nativeTrees'],original['nativeTrees']):
        require(x['root']==y['root'] and set(x['files'])==set(y['files']) and x['directories']==y['directories'],'Protected original native closure')
        for name,row in x['files'].items():require(all(row[k]==y['files'][name][k] for k in ['bytes','sha256','mode','uid','gid']),'Protected original native full binding')
    require(len(protected['nativeTrees'])==len(original['nativeTrees'])==3 and protected['postgres']==original['postgres'],'Three original trees/PG reference')
    require(before['protectedOriginal']==after['protectedOriginal'] and before['protectedOriginal']['passed'] is True and before['protectedOriginal']['manifestSha256']==sha(protected_path),'Wrapper protected original before/after differs')
    require(sum(len(x['files'])for x in protected['nativeTrees'])==57 and after['protectedOriginal']['postgres']['files']==989,'Exact protected57 native/PG989 files required')
    for key,previous in c['priorGates'].items():
        n=int(key)
        require(sha(raw/('source/release/arm-%d-collection-gate.json'%n))==previous['sha256']
            and sha(raw/('source/release/arm-%d-private-push.json'%n))==previous['privatePushSha256'],'Collected exact prior gate/private-push pair differs')
    if c['arm']>1:
        previous=c['priorGates'][str(c['arm']-1)]
        require(before['priorArm']['passed'] is True and before['priorArm']['gateSha256']==previous['sha256']
            and before['priorArm']['privatePushReceiptSha256']==previous['privatePushSha256'],'Actual immediate prior-arm collection/private-push gate binding')
    report={'passed':True,'arm':c['arm'],'sourceCommit':release['sourceCommit'],'releaseSha256':c['releaseSha256'],'frozenCodeFingerprintIndependentlyRecomputed':h.hexdigest(),'actualCodeSources':actual_sources,'actualJarEntries':jar_entries,'nestedFiles':len(seen),'nestedDirectories':len(dirs),'nestedLogicalBytes':inv['logicalBytes'],'nestedAllocatedBytesRecorded':inv['allocatedBytes'],'allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified':True,'allNestedFilesExactlyBoundToOuterArchive':True,'actualArguments':identities,'threeRawNodeStopReports':True,'nodeLogClassifications':log_reports,'retainedPostCheckpointEosWarningPairs':sum(v['warningPairCount'] for v in log_reports),'idleAttestation':idle,'ownerPollAttestation':owner_actual,'serverDriverMaximumParkNs':100000,'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],'normalParentExitBasis':'Successful frozen controller requires normal returncode 0, reaps direct parent and verifies registered identity absence; parent has no fourth raw stop report. Source/result reconciliation, no new live process query.','arms':arms,'commonOperationalCapsEqual':True,'protectedOriginalBeforeAfterExactlyEqual':True,'protectedNativeFiles':sum(len(x['files']) for x in protected['nativeTrees']),'protectedPgFiles':after['protectedOriginal']['postgres']['files'],'scope':'Local closed archive/artifact/lifecycle reconciliation only. Full protected-original checks performed by wrapper before/after, not independently rehashed remotely by collector.'}
    (a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n');return report

def main():
    a,c,r=audit_arguments(__doc__)
    try:
        report=audit(a,c,r);print(json.dumps({k:report[k] for k in ['passed','arm','nestedFiles','nestedDirectories','nestedLogicalBytes']},indent=2))
    except BaseException as error:
        (a.out/'failure.json').write_text(json.dumps({'passed':False,'error':repr(error),'traceback':traceback.format_exc(),'partialArtifactsRetained':True},indent=2)+'\n');raise
if __name__=='__main__':main()
