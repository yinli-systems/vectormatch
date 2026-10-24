#!/usr/bin/env python3
"""One new current-checkpoint maintenance attempt; no orders/ACK/PG operations. Default is read-only preflight."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
PLAN_SHA='564c74fbf9ae983f04ff0b001f66ff163f1cffdbdc2fbc746f424fac26ec61e6'
BASE_SHA='8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87'

def require(ok,why):
 if not ok:raise RuntimeError(why)
def file_sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
base_path=HERE/'original_cluster_lifecycle_base.py'
require(file_sha(base_path)==BASE_SHA,'Exact previously root-executed ownership/budget library differs')
spec=importlib.util.spec_from_file_location('original_checkpoint_owned_base',base_path)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def load_plan():
 require(file_sha(HERE/'plan.json')==PLAN_SHA,'Frozen checkpoint plan SHA differs')
 p=json.loads((HERE/'plan.json').read_text())
 require(p['host']=='ed6c0673f5cb' and sum(len(n['files']) for n in p['nodes'])==51,'Exact host/post-r1 node path closure required')
 require(p['expectedState']=={'canonicalEngineSha256':'ea7b98a23a30b5ddde84db4520e3e915fd07a73900e2c3aa41ee28c8614b5b65','commandSeq':4609,'eventSeq':6214,'marketSeq':6194,'exportedSeq':6214,'pendingEvents':0,'outboxCapacity':65536},'Actual r1 current state required')
 return p

def verify_tree(actual,expected):
 require(set(actual['files'])==set(expected['files']) and set(actual['directories'])==set(expected['directories']),'Post-r1 native file/directory closure differs')
 for name,row in expected['files'].items():require(all(actual['files'][name][k]==row[k] for k in ['bytes','sha256','mode','uid','gid']),'Post-r1 native bytes/mode/owner differs')
 for name,row in expected['directories'].items():require(all(actual['directories'][name][k]==row[k] for k in ['mode','uid','gid']),'Post-r1 native directory mode/owner differs')

def verify_reader(folder,plan):
 base.no_links(folder);expected=plan['offlineReader'];require(file_sha(folder/'PREPARATION.json')==expected['preparationManifestSha256'],'Frozen offline reader preparation differs')
 paths=list(folder.rglob('*'));require(not any(p.is_symlink() for p in paths),'Offline reader symlink refused')
 actual={str(p.relative_to(folder)) for p in paths if p.is_file()}
 expected_dirs={'.'}
 for name in expected['files']:
  expected_dirs.update(str(x) for x in Path(name).parents)
 require({str(p.relative_to(folder)) for p in [folder]+paths if p.is_dir()}==expected_dirs,'Offline reader empty-directory closure differs')
 require(actual==set(expected['files']),'Exact offline reader package closure differs')
 for rel,row in expected['files'].items():
  p=folder/rel;base.no_links(p);require(p.is_file() and p.stat().st_size==row['bytes'] and file_sha(p)==row['sha256'],'Offline reader package bytes differ')

def preflight(plan):
 require(platform.system()=='Linux' and platform.machine()=='x86_64' and socket.gethostname()==plan['host'] and os.geteuid()==0,'Exact CPU Linux host/root required')
 prep,job=Path(plan['prep']),Path(plan['job']);base.no_links(prep)
 require(prep.is_dir() and not job.exists() and not Path(plan['probeOutput']).exists(),'New registered attempt/output required; no reuse')
 require(Path(plan['java']).resolve()==Path(plan['javaReal']) and 'JAVA_VERSION="21.0.13"' in (Path(plan['javaReal']).parents[1]/'release').read_text(),'Exact original JDK required')
 base.no_links(plan['restorationReceipt']);require(file_sha(plan['restorationReceipt'])==plan['restorationReceiptSha256'],'Original immutable restore receipt changed')
 parent=plan['parentRecovery'];parent_job=Path(parent['job'])
 for rel,row in parent['files'].items():
  f=parent_job/rel;base.no_links(f);require(f.stat().st_size==row['bytes'] and file_sha(f)==row['sha256'],'Exact closed r1 parent evidence differs')
 c=json.loads((parent_job/'completion.json').read_text());require(c['passed'] and c['allOwnedStopped'] and c['result']['canonicalEngineSha256']==plan['expectedState']['canonicalEngineSha256'],'r1 parent was not successfully closed')
 base.no_links(parent['afterArchive']['path']);require(file_sha(parent['afterArchive']['path'])==parent['afterArchive']['sha256'],'Immutable r1 after-state archive differs')
 require({p.name for p in (prep/'lib').iterdir()}==set(plan['jars']),'Exact four original cluster JARs required')
 for name,digest in plan['jars'].items():base.no_links(prep/'lib'/name);require(file_sha(prep/'lib'/name)==digest,'Original cluster JAR differs')
 helper=prep/plan['helperJar']['name'];base.no_links(helper);require(helper.stat().st_size==plan['helperJar']['bytes'] and file_sha(helper)==plan['helperJar']['sha256'],'New checkpoint helper differs')
 verify_reader(prep/plan['offlineReader']['directory'],plan)
 require(shutil.disk_usage(base.ROOT).free>=plan['bounds']['minimumInitialFreeBytes'],'Initial root free below3GiB')
 require(base.memory_headroom()>=plan['bounds']['minimumMemoryHeadroomBytes'],'Memory headroom below8GiB')
 idle=base.idle_check();ports=base.port_check();trees=[]
 parent_after=json.loads((parent_job/'after-native.json').read_text())
 require([{'files':n['files'],'directories':n['directories']} for n in plan['nodes']]==[{'files':n['files'],'directories':n['directories']} for n in parent_after['inventories']],'Plan node baseline disagrees with closed r1 after-state')
 for row in plan['nodes']:
  require(file_sha(row['sourceArchive'])==row['sourceArchiveSha256'],'Original immutable source archive differs')
  actual=base.scan(row['base'],True);verify_tree(actual,row);trees.append(actual)
 pg=base.verify_pg(plan)
 return {'passed':True,'scope':'Read-only post-r1 current baseline checks; no JVM/PG/toggle started','atUtc':base.now(),'nodes':trees,'pg':pg,'idle':idle,'ports':ports,'controllerSha256':file_sha(__file__),'ownershipLibrarySha256':BASE_SHA}

def helper_argv(plan,artifacts):
 cp=':'.join(str(artifacts/'lib'/name) for name in sorted(plan['jars']))+':'+str(artifacts/plan['helperJar']['name'])
 return [plan['java'],'--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED','-Xmx128m','-cp',cp,plan['probeClass'],plan['probeOutput']]

def clean_owned(plan,owned):
 stops=[];errors=[]
 for slot in reversed(owned):
  try:
   if slot['child'].poll() is not None:stopped={'stopped':True,'alreadyExited':True,'originalChildExitCode':slot['child'].returncode}
   elif slot['record'] is None:
    identity=base.process_identity(slot['child'].pid)
    require(identity is None or identity['arguments']==slot['args'] and identity['commandSha256']==base.argv_digest(slot['args']),'Unrecorded direct child changed; no signal')
    slot['record']=identity;stopped={'stopped':True,'alreadyExited':True} if identity is None else base.stop_owned(identity,plan['bounds']['cleanStopSecondsPerProcess'])
   else:stopped=base.stop_owned(slot['record'],plan['bounds']['cleanStopSecondsPerProcess'])
   slot['child'].wait(timeout=1);stops.append(dict(stopped,role=slot['role'],exitCode=slot['child'].returncode))
  except BaseException as e:errors.append({'role':slot['role'],'type':type(e).__name__,'message':str(e)})
 return {'allOwnedStopped':len(stops)==len(owned) and not errors,'stops':stops,'errors':errors,'numericPidSignalFallback':False,'forcedKill':False,'registeredHandles':[{'role':s['role'],'pid':s['child'].pid,'arguments':s['args'],'record':s['record']} for s in owned]}

def prefix_copy(native,target,expected):
 base.no_links(native);require(native.name.endswith('-0.rec') and native.is_file() and 0<native.stat().st_size<=512*1024**2,'Bounded first recording segment required')
 limit=min(native.stat().st_size,16*1024**2);h=hashlib.sha256();first=hashlib.sha256();total=0
 with native.open('rb') as source,target.open('xb') as dest:
  while True:
   b=source.read(1024**2)
   if not b:break
   h.update(b)
   if total<limit:part=b[:limit-total];dest.write(part);first.update(part)
   elif any(b):raise RuntimeError('Nonzero data beyond bounded recording prefix')
   total+=len(b)
  dest.flush();os.fsync(dest.fileno())
 require(total==expected['bytes'] and h.hexdigest()==expected['sha256'],'Stopped recording full bytes changed while prefix copied')
 return {'path':str(target),'bytes':limit,'sha256':first.hexdigest()}

def prepare_offline(plan,job):
 base.idle_check();output=Path(plan['probeOutput']);folder=output/'offline-input';folder.mkdir(mode=0o700)
 stop=job/'owned-stop.json';stopped=json.loads(stop.read_text());require(stopped['allOwnedStopped'],'Stop proof required before prefix reads')
 shutil.copy2(stop,folder/'owned-stop.json');metadata=json.loads((output/'snapshot-metadata.json').read_text());require([x['node'] for x in metadata]==[0,1,2],'Three ordered observed metadata nodes required')
 nodes=[]
 for row,node in zip(metadata,plan['nodes']):
  state=base.scan(node['base'],True);dest=folder/('node'+str(node['node']));dest.mkdir(mode=0o700)
  log=Path(node['base'])/'cluster/recording.log';shutil.copy2(log,dest/'recording.log');observed=state['files']['cluster/recording.log'];require(file_sha(dest/'recording.log')==observed['sha256'],'Stopped metadata copy differs')
  selected=row['selected'];require(type(selected['recordingId']) is int and selected['recordingId']>=0,'Observed recording ID required')
  filename=str(selected['recordingId'])+'-0.rec';recording=Path(node['base'])/'archive'/filename;expected=state['files']['archive/'+filename];prefix=prefix_copy(recording,dest/'recording-prefix.bin',expected)
  prefix['path']=str(Path('node'+str(node['node']))/'recording-prefix.bin')
  nodes.append({'node':node['node'],'preflightMaxSnapshotEntryIndex':row['preflightMaxSnapshotEntryIndex'],'recordingLog':{'path':str(Path('node'+str(node['node']))/'recording.log'),'bytes':observed['bytes'],'sha256':observed['sha256']},'selected':selected,'recording':{'filename':filename,'bytes':expected['bytes'],'sha256':expected['sha256'],'prefix':prefix,'zeroTailBeyondPrefixVerified':True}})
 manifest={'schemaVersion':1,'scope':'STOPPED_CURRENT_ORIGINAL_CHECKPOINT','allOwnedStopped':True,'sourceRevision':plan['baseSource'],'expected':plan['expectedState'],'stopReceipt':{'path':'owned-stop.json','bytes':stop.stat().st_size,'sha256':file_sha(stop)},'nodes':nodes};base.save(folder/'manifest.json',manifest);base.idle_check();return folder/'manifest.json'

def offline_read(plan,job,artifacts,initial,phase):
 manifest=prepare_offline(plan,job);reader_root=artifacts/plan['offlineReader']['directory'];verify_reader(reader_root,plan)
 spec=importlib.util.spec_from_file_location('frozen_current_checkpoint_reader',reader_root/'read-current-checkpoints.py');module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 prepared=module.prepare_inputs(manifest,Path(plan['probeOutput'])/'offline-decoded',plan['java']);owned=[];results=[];failure=None
 try:
  require([x['node'] for x in prepared['nodes']]==[0,1,2],'Three exact offline jobs required')
  for node in prepared['nodes']:
   args=node['argv'];require(args[0]==plan['java'] and 'io.vectormatch.cluster.ReadCurrentOriginalCheckpointsR3' in args and '-Xmx128m' in args,'Exact bounded offline reader argv required')
   slot=base.launch(plan,'offline-reader-'+str(node['node']),args,owned,job);deadline=time.monotonic()+60
   while slot['child'].poll() is None:
    base.monitor(plan,[slot],initial,('offline-reader-'+str(node['node']),));require(time.monotonic()<deadline,'Offline reader exceeded observation allowance');time.sleep(0.25)
   require(slot['child'].returncode==0,'Offline current checkpoint decoder failed');results.append({'node':node['node'],'exitCode':slot['child'].returncode,'record':slot['record']})
  result=module.finish_outputs(prepared,results)
 except BaseException as e:failure=e;result=None
 finally:
  phase['cleaning']=True
  closed=clean_owned(plan,owned);base.save(job/'offline-readers-stop.json',closed)
  if not closed['allOwnedStopped']:base.save(job/'BENCHMARK_BLOCKED.json',{'reason':'Offline reader owned clean stop unconfirmed','errors':closed['errors']});raise RuntimeError('Offline reader clean stop unconfirmed; benchmark blocked')
 if failure:raise failure
 require(result is not None,'Offline aggregate result absent');return result

def execute(plan):
 before=preflight(plan);base.enable_pidfd();job=Path(plan['job']);job.mkdir(mode=0o700);base.save(job/'before.json',before)
 for name in ['original_current_checkpoint_lifecycle.py','original_cluster_lifecycle_base.py','plan.json']:shutil.copy2(HERE/name,job/name)
 artifacts=job/'artifacts';(artifacts/'lib').mkdir(parents=True)
 for name,digest in plan['jars'].items():shutil.copy2(Path(plan['prep'])/'lib'/name,artifacts/'lib'/name);require(file_sha(artifacts/'lib'/name)==digest,'Private cluster JAR copy differs')
 h=plan['helperJar']['name'];shutil.copy2(Path(plan['prep'])/h,artifacts/h);require(file_sha(artifacts/h)==plan['helperJar']['sha256'],'Private current helper differs')
 shutil.copytree(Path(plan['prep'])/plan['offlineReader']['directory'],artifacts/plan['offlineReader']['directory']);verify_reader(artifacts/plan['offlineReader']['directory'],plan)
 initial=base.allocated(plan);owned=[];errors=[];result=None;offline=None;phase={'cleaning':False};previous={}
 def interrupted(signum,frame):
  if not phase['cleaning']:raise InterruptedError('Checkpoint controller signal '+str(signum))
 for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:previous[sig]=signal.signal(sig,interrupted)
 try:
  base.idle_check();base.port_check()
  for n in range(3):base.launch(plan,'node-'+str(n),base.node_argv(plan,n,artifacts/'lib'),owned,job)
  deadline=time.monotonic()+plan['bounds']['startupSeconds']
  while True:
   base.monitor(plan,owned,initial);texts=[Path(x['log']).read_text(errors='replace') for x in owned]
   started=all('VECTOR_CLUSTER_STARTED node='+str(n) in texts[n] and 'sync=2' in texts[n] and 'VECTOR_SNAPSHOT_RESTORED hash=4450df5dc1a6662fec3c8addd55452657ee6fd1ccd0aeae92cc6dbb7e18c780b commands=4539' in texts[n] for n in range(3))
   if started and any('VECTOR_CLUSTER_ROLE role=LEADER' in t for t in texts):break
   require(time.monotonic()<deadline,'Original post-r1 startup exceeded120s');time.sleep(0.25)
  slot=base.launch(plan,'current-checkpoint-r3',helper_argv(plan,artifacts),owned,job);deadline=time.monotonic()+plan['bounds']['probeSeconds']
  while slot['child'].poll() is None:
   base.monitor(plan,owned,initial,('current-checkpoint-r3',));require(time.monotonic()<deadline,'Current checkpoint helper exceeded180s');time.sleep(0.25)
  require(slot['child'].returncode==0,'Current checkpoint helper failed; partial evidence retained');result=json.loads((Path(plan['probeOutput'])/'result.json').read_text())
  require(result['passed'] and result['canonicalEngineSha256']==plan['expectedState']['canonicalEngineSha256'] and result['commandSeq']==4609 and result['eventSeq']==6214 and result['marketSeq']==6194 and result['exportedSeq']==6214 and result['pendingEvents']==0 and result['snapshotToggleCount']==1 and result['threeNewPairedMetadataObserved'] and result['businessApplied'] is False and result['ackSent'] is False,'Actual checkpoint helper contract differs')
 except BaseException as e:errors.append({'phase':'startup-or-checkpoint','type':type(e).__name__,'message':str(e)})
 finally:
  phase['cleaning']=True;closed=clean_owned(plan,owned);base.save(job/'owned-stop.json',closed)
 if not closed['allOwnedStopped']:
  for sig,handler in previous.items():signal.signal(sig,handler)
  base.save(job/'BENCHMARK_BLOCKED.json',{'reason':'Original nodes/helper clean stop unconfirmed','errors':closed['errors']});raise RuntimeError('Owned clean shutdown unconfirmed; benchmark blocked')
 try:
  phase['cleaning']=False
  if result is not None and not errors:offline=offline_read(plan,job,artifacts,initial,phase)
 except BaseException as e:errors.append({'phase':'offline-current-checkpoints','type':type(e).__name__,'message':str(e)})
 finally:
  for sig,handler in previous.items():signal.signal(sig,handler)
 require(not (job/'BENCHMARK_BLOCKED.json').exists(),'Reader cleanup blocked; no active evidence archive')
 after=base.after_native(plan,job);base.save(job/'after-native.json',after);pg=base.verify_pg(plan);idle=base.idle_check()
 base.save(job/'completion.json',{'passed':not errors and offline is not None,'allOwnedStopped':True,'onlineResult':result,'offlineResult':offline,'errors':errors,'postPgBaselineVerified':pg,'postIdle':idle,'businessSubmitted':False,'ackSubmitted':False,'maintenanceSnapshotIntentRecorded':(Path(plan['probeOutput'])/'snapshot-intent.json').exists(),'maintenanceSnapshotToggleConfirmed':result is not None,'threeCurrentReplicaStatesProven':not errors and offline is not None,'performanceProven':False,'originalBackupsAndR1AfterArchiveRetained':True,'atUtc':base.now()})
 require(not errors and offline is not None,'Current checkpoint proof failed; closed raw evidence retained')
 return {'passed':True,'allOwnedStopped':True,'job':str(job),'scope':'Original current three-replica stopped canonical checkpoint only; no performance proof'}

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);p.add_argument('--start-new',action='store_true');args=p.parse_args(argv);plan=load_plan();print(json.dumps(execute(plan) if args.start_new else preflight(plan)),flush=True)
if __name__=='__main__':main()
