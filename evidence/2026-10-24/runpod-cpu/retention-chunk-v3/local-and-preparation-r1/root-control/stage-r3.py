"""Root-reviewed one-shot staging and read-only CPU preflight; never starts an application."""
import argparse,hashlib,importlib.util,json,pathlib,shlex,subprocess,tarfile

BASE=pathlib.Path(__file__).resolve().parent
PREP='/opt/vectormatch-cpu/preparation/chunk-cloud-abab-r3'
PREPARATION_SHA='c16ebf372474bf4b0818aaddb262128732fa4904787b813addb1c8c4b44f725b'
CONTROLLER_SHA='8be694cfb8e7077fc2035667352b490ca704de21da4bc10f8dc2cca738c423bd'

def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def save(path,data):
 with pathlib.Path(path).open('x') as out:json.dump(data,out,indent=2,sort_keys=True);out.write('\n')

def main():
 parser=argparse.ArgumentParser(allow_abbrev=False)
 parser.add_argument('--candidate',type=pathlib.Path,required=True)
 parser.add_argument('--candidate-sha256',required=True)
 parser.add_argument('--output',type=pathlib.Path,required=True)
 options=parser.parse_args();out=options.output.resolve();out.mkdir(mode=0o700,exist_ok=False)
 source=BASE/'chunk-cloud-abab-preparation-r3'
 assert sha(source/'LOCAL_PREPARATION_FROZEN.json')==PREPARATION_SHA
 assert sha(source/'chunk_cloud_abab.py')==CONTROLLER_SHA
 frozen=json.loads((source/'LOCAL_PREPARATION_FROZEN.json').read_text())
 files={}
 for name,row in frozen['files'].items():
  p=source/name;assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'];files[name]=p
 files['LOCAL_PREPARATION_FROZEN.json']=source/'LOCAL_PREPARATION_FROZEN.json'
 candidate=options.candidate.resolve();assert sha(candidate)==options.candidate_sha256
 success=json.loads((candidate.parent.parent/'SUCCESS.json').read_text());assert success['passed'] is True and success['candidateSha256']==options.candidate_sha256
 release=json.loads(candidate.read_text());assert release['releaseReady'] is False and release['controllerSha256']==CONTROLLER_SHA
 provenance=release['rootReview']['candidateProvenance']
 assert provenance['nativeFunctionalBinding']['passed'] is True
 assert provenance['source']['sourceCommit']==release['sourceCommit'] and provenance['source']['allCapturedSourceAndDocsMatchCommit'] is True
 release['releaseReady']=True;release['status']='ROOT_REVIEWED_FROZEN_ABAB_RELEASE_CPU_GUARDS_AND_PREFLIGHT_REQUIRED'
 release['rootReview']['rootIndependentReview']={'sourceAndLifecycleReviewed':True,'actualCandidateByteFingerprintReviewed':True,'failedNativeR1Retained':True,'nativeR2Both6400Accepted':True,'noPerformancePromotionFromLocalPair':True,'actualImageLifecycleAllowsBoundedAddRemove':True,'linuxGuardsAndReadOnlyPreflightRequired':True,'noNewResources':True}
 spec=importlib.util.spec_from_file_location('frozen_chunk_controller_review',source/'chunk_cloud_abab.py');controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller);controller.validate_release(release)
 final=out/'release.json';save(final,release);release_sha=sha(final)
 files['release/release.json']=final
 protected=candidate.parent/'current-stopped-original-state.json';assert sha(protected)==release['protectedOriginalState']['manifestSha256']
 files['release/current-stopped-original-state.json']=protected
 for remote_path,row in release['artifacts'].items():
  name=pathlib.Path(remote_path).name;p=candidate.parent/'lib'/name
  assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256'];files['release/lib/'+name]=p
 rows={name:{'bytes':p.stat().st_size,'sha256':sha(p)} for name,p in files.items()}
 bundle=out/'stage-bundle.tar.gz'
 with tarfile.open(bundle,'w:gz',compresslevel=1) as archive:
  for name,p in files.items():archive.add(p,arcname=name,recursive=False)
 spec=importlib.util.spec_from_file_location('cpu_remote',BASE/'remote.py');remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
 target=PREP+'-source.tar.gz'
 program='target_name='+repr(target)+'\n'+"import pathlib,sys,shutil,os;os.umask(0o077)\nwith pathlib.Path(target_name).open('xb') as out:shutil.copyfileobj(sys.stdin.buffer,out)"
 r=subprocess.run(remote.sshargs()+['python3 -c '+shlex.quote(program)],input=bundle.read_bytes(),capture_output=True,timeout=120)
 (out/'upload.stdout').write_bytes(r.stdout);(out/'upload.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr
 program='rows='+repr(rows)+'\nprep_name='+repr(PREP)+'\ntarget_name='+repr(target)+'\nbundle_sha='+repr(sha(bundle))+'\n'+r'''
import pathlib,hashlib,json,tarfile,os
target=pathlib.Path(target_name);assert hashlib.sha256(target.read_bytes()).hexdigest()==bundle_sha
os.umask(0o077);prep=pathlib.Path(prep_name);prep.mkdir(mode=0o700);seen=set()
with tarfile.open(str(target),'r:gz') as archive:
 for member in archive:
  assert member.isfile() and member.name in rows and member.name not in seen
  assert '..' not in pathlib.PurePosixPath(member.name).parts and not member.name.startswith('/')
  row=rows[member.name];assert member.size==row['bytes'] and member.size<32*1024**2
  raw=archive.extractfile(member).read();assert hashlib.sha256(raw).hexdigest()==row['sha256']
  path=prep/member.name;path.parent.mkdir(parents=True,exist_ok=True)
  with path.open('xb') as output:output.write(raw)
  seen.add(member.name)
assert seen==set(rows)
for name,row in rows.items():
 raw=(prep/name).read_bytes();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
print(json.dumps({'passed':True,'files':rows}))
'''
 r=remote.run('python3 -c '+shlex.quote(program),timeout=90)
 (out/'stage.stdout.json').write_text(r.stdout);(out/'stage.stderr').write_text(r.stderr);assert r.returncode==0,r.stderr
 for label,command,timeout in [('linux-guards','python3 -B '+shlex.quote(PREP+'/test_chunk_cloud_abab.py'),90),('read-only-preflight','python3 -B '+shlex.quote(PREP+'/chunk_cloud_abab.py')+' --round 1 --release-sha256 '+release_sha,240)]:
  r=remote.run(command,timeout=timeout);(out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr);assert r.returncode==0,r.stderr
 save(out/'SUCCESS.json',{'passed':True,'releaseSha256':release_sha,'stageBundleSha256':sha(bundle),'stagedFiles':rows,'linuxPureGuards':frozen['finalPureTests'],'readOnlyPreflightPassed':True,'applicationStarted':False,'resourceCreated':False})
 print(json.dumps({'passed':True,'releaseSha256':release_sha,'applicationStarted':False}))

if __name__=='__main__':main()
