"""LOCAL immutable candidate assembly only; no SSH/Java or releaseReady promotion."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import cpu_idle_abab as campaign

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
PINS={
 'linuxSuccess':('idle-linux-metadata-r1/SUCCESS.json','06c6189ce2662eb46483da86b8fe1a04c119e323357c2310564b87ccae2ef79d'),
 'linuxObservation':('idle-linux-metadata-r1/actual-linux-distribution-observation.json','be6e47b6697f5518a846f6e2c720681761dcb1e10231507bd0d22470c198e60f'),
 'rootSourceReview':('idle-root-source-review-r2/ROOT_SOURCE_REVIEW.json','0b4cbeb28859b41a0ef821ffd222552a0b2f76b2156294cbcf8de9a51873c027'),
 'rootNativeReview':('idle-root-native-review-r1/ROOT_NATIVE_REVIEW.json','ec2cf726e3bf90d91f77735e31a913e6c48af61011a86fc8447af6ba67854cdd'),
 'localPostCloseAudit':('latency-idle-v3-worktree/runtime/latency-idle-local-validation/native-r2/post-close-audit-r1/result.json','5e1f98fbc1dd81dd21afe0c4e5cd99cec5c5f606fd941cd86ce2919c830c0f7d'),
 'unitCompletion':('latency-idle-v3-worktree/runtime/latency-idle-local-validation/units-r4/completion.json','b5d027a158189950ea9be3acd2155e2192bbcc9be6e5322191c119be326d61ed'),
 'warningReview':('cpu-idle-shutdown-warning-review-r1/CLOSED_REVIEW.json','876b6c3b019795f1e0011a799da7e77d187ea6140af037bf3caa11afdbab3419')}


def assemble():
    out=HERE/'candidate';out.mkdir(mode=0o700)
    proofs=out/'proof-inputs';proofs.mkdir();sources={};bound={}
    for key,(relative,expected) in PINS.items():
        source=BASE/relative;data=source.read_bytes();assert hashlib.sha256(data).hexdigest()==expected
        (proofs/(key+'.json')).write_bytes(data);bound[key]=json.loads(data)
        sources[key]={'path':str(source),'bytes':len(data),'sha256':expected}
    linux=bound['linuxObservation'];assert bound['linuxSuccess']['passed'] is True
    assert bound['rootSourceReview']['passed'] is True
    assert linux['codeFingerprint']=='f78025f91f9e43ad634840b400ab04ed4ae422597c35800984e434dbd1844c8f'
    assert linux['commonOperationalEnvelopesExact'] is True and linux['noDriverOrClusterStarted'] is True
    remote_path=BASE/'idle-linux-metadata-r1/remote-receipt.json'
    remote=json.loads(remote_path.read_text());assert campaign.digest(remote_path)=='ec83e53748b757c865b77cf8692656db7f5dd68f2e82653e2d2d4b5f64086e33'
    assert remote['passed'] is True and remote['execution']['exitCode']==0 and remote['execution']['metadataJvmExited'] is True
    release=json.loads((HERE/'release.template.json').read_text());release_root=out/'release';release_root.mkdir();lib=release_root/'lib';lib.mkdir()
    artifacts={};classpath=[]
    for name in ['cluster-0.1.0-SNAPSHOT.jar','core-0.1.0-SNAPSHOT.jar','aeron-all-1.53.3.jar','agrona-2.6.1.jar']:
        source=BASE/'idle-linux-metadata-r1/inputs/lib'/name;row=remote['stagedFiles']['lib/'+name]
        assert source.stat().st_size==row['bytes'] and campaign.digest(source)==row['sha256']
        shutil.copy2(source,lib/name);path=str(campaign.PREP/'release/lib'/name)
        artifacts[path]={'bytes':row['bytes'],'sha256':row['sha256']};classpath.append(path)
    node_classpath=list(dict.fromkeys(str(campaign.PREP/'release/lib'/Path(row['path']).name) for row in linux['actualSources']))
    recomputed=hashlib.sha256()
    for row in linux['actualSources']:
        payload=(lib/Path(row['path']).name).read_bytes()
        assert hashlib.sha256(payload).hexdigest()==row['sha256']
        recomputed.update(row['type'].encode());recomputed.update(payload)
    assert recomputed.hexdigest()==linux['codeFingerprint']
    protected=BASE/'chunk-cloud-abab-candidate-r3/release/current-stopped-original-state.json'
    assert campaign.digest(protected)=='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753'
    shutil.copy2(protected,release_root/'current-stopped-original-state.json')
    release.update(status='CANDIDATE_ONLY_ROOT_FREEZE_REQUIRED',releaseReady=False,
        sourceCommit=campaign.SOURCE_COMMIT,codeFingerprint=linux['codeFingerprint'],
        profileFingerprint=linux['profileFingerprint'],profileId=linux['profileId'],
        java=remote['registration']['actualJavaExecutable'],
        javaExecutableSha256=remote['registration']['javaExecutableSha256'],jdkReleaseSha256=remote['registration']['jdkReleaseSha256'],
        classPath=classpath,nodeClassPath=node_classpath,artifacts=artifacts,derivedPlan=linux['plans']['8'],
        controllerSha256=campaign.digest(HERE/'cpu_idle_abab.py'))
    release['rootReview']={'evidenceBindings':sources,'rootFreezeCompleted':False,
        'qualifiedLocalFunctionalNative':True,'originalLocalOuterWrapperFailed':True,
        'bothLocalSchedulerTimingValidFalse':True,'warningPairsRetained':2,
        'afterSigtermWallTimeProven':False,'eventCanInitiateElection':True,
        'linuxMetadataOnlyNoCpuFunctionalOrPerformanceClaim':True}
    release['requiredEvidenceBeforeRootFreezes']=['Root independently review this r2 source/guard/candidate identity',
        'Root creates a separate ready release with all source/JAR/plan/protected SHA bindings',
        'Root explicit allowlist stage + actualLinux guards/preflight before one manual arm',
        'Each next arm requires independently collected full prior archive/raw/owned-stop receipt and root gate']
    # Schema validation is exercised only on a separate in-memory hypothetical ready
    # view. No written candidate or receipt is marked ready.
    check=dict(release);check['releaseReady']=True;campaign.validate_release(check)
    target=release_root/'release.json';target.write_text(json.dumps(release,indent=2,sort_keys=True)+'\n')
    files={str(p.relative_to(out)):{'bytes':p.stat().st_size,'sha256':campaign.digest(p)} for p in sorted(out.rglob('*')) if p.is_file()}
    receipt={'schemaVersion':2,'status':'LOCAL_CANDIDATE_ONLY_NOT_STAGED_OR_READY',
        'createdAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'releaseReady':False,
        'releaseSha256':campaign.digest(target),'controllerSha256':release['controllerSha256'],
        'codeFingerprint':release['codeFingerprint'],'profileFingerprint':release['profileFingerprint'],
        'exactFourJarClosure':artifacts,'actualClassSources':linux['actualSources'],'nodeClassPath':node_classpath,
        'actualLinuxMetadataAndCommonPlanBound':True,'files':files,'noJavaSshCloudStageOrGit':True}
    (out/'CANDIDATE.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':receipt['status'],'releaseSha256':receipt['releaseSha256'],
                     'candidateSha256':campaign.digest(out/'CANDIDATE.json'),'releaseReady':False}))


if __name__=='__main__':assemble()
