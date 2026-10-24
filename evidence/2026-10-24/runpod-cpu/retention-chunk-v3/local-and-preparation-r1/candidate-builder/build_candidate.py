#!/usr/bin/env python3
"""Root-invoked LOCAL-ONLY candidate preparation; never freezes executable release or calls SSH."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import zipfile

HERE=Path(__file__).resolve().parent
NAMES=['cluster-0.1.0-SNAPSHOT.jar','core-0.1.0-SNAPSHOT.jar','aeron-all-1.53.3.jar','agrona-2.6.1.jar']
TYPES=['io.vectormatch.cluster.RetentionNodeMainV3','io.vectormatch.core.MatchingEngine','io.aeron.driver.MediaDriver','org.agrona.DirectBuffer']


def require(ok,message):
    if not ok:raise RuntimeError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1024**2),b''):h.update(data)
    return h.hexdigest()


def read(path):
    p=Path(path);require(p.is_file() and p.stat().st_size <= 4*1024**2,'Missing/unbounded input JSON')
    return json.loads(p.read_text())


def save(path,value):
    with Path(path).open('x') as stream:json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n')


def checked_file(path,row):
    p=Path(path)
    require(not any(q.is_symlink() for q in [p]+list(p.parents)), 'Input symlink path refused')
    require(p.is_file() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'Frozen file bytes/SHA differ: '+str(p))


def load_controller(preparation):
    path=preparation/'chunk_cloud_abab.py'
    freeze=read(preparation/'LOCAL_PREPARATION_FROZEN.json')
    for name,row in freeze['files'].items():checked_file(preparation/name,row)
    spec=importlib.util.spec_from_file_location('chunk_candidate_controller',str(path))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def git_source_closure(worktree,commit,manifest):
    require(len(commit)==40 and all(c in '0123456789abcdef' for c in commit),'Exact final source commit required')
    rows={}
    for name,expected in manifest['sourceSha256'].items():
        result=subprocess.run(['git','-C',str(worktree),'show',commit+':'+name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        require(result.returncode==0 and hashlib.sha256(result.stdout).hexdigest()==expected,'Captured source differs from final commit: '+name)
        rows[name]=expected
    return {'passed':True,'sourceCommit':commit,'sourcePaths':len(rows),'allCapturedSourceAndDocsMatchCommit':True}


def verify_class_jars(capture,manifest):
    captured_classes={}
    for module in ['core','cluster']:
        archive=capture/manifest['classes'][module]['zip']
        checked_file(archive,manifest['files'][archive.name])
        with zipfile.ZipFile(archive) as z:
            require(len(z.namelist())==len(set(z.namelist())),'Duplicate frozen class ZIP entry')
            observed={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.endswith('.class')}
            require(observed==manifest['classes'][module]['classSha256'],'Frozen class ZIP closure differs')
            captured_classes[module]={n:z.read(n) for n in observed}
        with zipfile.ZipFile(capture/'lib'/(module+'-0.1.0-SNAPSHOT.jar')) as z:
            require(len(z.namelist())==len(set(z.namelist())),'Duplicate JAR entry')
            observed={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.endswith('.class')}
            require(observed==manifest['classes'][module]['classSha256'],'Distribution class bytes differ from frozen native main classes')
    return captured_classes


def native_inventory_fingerprint(inventory,manifest,capture,classes):
    h=hashlib.sha256();counts={}
    require({r['type'] for r in inventory['actualFiles']}==set(TYPES),'Unexpected native anchor type')
    for typename in TYPES:
        h.update(typename.encode());rows=[r for r in inventory['actualFiles'] if r['type']==typename]
        if len(rows)==1 and rows[0]['path'].endswith('.jar'):
            row=rows[0];name=Path(row['path']).name
            require(name in NAMES,'Unknown native anchor JAR')
            frozen=capture/'lib'/name;checked_file(frozen,row)
            h.update(frozen.read_bytes());counts[typename]={'kind':'completeJar','name':name,'sha256':row['sha256']}
        else:
            module={'io.vectormatch.cluster.RetentionNodeMainV3':'cluster','io.vectormatch.core.MatchingEngine':'core'}.get(typename)
            require(module is not None,'Unexpected native class-directory anchor')
            prefix=manifest['classes'][module]['actualPath']+'/'
            require(all(r['path'].startswith(prefix) for r in rows),'Native actual class root differs from frozen capture')
            names={r['path'][len(prefix):]:r for r in rows}
            require(len(names)==len(rows) and set(names)==set(classes[module]),'Native exact main class closure differs')
            for name in sorted(names):
                row,data=names[name],classes[module][name]
                require(row['bytes']==len(data) and row['sha256']==hashlib.sha256(data).hexdigest(),'Native recorded class bytes differ')
                h.update(name.encode());h.update(data)
            counts[typename]={'kind':'completeClassDirectory','classes':len(names)}
    require(h.hexdigest()==inventory['codeFingerprint'],'Native independently reconstructed fingerprint differs')
    return {'passed':True,'actualNativeCodeFingerprint':h.hexdigest(),'anchorClosure':counts}


def verify_native_pair(pair,manifest,capture,classes,plans):
    complete=read(pair/'pair-completion.json')
    require(complete['passed'] is True and complete['archiveChunkBytes']==[3072,6144] and complete['fixedBusinessBatchCap']==4,'Actual completed chunk native pair required')
    result={}
    for chunk in [3072,6144]:
        arm=pair/('chunk-'+str(chunk));functional=read(arm/'functional-result.json');closure=read(arm/'completion.json');stop=read(arm/'owned-stop.json')
        require(functional['passed'] is True and closure['passed'] is True and closure['allOwnedStopped'] is True and stop['allOwnedStopped'] is True,'Native arm did not complete and stop')
        summary=functional['actualSourceSummary']
        require(summary['confirmedAcceptedUniqueOrders']==6400 and summary['notSent']==0 and summary['unknownFinal']==0 and summary['archiveChunkBytes']==chunk and summary['batchCap']==4,'Native source functional counters differ')
        require(read(arm/'load/admission-plan.json')==plans[str(chunk)],'Exact distribution-derived plan differs from native arm')
        inventory=read(arm/'artifact-inventory.json')
        checked=native_inventory_fingerprint(inventory,manifest,capture,classes)
        result[str(chunk)]={'functionalResultSha256':sha(arm/'functional-result.json'),'completionSha256':sha(arm/'completion.json'),'inventorySha256':sha(arm/'artifact-inventory.json'),'schedulerTimingValid':summary['schedulerTimingValid'],'fingerprint':checked}
    return {'passed':True,'pairRoot':str(pair),'pairCompletionSha256':sha(pair/'pair-completion.json'),'arms':result,'performanceComparisonOrCapacityPromotion':False}


def command(args,log):
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
    require(len(result.stdout)<=4*1024**2,'Local helper command output cap')
    Path(log).write_bytes(result.stdout)
    require(result.returncode==0,'Local metadata command failed; exact log preserved: '+str(log))


def build(options):
    output=options.output.resolve();require(not output.exists(),'Fresh output directory required; failed candidate is retained')
    require(all(root.resolve() not in output.parents and output != root.resolve() for root in [options.preparation,options.capture,options.worktree]), 'Candidate output must be outside frozen preparation/capture/worktree')
    output.mkdir(parents=True,mode=0o700)
    try:
        preparation=options.preparation.resolve();capture=options.capture.resolve();manifest_path=capture/'manifest.json'
        require(sha(manifest_path)==options.capture_sha256,'Explicit frozen artifact capture SHA differs')
        manifest=read(manifest_path);controller=load_controller(preparation)
        source=git_source_closure(options.worktree.resolve(),options.source_commit,manifest)
        require(set(manifest['jars'])==set(NAMES),'All and only frozen four runtime JARs required')
        for name in NAMES:
            checked_file(capture/'lib'/name,manifest['jars'][name]);checked_file(capture/'lib'/name,manifest['files']['lib/'+name])
        classes=verify_class_jars(capture,manifest)
        release_root=output/'release';lib=release_root/'lib';lib.mkdir(parents=True)
        for name in NAMES:shutil.copy2(capture/'lib'/name,lib/name)
        observation_root=output/'observation';observation_root.mkdir()
        java_source=observation_root/'ChunkReleaseObservationV3.java';shutil.copy2(HERE/'ChunkReleaseObservationV3.java',java_source)
        helper_classes=observation_root/'classes';helper_classes.mkdir()
        java=options.java.resolve();javac=java.parent/'javac';require(java.is_file() and javac.is_file(),'Explicit local JDK java+javac required')
        require('JAVA_VERSION="21.0.13"' in (java.parents[1]/'release').read_text(), 'Pinned local JDK21.0.13 metadata observer required')
        classpath=':'.join(str(lib/name) for name in NAMES)
        command([str(javac),'--release','21','-cp',classpath,'-d',str(helper_classes),str(java_source)],observation_root/'javac.log')
        observed_path=observation_root/'actual-distribution-observation.json'
        command([str(java),'--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED','-Xmx256m','-cp',classpath+':'+str(helper_classes),'io.vectormatch.cluster.ChunkReleaseObservationV3',str(observed_path)],observation_root/'java.log')
        observed=read(observed_path);h=hashlib.sha256();anchors=[]
        require([r['type'] for r in observed['actualSources']]==TYPES,'Actual JAR anchor order differs')
        for row in observed['actualSources']:
            p=Path(row['path']);require(p.parent==lib and p.name in NAMES and p.stat().st_size==row['bytes'],'Actual helper anchor loaded outside frozen JARs')
            h.update(row['type'].encode());h.update(p.read_bytes());anchors.append(p.name)
        require(h.hexdigest()==observed['codeFingerprint'],'Independent Python complete-JAR fingerprint differs')
        native=verify_native_pair(options.native_pair.resolve(),manifest,capture,classes,observed['plans'])
        old_path=options.previous_candidate.resolve();old=read(old_path)
        protected=old_path.parent/'current-stopped-original-state.json'
        require(sha(protected)==old['protectedOriginalState']['manifestSha256'],'Copied current original-state protection provenance differs')
        shutil.copy2(protected,release_root/'current-stopped-original-state.json')
        release=read(preparation/'release.template.json')
        release.update(sourceCommit=options.source_commit,codeFingerprint=observed['codeFingerprint'],profileFingerprint=observed['profileFingerprint'],profileId=observed['profileId'],
            java=old['java'],javaExecutableSha256=old['javaExecutableSha256'],jdkReleaseSha256=old['jdkReleaseSha256'],controllerSha256=sha(preparation/'chunk_cloud_abab.py'))
        remote_lib=controller.PREP/'release/lib'
        release['classPath']=[str(remote_lib/name) for name in NAMES]
        release['nodeClassPath']=list(dict.fromkeys(str(remote_lib/name) for name in anchors))
        release['artifacts']={str(remote_lib/name):{'bytes':(lib/name).stat().st_size,'sha256':sha(lib/name)} for name in NAMES}
        release['derivedPlans']=observed['plans'];release['protectedOriginalState']['manifestSha256']=sha(protected)
        provenance={'source':source,'captureManifest':str(manifest_path),'captureManifestSha256':sha(manifest_path),'previousCandidate':str(old_path),'previousCandidateSha256':sha(old_path),'currentProtectedSource':str(protected),'currentProtectedSourceSha256':sha(protected),
            'localMetadataJavaExecutable':str(java),'localMetadataJavaSha256':sha(java),'localMetadataJdkReleaseSha256':sha(java.parents[1]/'release'),
            'distributionObservationSha256':sha(observed_path),'nativeFunctionalBinding':native,'controllerSourceSha256':sha(preparation/'chunk_cloud_abab.py'),
            'newRemoteJdkObservationPerformed':False,'cloudAccessPerformed':False,'executableReleaseFrozen':False}
        release['rootReview']={'status':'LOCAL_CANDIDATE_ONLY_REQUIRES_INDEPENDENT_ROOT_REVIEW','candidateProvenance':provenance}
        # Check executable-shape contract on a detached validation copy; saved candidate stays false.
        validation=json.loads(json.dumps(release));validation['releaseReady']=True;controller.validate_release(validation)
        save(release_root/'release.candidate.json',release);save(output/'candidate-provenance.json',provenance)
        save(output/'SUCCESS.json',{'passed':True,'releaseReady':False,'sourceCommit':options.source_commit,'codeFingerprint':observed['codeFingerprint'],'profileFingerprint':observed['profileFingerprint'],'candidateSha256':sha(release_root/'release.candidate.json'),'cloudAccessPerformed':False,'sourcePreparationUnchanged':True})
        return output
    except BaseException as error:
        save(output/'FAILED.json',{'passed':False,'error':repr(error),'traceback':traceback.format_exc(),'cloudAccessPerformed':False,'failedDirectoryRetained':True})
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for key in ['preparation','capture','worktree','native-pair','previous-candidate','java','output']:parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--capture-sha256',required=True);parser.add_argument('--source-commit',required=True)
    options=parser.parse_args();print(build(options))

if __name__=='__main__':main()
