#!/usr/bin/env python3
"""Archive only explicitly named, closed local stage/launch metadata. No network, Java, Git or extraction."""
from pathlib import Path,PurePosixPath
import argparse,datetime,hashlib,json,os,re,shutil,stat,tarfile

LIMIT=32*1024**2
STAGE_NAMES={'root-freeze.json','release.json','stage-bundle.tar.gz','metadata-prerequisite.stdout','metadata-prerequisite.stderr','upload.stdout','upload.stderr','stage.stdout.json','stage.stderr','linux-guards.stdout','linux-guards.stderr','read-only-preflight.stdout','read-only-preflight.stderr','STAGE_SUCCESS.json'}
DRAFT_NAMES={'LOCAL_DRAFT_FROZEN.json','README.md','ROOT_FREEZE.template.json','stage_window_cloud.py','launch_window_cloud.py','test_stage_launch.py','guards-attempt-r1/registration.json','guards-attempt-r1/completion.json','guards-attempt-r1/stdout','guards-attempt-r1/stderr','guards-attempt-r1/source-copy-receipt.json','guards-attempt-r1/source-observed-after-run/ROOT_FREEZE.template.json','guards-attempt-r1/source-observed-after-run/stage_window_cloud.py','guards-attempt-r1/source-observed-after-run/launch_window_cloud.py','guards-attempt-r1/source-observed-after-run/test_stage_launch.py'}
PEER_NAMES={'ACTUAL_INPUT_BINDINGS.json','LAUNCH_REVIEW.json','REVIEW_COMPLETE.json','STAGE_ONLY_REVIEW.json','launch-source/launch_window_cloud.py','stage-only-source/stage_window_cloud.py'}

def require(x,message):
 if not x:raise ValueError(message)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def read(p):
 p=Path(p)
 for x in (p,*p.parents):require(not x.is_symlink(),'Symlink refused: '+str(x))
 require(p.is_file() and p.stat().st_size<=LIMIT,'Regular bounded file required: '+str(p));return p.read_bytes()
def js(p):return json.loads(read(p))
def reference(row):
 p=Path(row['path']);read(p);require(sha(p)==row['sha256'],'Input SHA changed: '+str(p));return p
def save(p,value):
 with Path(p).open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def state(p):
 s=p.lstat();require(stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode),'Special path refused')
 d={'type':'directory' if stat.S_ISDIR(s.st_mode) else 'file','mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
 if d['type']=='file':read(p);d.update(bytes=s.st_size,sha256=sha(p))
 return d
def paths(root):
 result={'.':state(root)}
 for current,dirs,files in os.walk(root,followlinks=False):
  for name in sorted(dirs+files):
   p=Path(current)/name;result[p.relative_to(root).as_posix()]=state(p)
 require(len(result)<=256,'Metadata path count bound');return result
def add_group(groups,label,root,names):
 require(not PurePosixPath(label).is_absolute() and '..' not in PurePosixPath(label).parts,'Unsafe archive group label')
 root=Path(root);snapshot=paths(root)
 require({n for n,row in snapshot.items() if row['type']=='file'}==set(names),'Unlisted/missing closed metadata in '+label)
 groups[label]=(root,snapshot)

def collect(config,destination):
 require(not destination.exists(),'Fresh archive destination required')
 stage_dir=Path(config['stageDirectory']);success_path=reference(config['stageSuccess']);require(success_path==stage_dir/'STAGE_SUCCESS.json','Wrong stage success path')
 success=js(success_path)
 require(success['passed'] is True and success['readOnlyPreflightPassed'] is True and success['linuxGuardTests']==122 and success['applicationStarted'] is False,'Stage not successfully closed/read-only')
 execution_closed=reference(config['rootExecutionClosed']);closed=js(execution_closed)
 require(closed.get('exitCode')==0 or closed.get('passed') is True,'Root stage execution not closed successfully')
 require(execution_closed.parent==Path(config['rootExecutionDirectory']),'Wrong execution receipt root')
 require(sha(stage_dir/'release.json')==success['releaseSha256'] and sha(stage_dir/'root-freeze.json')==success['rootVerifiedFreezeSha256'],'Stage ready release/root freeze changed')
 require(sha(stage_dir/'stage-bundle.tar.gz')==success['stageBundleSha256'],'Exact stage transfer archive changed')
 require(re.search(r'Ran 122 tests in ',read(stage_dir/'linux-guards.stderr').decode()) is not None and re.search(r'\nOK\s*$',read(stage_dir/'linux-guards.stderr').decode()) is not None,'Actual122 Linux guard transcript missing')
 preflight=js(stage_dir/'read-only-preflight.stdout');require(preflight['passed'] is True and preflight['noJavaStarted'] is True and preflight['round']==1,'Actual default read-only preflight differs')
 draft=Path(config['draftDirectory']);frozen=js(draft/'LOCAL_DRAFT_FROZEN.json')
 for name,row in frozen['files'].items():require(sha(draft/name)==row['sha256'] and (draft/name).stat().st_size==row['bytes'],'Frozen draft source changed')
 registration=js(Path(config['rootExecutionDirectory'])/'registration.json')
 for name,h in registration['inputs'].items():require(sha(draft/name)==h,'Actually executed stage source differs')
 require(closed['inputsUnchanged'] is True,'Root stage inputs changed during execution')
 groups={};add_group(groups,'draft',config['draftDirectory'],DRAFT_NAMES);add_group(groups,'peer-review',config['peerReviewDirectory'],PEER_NAMES)
 add_group(groups,'root-freeze',config['rootFreezeDirectory'],{'ROOT_FREEZE.json','release.json','RECEIPT.json'})
 add_group(groups,'root-stage-execution',config['rootExecutionDirectory'],config['rootExecutionFiles'])
 stage_snapshot=paths(stage_dir);require({n for n,s in stage_snapshot.items() if s['type']=='file'}==STAGE_NAMES,'Actual stage output closure differs')
 groups['stage-output']=(stage_dir,stage_snapshot)
 for index,history in enumerate(config.get('additionalClosedFailures',[])):
  reference(history['closedReceipt']);add_group(groups,'preserved-failure-'+str(index+1),history['directory'],history['files'])
 for index,launch in enumerate(config.get('closedLaunchMetadata',[])):
  require(js(reference(launch['closedReceipt'])).get('exitCode')==0 or js(reference(launch['closedReceipt'])).get('passed') is True,'Launch metadata not closed')
  add_group(groups,launch.get('label','closed-launch-'+str(index+1)),launch['directory'],launch['files'])
 launch_reports=[]
 for launch in config.get('closedLaunchMetadata',[]):
  base=Path(launch['directory'])
  if (base/'LAUNCH_ATTEMPT.json').is_file():
   intent=js(base/'LAUNCH_ATTEMPT.json');identity=js(base/'launch.stdout.json');args=intent['expectedArguments']
   require(intent['oneAttemptOnly'] is True and identity['noResubmission'] is True and identity['observedExecArgvMatches'] is True and identity['stableStartTicks'] is True,'Actual launch ownership observation differs')
   require(identity['expectedArguments']==args and identity['frozenReleaseSha256']==intent['releaseSha256']==success['releaseSha256'] and identity['round']==intent['round'],'Actual launch release/round/argv mismatch')
   require(hashlib.sha256(b''.join(x.encode()+b'\0' for x in args)).hexdigest()==identity['observedCommandSha256'] and identity['pid']>1 and identity['startTicks']>0,'Actual launch argv SHA/startticks mismatch')
   launch_reports.append({'directory':str(base),'pidObservedAtLaunch':identity['pid'],'startTicks':identity['startTicks'],'round':identity['round'],'fullArgvSha256':identity['observedCommandSha256'],'stableKernelIdentityObserved':True,'currentProcessStateOrBenchmarkCompletionIndependentlyChecked':False})
 # Validate every transport member and bind its body to an already archived exact candidate source,
 # except the ready release, which is copied below. Never duplicate or extract candidate/JAR bodies.
 release_proof=Path(config['existingReleaseMetadataProof']);candidate=release_proof/'candidate';rows=success['stagedFiles'];members=[];seen=set()
 with tarfile.open(stage_dir/'stage-bundle.tar.gz','r|gz') as archive:
  for m in archive:
   name=m.name;p=PurePosixPath(name);require(m.isfile() and not p.is_absolute() and '..' not in p.parts and name in rows and name not in seen,'Unsafe/unlisted transfer member')
   row=rows[name];require(m.size==row['bytes'] and m.size<LIMIT and m.mode&0o777==row['mode'],'Transfer size/mode binding')
   h=hashlib.sha256();length=0
   with archive.extractfile(m) as f:
    for b in iter(lambda:f.read(1024**2),b''):h.update(b);length+=len(b)
   require(length==row['bytes'] and h.hexdigest()==row['sha256'],'Transfer full member SHA binding')
   existing=stage_dir/'release.json' if name=='release/release.json' else candidate/name if name.startswith('release/') else candidate/'preparation'/name
   require(existing.is_file() and existing.stat().st_size==length and sha(existing)==row['sha256'],'Prior archived source body differs: '+name)
   members.append({'member':name,**row,'uid':m.uid,'gid':m.gid,'alreadyArchivedBody':str(existing),'bodyReusedWithoutDuplicate':name!='release/release.json'});seen.add(name)
 require(seen==set(rows) and len(seen)==23,'Exact23 transfer member closure')
 total=sum(s.get('bytes',0) for _,inv in groups.values() for s in inv.values());require(total<64*1024**2 and shutil.disk_usage(destination.parent if destination.parent.exists() else Path.cwd()).free>1024**3,'Local copy/disk bound')
 destination.mkdir(parents=True);bindings=[]
 for label,(source,snapshot) in groups.items():
  for name,row in sorted(snapshot.items(),key=lambda x:(x[0].count('/'),x[0])):
   if label=='stage-output' and name=='stage-bundle.tar.gz':continue
   src=source if name=='.' else source/name;dst=destination/label if name=='.' else destination/label/name
   if row['type']=='directory':dst.mkdir(parents=True,exist_ok=True);dst.chmod(row['mode'])
   else:shutil.copy2(src,dst)
   require(state(dst)==row,'Copy SHA/mode/owner mismatch');bindings.append({'source':str(src),'destination':str(dst.relative_to(destination)),**row})
  current=paths(source);require(current==snapshot,'Closed source changed during copy: '+label)
  expected={n:s for n,s in snapshot.items() if not(label=='stage-output' and n=='stage-bundle.tar.gz')}
  require(paths(destination/label)==expected,'Copied file/empty-directory closure differs')
 save(destination/'COPY_BINDINGS.json',bindings)
 save(destination/'VALIDATION.json',{'passed':True,'actualLinuxGuards':122,'actualReadOnlyPreflightPassed':True,'noJavaStartedByStage':True,'rootStageExitCode':closed.get('exitCode'),'rootStageInputsUnchanged':closed['inputsUnchanged'],'stageSuccessSha256':config['stageSuccess']['sha256'],'readyReleaseSha256':success['releaseSha256'],'closedLocalLaunchObservations':launch_reports,'sourceTreesUnchangedDuringCopy':True,'allCopiedFullShaBytesModeOwnerAndEmptyDirectoryClosureVerified':True,'scope':'Closed local source/stage/launch metadata only. No remote process status, native benchmark closure, throughput or p99 claim.'})
 save(destination/'TRANSPORT_ARCHIVE_BINDINGS.json',{'stageBundleSha256':success['stageBundleSha256'],'bytes':(stage_dir/'stage-bundle.tar.gz').stat().st_size,'members':members,'all23MembersFullShaBytesModesVerified':True,'compressedArchiveCopied':False,'reason':'Bodies already archived in release-metadata-r1; ready release is copied in this proof. Original transport gzip remains unchanged locally, full SHA pinned. No claim that compressed bytes are newly archived.'})
 shutil.copy2(config['configPath'],destination/'archive-config.json');tool=destination/'archive-helper.py';shutil.copy2(Path(__file__),tool)
 # Strong known-marker review; synthetic source regex literals are reported, not silently removed.
 patterns={'private-key':rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED) PRIVATE KEY-----','github-token':rb'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b','aws-key':rb'\bAKIA[A-Z0-9]{16}\b','runpod-token':rb'\b(?:rpa|rp)_[A-Za-z0-9]{30,}\b'}
 hits=[];scan_bytes=0;scan_files=0
 for p in sorted(destination.rglob('*')):
  if p.is_file():
   b=read(p);scan_bytes+=len(b);scan_files+=1
   for kind,pat in patterns.items():
    found=list(re.finditer(pat,b))
    if found:hits.append({'path':str(p.relative_to(destination)),'kind':kind,'count':len(found)})
 require(scan_bytes<64*1024**2,'Marker review byte bound')
 save(destination/'CREDENTIAL_MARKER_REVIEW.json',{'passed':not hits,'hits':hits,'files':scan_files,'bytes':scan_bytes,'scope':'Bounded strong known markers; source/metadata only, no original PG/key/env files selected. Prior candidate/JAR bodies were separately archived/reviewed.'})
 text='''# Closed window stage and launch preparation evidence

This proof contains only exact closed local adapter drafts, peer review, root freeze/execution and actual successful stage metadata. The stage performed source upload, 122 Linux Python guards and default read-only preflight; it started no benchmark application. Optional later closed launch metadata is labeled separately and is not a benchmark completion result.

Every selected file is bound by full SHA/size/mode/uid/gid, with exact directory and empty-directory closure. Inputs are rehashed after copying. Local guard failure histories, if supplied, remain separate; no old output is replaced. Original native/PG trees, keys and environment files are excluded.

The stage transport TAR was fully streamed and every one of its 23 member bodies/modes was reconciled against STAGE_SUCCESS and exact already archived candidate/preparation/JAR bodies, plus the newly copied root-ready release. Its full compressed SHA/size are pinned in TRANSPORT_ARCHIVE_BINDINGS.json. Its duplicate compressed bytes and prior multi-MB candidate/JAR bodies are deliberately not recopied. No sparse/native extraction occurred. This is metadata/source evidence, not a new throughput/p99/100M proof.
'''
 (destination/'README.md').write_text(text)
 inv=paths(destination);save(destination/'FINAL_LOCAL_INVENTORY.json',{'selfExcluded':True,'paths':inv,'files':sum(s['type']=='file' for s in inv.values()),'directoriesIncludingRoot':sum(s['type']=='directory' for s in inv.values()),'logicalBytes':sum(s.get('bytes',0) for s in inv.values()),'freeBytes':shutil.disk_usage(destination).free})
 return {'passed':True,'proof':str(destination),'inventorySha256':sha(destination/'FINAL_LOCAL_INVENTORY.json'),'otherFiles':sum(s['type']=='file' for s in inv.values()),'otherLogicalBytes':sum(s.get('bytes',0) for s in inv.values()),'knownMarkerHits':len(hits),'noNativeOrCloudOperationPerformed':True}

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);o=p.parse_args();config=js(o.config);config['configPath']=str(o.config.resolve());result=collect(config,o.output.resolve());print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
