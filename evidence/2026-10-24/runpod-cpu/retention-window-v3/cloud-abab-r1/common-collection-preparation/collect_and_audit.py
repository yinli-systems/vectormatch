"""Independent root-invoked closed collection runner; default validates locally, never launches workload."""
from pathlib import Path
import argparse,datetime,importlib.util,json,shutil,subprocess,sys,traceback
import build_config as b
HERE=Path(__file__).resolve().parent

def checked_config(path,expected_sha):
 path=b.reference(path,expected_sha);bound=b.read(path.parent/'CONFIG_BOUND.json');b.require(bound['passed'] is True and bound['configSha256']==expected_sha,'Config builder receipt differs');b.frozen_sources()
 stage=path.parent/'inputs/STAGE_SUCCESS.json';s,r=b.stage_inputs(stage,bound['actualStageReceiptSha256'])
 spec=importlib.util.spec_from_file_location('closed_collection_common',HERE/'frozen/common.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);c,release,expected,allow=m.load_config(path)
 b.require(c['releaseSha256']==b.RELEASE and c['remotePrep']==b.PREP and c['executionMetadata']==['round-%d-execution-register.json'%c['round'],'round-%d-execution.stdout'%c['round'],'round-%d-execution.stderr'%c['round']],'Bound release/path/opaque execution names')
 b.require(allow==bound['sourceAllowlist'] and len(expected)==23+(c['round']==2),'Exact original stage and optional prior gate only')
 return c,s,allow

def closed_proof(path,expected_sha,c):
 p=b.reference(path,expected_sha);x=b.read(p)
 b.require(x['schemaVersion']==1 and x['scope']=='ROOT_VERIFIED_CLOSED_WINDOW_CONTROLLER' and x['rootVerified'] is True,'Explicit root closed-controller receipt required')
 b.require(x['round']==c['round'] and x['frozenReleaseSha256']==b.RELEASE and x['controllerSha256']==b.CONTROLLER and x['job']==b.PREP+'/round-'+str(c['round']),'Wrong closed controller scope')
 b.require(x['controllerIdentityGone'] is True and x['allOwnedStopped'] is True,'Controller/node identity closure unconfirmed')
 return x

def preparation(expected_sha):
 p=b.reference(HERE/'LOCAL_COLLECTION_PREPARATION_FROZEN.json',expected_sha);f=b.read(p)
 for name,row in f['sourceFiles'].items():
  q=b.reference(HERE/name,row['sha256']);b.require(q.stat().st_size==row['bytes'],'Collection source size changed')
 return f

def invoke(args,output,label):
 with (output/(label+'.stdout')).open('xb') as out,(output/(label+'.stderr')).open('xb') as err:
  r=subprocess.run(args,stdout=out,stderr=err,timeout=1200)
 row={'command':args,'exitCode':r.returncode,'stdoutSha256':b.sha(output/(label+'.stdout')),'stderrSha256':b.sha(output/(label+'.stderr'))};b.save(output/(label+'-execution.json'),row);return row

def execute(config,config_sha,output,proof,proof_sha,preparation_sha):
 preparation(preparation_sha);c,s,allow=checked_config(config,config_sha);closed_proof(proof,proof_sha,c);b.require(not output.exists(),'Do not reuse an existing collection/failed attempt');output.mkdir(parents=True,mode=0o700)
 shutil.copy2(proof,output/'root-controller-closed.json');shutil.copy2(config,output/'collector-config.json');steps=[]
 b.save(output/'REGISTRATION.json',{'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'configSha256':config_sha,'controllerClosedReceiptSha256':proof_sha,'collectionPreparationSha256':preparation_sha,'round':c['round'],'frozenReleaseSha256':b.RELEASE,'sourceAllowlist':allow,'sourcePrepNeverRecursivelyCollected':True,'rootControllerClosed':True,'readOnlyRemoteCollectionOnly':True,'noWorkloadStartSignalsWritesOrPrune':True,'runnerSha256':b.sha(Path(__file__))})
 try:
  py=sys.executable;collection=output/'collection';native=output/'strict-native-audit';raw=output/'strict-raw-audit';full=output/'all-outcome-native-byte-audit';final=output/'finalized'
  steps.append(invoke([py,'-B',str(HERE/'frozen/collect_closed_round.py'),'--config',str(config),'--dest',str(collection),'--remote-helper',s['remoteHelper']['path'],'--collect-readonly'],output,'collect-readonly'))
  b.require(steps[-1]['exitCode']==0,'Read-only collection failed; preserve partial archive/tapes and inspect, no retry')
  steps.append(invoke([py,'-B',str(HERE/'verify_closed_archives.py'),'--collection',str(collection),'--output',str(full)],output,'verify-all-outcome-native-bytes'))
  for label,script,dest in [('strict-native','audit_native_artifacts.py',native),('strict-raw','audit_raw.py',raw)]:
   steps.append(invoke([py,'-B',str(HERE/'frozen'/script),'--config',str(config),'--collection',str(collection),'--out',str(dest)],output,label))
  if all(x['exitCode']==0 for x in steps):steps.append(invoke([py,'-B',str(HERE/'frozen/finalize_local_collection.py'),'--config',str(config),'--collection',str(collection),'--native-audit',str(native),'--raw-audit',str(raw),'--out',str(final)],output,'finalize-local'))
  passed=all(x['exitCode']==0 for x in steps) and len(steps)==5
  preparation(preparation_sha)
  report={'passed':passed,'round':c['round'],'frozenReleaseSha256':b.RELEASE,'steps':steps,'allFailuresAndPartialRawRetained':True,'noAutomaticRetry':True,'nextRoundAuthorized':False,'rootAttestationCreated':False,'cpuStableOrSustainedCapacityClaimed':False,'scope':'Finite12.8-second same-host functional workload. Strict closure failure remains visible; complete byte archive can pass independently of business validity.'};b.save(output/('SUCCESS.json' if passed else 'DIAGNOSTICS_ONLY.json'),report);return report
 except BaseException as e:
  b.save(output/'FAILED.json',{'passed':False,'error':repr(e),'traceback':traceback.format_exc(),'steps':steps,'allPartialRawAndFailuresRetained':True,'noAutomaticRetry':True,'nextRoundAuthorized':False});raise

def main():
 p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);p.add_argument('--config',required=True,type=Path);p.add_argument('--config-sha256',required=True);p.add_argument('--output',type=Path);p.add_argument('--controller-closed-proof',type=Path);p.add_argument('--controller-closed-sha256');p.add_argument('--preparation-sha256');p.add_argument('--collect-readonly',action='store_true');a=p.parse_args();c,s,allow=checked_config(a.config,a.config_sha256)
 if not a.collect_readonly:print(json.dumps({'localConfigValid':True,'round':c['round'],'remoteAccessed':False,'sourceAllowlist':allow,'controllerClosedProofStillRequired':True},indent=2));return
 b.require(a.output is not None and a.controller_closed_proof is not None and a.controller_closed_sha256 is not None and a.preparation_sha256 is not None,'Explicit fresh output, frozen preparation SHA and root closed-controller receipt/SHA required')
 report=execute(a.config,a.config_sha256,a.output,a.controller_closed_proof,a.controller_closed_sha256,a.preparation_sha256);print(json.dumps(report,indent=2));raise SystemExit(0 if report['passed'] else 1)
if __name__=='__main__':main()
