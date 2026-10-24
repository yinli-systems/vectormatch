#!/usr/bin/env python3
"""Local full nested closure, actual JAR/class binding, process/config and protected-state reconciliation."""
from pathlib import Path,PurePosixPath
import hashlib,json,tarfile,zipfile,traceback
from common import WINDOWS,require,sha,audit_arguments

def audit(a,c,release):
    prep=c['remotePrep'];raw=a.collection/'raw-files';job=raw/'job';outer=json.loads((a.collection/'remote-inventory.stdout.json').read_text())
    before=json.loads((job/'before.json').read_text());after=json.loads((job/'after-clean-stop.json').read_text());completion=json.loads((job/'completion.json').read_text())
    require(completion['passed'] is True and completion['errors']==[] and completion['allOwnedStopped'] is True and completion['round']==c['round'] and completion['frozenReleaseSha256']==c['releaseSha256'],'Closed successful same-release round required for PASS')
    require(sha(raw/'source/release/release.json')==sha(job/'release.json')==c['releaseSha256'],'Actual release SHA differs')
    require(sha(job/'controller-source.py')==release['controllerSha256']==before['controllerSha256'],'Actual controller source differs')
    require(sha(job/'owned_linux_base_8eeb.py')==before['baseSha256']=='8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87','Actual ownership source differs')
    require(any(v['sha256']==release['controllerSha256'] for k,v in outer['files'].items() if k.startswith('source/')),'Frozen source whitelist omits actual controller')
    archive=a.collection/'pilot-after-clean-stop.tar.gz';inv=after['archive']['inventory']
    require(sha(archive)==after['archive']['archive']['sha256'] and archive.stat().st_size==after['archive']['archive']['bytes'],'Nested artifact SHA/size')
    seen=set();dirs=set()
    with tarfile.open(archive,'r|gz') as t:
        for member in t:
            name=member.name.rstrip('/');p=PurePosixPath(name);require(p.parts and p.parts[0]=='read-window-pair' and not p.is_absolute() and '..' not in p.parts,'Unsafe nested path')
            rel=str(PurePosixPath(*p.parts[1:]));require(rel not in seen|dirs,'Duplicate nested member')
            if member.isdir():
                row=inv['directories'][rel];require((member.mode,member.uid,member.gid)==(row['mode'],row['uid'],row['gid']),'Nested directory owner/mode');dirs.add(rel);continue
            require(member.isfile(),'Nonregular nested member');row=inv['files'][rel]
            require((member.size,member.mode,member.uid,member.gid)==(row['bytes'],row['mode'],row['uid'],row['gid']),'Nested full metadata')
            h=hashlib.sha256();f=t.extractfile(member)
            for data in iter(lambda:f.read(1024**2),b''):h.update(data)
            require(h.hexdigest()==row['sha256'],'Nested full SHA: '+rel);seen.add(rel)
            require(all(outer['files']['job/read-window-pair/'+rel][k]==row[k] for k in ['bytes','sha256','mode','uid','gid']),'Nested exact outer binding')
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
    reports=stop['reports'];require(len(reports)==6 and {r['role'] for r in reports}=={'window-%d-node-%d'%(v,n) for v in WINDOWS for n in range(3)} and all(r['stopped'] for r in reports),'Six actual node stop reports required, not seven')
    parent=json.loads((job/'identity-observation-000.json').read_text());launch=json.loads((job/'parent-launch-handle.json').read_text());require(parent['role']=='pilot-parent' and parent['origin']=='independent-direct-child-proc','Actual parent exec observation')
    record=parent['kernelIdentity'];require(record['pid']==launch['pid'] and record['arguments']==launch['expectedArguments'] and record['commandSha256']==launch['expectedCommandSha256'],'Parent launch/kernel binding')
    controller=(job/'controller-source.py').read_text()
    for fragment in ['require(parent.returncode == 0','parent.wait(timeout=',"require(base.matching_identity(row['identity']) is None"]:require(fragment in controller,'Normal parent exit/absence source basis missing')
    records=reports+[{'role':'pilot-parent','record':record}];identities=[];pair=prep+'/round-'+str(c['round'])+'/read-window-pair'
    for r in records:
        rec=r['record'];args=rec['arguments'];require(hashlib.sha256(b''.join(x.encode()+b'\0' for x in args)).hexdigest()==rec['commandSha256'],'Actual argv SHA')
        require(args[0]==release['java'] and args[args.index('-cp')+1].split(':')==(release['classPath'] if r['role']=='pilot-parent' else release['nodeClassPath']),'Actual exact classpath')
        if r['role']=='pilot-parent':require(args==[release['java']]+release['parentJvmArguments']+['-cp',':'.join(release['classPath']),'io.vectormatch.cluster.RetentionCapacityAeronPilotV3',pair,'read-windows','42000'],'Parent fixed arguments')
        identities.append({'role':r['role'],**rec})
    arms=[]
    for chunk in WINDOWS:
        arm=job/'read-window-pair'/('window-'+str(chunk));reg=json.loads((arm/'registration.json').read_text());art=json.loads((arm/'artifact-inventory.json').read_text())
        require(reg['batchCap']==4 and reg['archiveChunkBytes']==6144 and reg['readWindow']==chunk and reg['appointedLeader']==0 and reg['ports']==42000 and reg['sync']==2 and reg['arrivals']==6400 and reg['rate']==500,'Actual fixed registration')
        require(reg['codeSha256']==release['codeFingerprint'] and reg['profileSha256']==release['profileFingerprint'] and art['codeFingerprint']==release['codeFingerprint'],'Actual source/profile fingerprints')
        require([(x['type'],Path(x['path']).name) for x in art['actualFiles']]==actual_sources,'Actual runtime type-to-JAR binding')
        for x in art['actualFiles']:require(all(x[k]==release['artifacts'][x['path']][k] for k in ['bytes','sha256']),'Actual JAR inventory differs')
        require(json.loads((arm/'load/admission-plan.json').read_text())==release['derivedPlans'][str(chunk)],'Actual common admission plan differs')
        for n in range(3):
            rec=next(x for x in identities if x['role']=='window-%d-node-%d'%(chunk,n));args=rec['arguments'];i=args.index('io.vectormatch.cluster.RetentionNodeMainV3')
            require('-Xmx256m' in args and '-Daeron.cluster.appointed.leader.id=0' in args and args[i+1:]==[str(n),pair+'/window-'+str(chunk),'42000','2',release['profileId'],reg['lineage'],release['profileFingerprint'],release['codeFingerprint'],'bounded-maintenance-v1'],'Actual node fixed args')
        arms.append({'archiveChunkBytes':6144,'readWindow':chunk,'batchCap':4,'ports':reg['ports'],'lineage':reg['lineage']})
    require(arms[0]['lineage']!=arms[1]['lineage'],'Separate fresh lineages')
    selected={'requestedReadWindow'};plans=release['derivedPlans']
    require({k:v for k,v in plans['1'].items() if k not in selected}=={k:v for k,v in plans['8'].items() if k not in selected},'Same common operational caps required')
    protected_path=raw/'source/release/current-stopped-original-state.json';require(sha(protected_path)==release['protectedOriginalState']['manifestSha256'],'Frozen protected state SHA')
    protected=json.loads(protected_path.read_text());original=json.loads(Path(c['protectedReference']).read_text())
    for x,y in zip(protected['nativeTrees'],original['nativeTrees']):
        require(x['root']==y['root'] and set(x['files'])==set(y['files']) and x['directories']==y['directories'],'Protected original native closure')
        for name,row in x['files'].items():require(all(row[k]==y['files'][name][k] for k in ['bytes','sha256','mode','uid','gid']),'Protected original native full binding')
    require(len(protected['nativeTrees'])==len(original['nativeTrees'])==3 and protected['postgres']==original['postgres'],'Three original trees/PG reference')
    require(before['protectedOriginal']==after['protectedOriginal'] and before['protectedOriginal']['passed'] is True and before['protectedOriginal']['manifestSha256']==sha(protected_path),'Wrapper protected original before/after differs')
    if c['round']==2:
        require(sha(raw/'source/release/round-1-collection-gate.json')==c['round1GateSha256'] and before['priorRound']['passed'] is True and before['priorRound']['gateSha256']==c['round1GateSha256'],'Actual round-2 prior collection gate binding')
    report={'passed':True,'round':c['round'],'sourceCommit':release['sourceCommit'],'releaseSha256':c['releaseSha256'],'frozenCodeFingerprintIndependentlyRecomputed':h.hexdigest(),'actualCodeSources':actual_sources,'actualJarEntries':jar_entries,'nestedFiles':len(seen),'nestedDirectories':len(dirs),'nestedLogicalBytes':inv['logicalBytes'],'nestedAllocatedBytesRecorded':inv['allocatedBytes'],'allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified':True,'allNestedFilesExactlyBoundToOuterArchive':True,'actualArguments':identities,'sixRawNodeStopReports':True,'normalParentExitBasis':'Successful frozen controller requires normal returncode 0, reaps direct parent and verifies registered identity absence; parent has no seventh raw stop report. Source/result reconciliation, no new live process query.','arms':arms,'commonOperationalCapsEqual':True,'protectedOriginalBeforeAfterExactlyEqual':True,'protectedNativeFiles':sum(len(x['files']) for x in protected['nativeTrees']),'protectedPgFiles':after['protectedOriginal']['postgres']['files'],'scope':'Local closed archive/artifact/lifecycle reconciliation only. Full protected-original checks performed by wrapper before/after, not independently rehashed remotely by collector.'}
    (a.out/'result.json').write_text(json.dumps(report,indent=2)+'\n');return report

def main():
    a,c,r=audit_arguments(__doc__)
    try:
        report=audit(a,c,r);print(json.dumps({k:report[k] for k in ['passed','round','nestedFiles','nestedDirectories','nestedLogicalBytes']},indent=2))
    except BaseException as error:
        (a.out/'failure.json').write_text(json.dumps({'passed':False,'error':repr(error),'traceback':traceback.format_exc(),'partialArtifactsRetained':True},indent=2)+'\n');raise
if __name__=='__main__':main()
