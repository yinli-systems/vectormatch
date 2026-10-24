"""Explicit root-controlled one-shot launch. Requires a hash-reviewed successful stage; never stages or retries."""
import argparse,hashlib,json,pathlib,shlex,shutil
import stage_long_cuts as stage

def validate_stage(directory,expected_sha):
 directory=stage.no_links(pathlib.Path(directory).absolute()).resolve();receipt=stage.load(stage.reference({'path':str(directory/'STAGE_SUCCESS.json'),'sha256':expected_sha}))
 stage.require(receipt['passed'] is True and receipt['readOnlyPreflightPassed'] is True and receipt['applicationStarted'] is False and receipt['resourceCreated'] is False,'Actual closed readonly stage required')
 checked=stage.validate_inputs(directory/'root-freeze.json',receipt['rootVerifiedFreezeSha256'])
 stage.require(receipt['remotePrep']==stage.PREP and receipt['controllerSha256']==checked['ready']['controllerSha256'] and receipt['protectedManifestSha256']==stage.PROTECTED_SHA,'Wrong long stage/controller/protected state')
 stage.require(receipt['linuxGuardCommands']==checked['guardGroups'] and receipt['linuxGuardTests']==sum(g['tests'] for g in checked['guardGroups']),'Actual final controller/parser Linux guards required')
 stage.require(receipt['releaseSha256']==stage.sha(directory/'release.json')==checked['gate']['readyRelease']['sha256'],'Actual stage release changed')
 stage.require(receipt['stagedFiles']==checked['rows'] and set(receipt['localSourcePaths'])==set(checked['files']),'Actual source closure changed')
 for name,row in receipt['stagedFiles'].items():
  expected=directory/'release.json' if name=='release/release.json' else checked['files'][name]
  stage.require(pathlib.Path(receipt['localSourcePaths'][name])==expected,'Stage local source path changed')
  stage.reference({'path':str(expected),'sha256':row['sha256']});stage.require(expected.stat().st_size==row['bytes'],'Actual staged source size changed')
 stage.require(stage.sha(directory/'stage-bundle.tar.gz')==receipt['stageBundleSha256'],'Reviewed bundle changed')
 return receipt,checked


def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--arm',type=int,choices=[1],required=True);p.add_argument('--staging',type=pathlib.Path,required=True);p.add_argument('--stage-success-sha256',required=True);p.add_argument('--output',type=pathlib.Path,required=True);o=p.parse_args()
 receipt,checked=validate_stage(o.staging,o.stage_success_sha256)
 out=stage.no_links(o.output.absolute());out.mkdir(mode=0o700,exist_ok=False)
 args=['/usr/bin/python3','-B',stage.PREP+'/cpu_long_cuts.py','--arm',str(o.arm),'--release-sha256',receipt['releaseSha256'],'--start-new']
 stage.save(out/'LAUNCH_ATTEMPT.json',{'arm':o.arm,'rootReviewedStageSuccessSha256':o.stage_success_sha256,'releaseSha256':receipt['releaseSha256'],'expectedArguments':args,'oneAttemptOnly':True,'remoteOutcomeInitiallyUnknown':True})
 program='prep_name='+repr(stage.PREP)+'\nrows='+repr(receipt['stagedFiles'])+'\nargs='+repr(args)+'\narm_number='+repr(o.arm)+'\nrelease_sha='+repr(receipt['releaseSha256'])+'\n'+r'''
import hashlib,json,os,pathlib,stat,subprocess,time,platform,shutil
assert platform.system()=='Linux' and platform.machine()=='x86_64' and platform.node()=='ed6c0673f5cb' and os.geteuid()==0
assert shutil.disk_usage('/opt/vectormatch-cpu').free>=1024**3
source=pathlib.Path(prep_name)
for name,row in rows.items():
 path=source/name
 for parent in (path,*path.parents):assert not parent.is_symlink()
 assert path.is_file() and path.stat().st_size==row['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'] and stat.S_IMODE(path.stat().st_mode)==row['mode']
assert not (source/('arm-'+str(arm_number))).exists(),'Arm job already exists; inspect original attempt, never resubmit'
prefix='arm-'+str(arm_number)+'-execution'
with (source/(prefix+'-register.json')).open('x') as register:
 intent={'state':'INTENT_NO_PID_YET','expectedArguments':args,'arm':arm_number,'frozenReleaseSha256':release_sha,'noResubmission':True}
 register.write(json.dumps(intent)+'\n');register.flush();os.fsync(register.fileno())
 with (source/(prefix+'.stdout')).open('xb') as output,(source/(prefix+'.stderr')).open('xb') as error:
  child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=output,stderr=error,cwd=str(source),start_new_session=True,close_fds=True)
 register.write(json.dumps({'state':'SPAWNED_IDENTITY_PENDING','pid':child.pid,'arm':arm_number,'noResubmission':True})+'\n');register.flush();os.fsync(register.fileno())
 proc=pathlib.Path('/proc')/str(child.pid);expected=b''.join(arg.encode()+b'\x00' for arg in args)
 row={'pid':child.pid,'expectedArguments':args,'startUnixNs':time.time_ns(),'arm':arm_number,'frozenReleaseSha256':release_sha,'noResubmission':True,'observedExecArgvMatches':False}
 try:
  fields=(proc/'stat').read_text().rsplit(')',1)[1].split();raw=(proc/'cmdline').read_bytes();fields2=(proc/'stat').read_text().rsplit(')',1)[1].split()
  row.update(startTicks=int(fields[19]),observedCommandSha256=hashlib.sha256(raw).hexdigest(),observedExecArgvMatches=raw==expected,stableStartTicks=fields[19]==fields2[19],observedState=fields2[0])
 except Exception as error:row['identityObservationError']=type(error).__name__+': '+str(error)
 register.write(json.dumps(row,sort_keys=True)+'\n');register.flush();os.fsync(register.fileno())
print(json.dumps(row),flush=True)
assert row.get('observedExecArgvMatches') is True and row.get('stableStartTicks') is True,'Launch outcome needs read-only inspection; never resubmit'
'''
 remote=stage.module(checked['remoteHelper'],'frozen_cpu_remote_launch');r=remote.run('python3 -c '+shlex.quote(program),timeout=45)
 (out/'launch.stdout.json').write_text(r.stdout);(out/'launch.stderr').write_text(r.stderr)
 stage.require(r.returncode==0,'Launch failed or ownership uncertain; inspect existing register, never resubmit')
 print(r.stdout)

if __name__=='__main__':main()
