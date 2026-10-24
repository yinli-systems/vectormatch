#!/usr/bin/env python3
"""LOCAL metadata-only compile/run; default preparation requires no Java execution."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,shutil,stat,subprocess,sys,time,traceback

HERE=Path(__file__).resolve().parent
VALIDATION=HERE.parent
WORK=VALIDATION.parent.parent
BASE=WORK.parents[3]
TOOLS=BASE/'.tools'
OUT=VALIDATION/'distribution-observation-r1'
SOURCE=HERE/'OwnerPollDistributionObservation.java'
SOURCE_COMMIT='977197616ade0283174f2ea6ddfaa700547f6d15'
EXPECTED_FP='23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884'
OLD_FP='6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8'
OLD=BASE/'runtime/cloud/cpu-20261024/retention-long-cuts-v3-worktree/runtime/long-cuts-local-validation/distribution-observation-r1/actual-distribution-observation.json'

def require(ok,msg):
 if not ok:raise AssertionError(msg)
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def row(p):
 s=p.stat();return {'bytes':s.st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'mode':stat.S_IMODE(s.st_mode)}
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def prepare():
 require(not OUT.exists(),'Create-new observation attempt only')
 unit=VALIDATION/'units-r2';completion=json.loads((unit/'completion.json').read_text())
 require(completion['passed']and completion['totals']=={'tests':78,'failures':0,'errors':0,'skipped':0}and not completion['nativePilotTestSelected'],'Actual scoped78-unit pass required')
 materials=json.loads((unit/'DISTRIBUTION_MATERIALS.json').read_text());require(materials['derivedCodeFingerprint']==EXPECTED_FP,'Pinned installed distribution differs')
 old=json.loads(OLD.read_text());require(old['actualCodeFingerprint']==OLD_FP,'Frozen old prospective-plan reference differs')
 OUT.mkdir();lib=OUT/'lib';lib.mkdir();shutil.copy2(SOURCE,OUT/SOURCE.name);shutil.copy2(OLD,OUT/'prior-plan-reference.json')
 jars=[]
 for name,pin in sorted(materials['artifacts'].items()):
  p=unit/'artifact-state/distribution/lib'/name;require(all(row(p)[k]==pin[k]for k in ('bytes','sha256')),'Frozen installed JAR changed')
  shutil.copy2(p,lib/name);jars.append({'path':str((lib/name).resolve()),**row(lib/name)})
 require(len(jars)==4,'Exact4JAR distribution required')
 classes=OUT/'classes';classpath=':'.join(r['path']for r in jars);jdk=TOOLS/'jdk'
 javac=[str(jdk/'bin/javac'),'-cp',classpath,'-d',str(classes),str(OUT/SOURCE.name)]
 java=[str(jdk/'bin/java'),'-Xmx128m','--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','-cp',str(classes)+':'+classpath,'io.vectormatch.cluster.OwnerPollDistributionObservation',str(OUT/'actual-distribution-observation.json')]
 save(OUT/'registration.json',{'atUtc':stamp(),'status':'PREPARED_NOT_EXECUTED','sourceCommit':SOURCE_COMMIT,'helperSource':row(OUT/SOURCE.name),'helperRunner':row(Path(__file__)),'jars':jars,'jarOrder':[Path(x['path']).name for x in jars],'jdkPath':str(jdk.resolve()),'jdkInputs':{n:row(jdk/n)for n in ('release','bin/java','bin/javac')},'commands':[javac,java],'priorPlanReference':row(OUT/'prior-plan-reference.json'),'priorPlanOriginalPath':str(OLD),'unitCompletion':row(unit/'completion.json'),'unitDistributionMaterials':row(unit/'DISTRIBUTION_MATERIALS.json'),'expectedCodeFingerprint':EXPECTED_FP,'actualOwnerRuntimeEvidenceExpected':False,'scope':'Metadata-only JVM; no owner/driver/client construction, business RPC, sockets, PG or performance/native workload'})
 print(json.dumps({'prepared':True,'registrationSha256':row(OUT/'registration.json')['sha256'],'commands':[javac,java],'JavaOrJavacExecuted':False},indent=2))

def execute(expected):
 p=OUT/'registration.json';require(row(p)['sha256']==expected,'Exact root-reviewed registration SHA required');r=json.loads(p.read_text());require(not(OUT/'execution-started.json').exists(),'No automatic resubmission')
 require(row(Path(__file__))==r['helperRunner']and row(OUT/SOURCE.name)==r['helperSource'],'Frozen metadata helper changed')
 jdk=TOOLS/'jdk';require(all(row(jdk/n)==pin for n,pin in r['jdkInputs'].items()),'Registered JDK changed')
 require(all(row(Path(j['path']))=={k:j[k]for k in ('bytes','sha256','mode')}for j in r['jars']),'Registered JAR changed')
 require(row(OUT/'prior-plan-reference.json')==r['priorPlanReference'],'Frozen plan comparison reference changed')
 env=os.environ.copy();env['JAVA_HOME']=str(jdk);save(OUT/'execution-started.json',{'atUtc':stamp(),'registrationSha256':expected,'commands':r['commands'],'metadataOnly':True})
 started=time.monotonic();steps=[]
 try:
  for label,command in zip(('javac','java'),r['commands']):
   with(OUT/(label+'.stdout')).open('xb')as stdout,(OUT/(label+'.stderr')).open('xb')as stderr:result=subprocess.run(command,cwd=OUT,env=env,stdout=stdout,stderr=stderr,timeout=60)
   steps.append({'command':command,'exitCode':result.returncode,'stdout':row(OUT/(label+'.stdout')),'stderr':row(OUT/(label+'.stderr'))});require(result.returncode==0,'Metadata '+label+' failed; preserve attempt/no retry')
  value=json.loads((OUT/'actual-distribution-observation.json').read_text());old=json.loads((OUT/'prior-plan-reference.json').read_text())
  require(value['noDriverOrClusterStarted']is True and value['ownerConstructed']is False and value['ownerRuntimeObservationAvailable']is False,'No owner/driver runtime evidence claimed')
  require(value['profileSha256']==old['profileSha256']and value['workloads']==old['workloads'],'Actual SHORT/LONG prospective plans/profile changed')
  require(value['actualCodeFingerprint']==EXPECTED_FP,'Actual JVM code fingerprint differs from exact installed distribution')
  names=['io.vectormatch.cluster.RetentionCapacityAeronPilotV3','io.vectormatch.cluster.RetentionNodeMainV3','io.vectormatch.cluster.RetentionBatchOwnerV3','io.vectormatch.cluster.RetentionOwnerPollPolicyV3','io.vectormatch.core.MatchingEngine','io.aeron.driver.MediaDriver','org.agrona.DirectBuffer']
  sources=value['actualCodeSources'];require([s['class']for s in sources]==names,'Actual7ClassSource coverage differs')
  for source in sources:
   name=Path(source['path']).name;expected_jar=next(j for j in r['jars']if Path(j['path']).name==name)
   require(source['path']==expected_jar['path']and all(source[k]==expected_jar[k]for k in ('bytes','sha256')),'Actual CodeSource not one of frozen4JARs')
  require(value['ownerPollAbsentSelection']=={'explicit':False}and value['ownerPollAbsentEffectiveMaximumParkNs']==1_000_000,'Legacy pure selection differs')
  for key in ('1000000','100000'):
   selected=value['ownerPollSelections'][key];require(selected=={'schema':'retention-owner-poll-selection-v1','property':'vectormatch.retention.ownerPollMaxParkNs','maximumParkNs':int(key),'factor':'owner poll requested park cap only','hardRealtimeGuaranteed':False},'Pure owner selection differs')
  require(all(row(Path(j['path']))=={k:j[k]for k in ('bytes','sha256','mode')}for j in r['jars'])and row(OUT/SOURCE.name)==r['helperSource']and row(Path(__file__))==r['helperRunner'],'Metadata inputs changed during execution')
  require(all(row(jdk/n)==pin for n,pin in r['jdkInputs'].items()),'JDK changed during execution')
  helper_classes=[{'path':str(q),**row(q)}for q in sorted((OUT/'classes').rglob('*'))if q.is_file()]
  require([Path(q['path']).relative_to(OUT/'classes').as_posix()for q in helper_classes]==['io/vectormatch/cluster/OwnerPollDistributionObservation.class'],'Exact single compiled helper class required')
  report={'passed':True,'atUtc':stamp(),'steps':steps,'elapsedSeconds':time.monotonic()-started,'sourceCommit':SOURCE_COMMIT,'actualCodeFingerprint':value['actualCodeFingerprint'],'profileSha256':value['profileSha256'],'observation':row(OUT/'actual-distribution-observation.json'),'helperClasses':helper_classes,'allMetadataInputsUnchanged':True,'plansEqualPriorSHORTandLONG':True,'actualClassSources':7,'metadataJvmExited':True,'noNativeExecution':True,'ownerRuntimeObservationAvailable':False,'scope':'Actual metadata-only installed-JAR JVM attestation, not constructed owner/native/performance evidence'}
  save(OUT/'completion.json',report);print(json.dumps(report,indent=2))
 except BaseException as error:
  save(OUT/'failure.json',{'atUtc':stamp(),'error':repr(error),'traceback':traceback.format_exc(),'steps':steps,'preserveAllInputsAndPartialOutputs':True,'automaticRetry':False});raise

def main():
 p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);m=p.add_mutually_exclusive_group(required=True);m.add_argument('--prepare-only',action='store_true');m.add_argument('--execute',action='store_true');p.add_argument('--registration-sha256');a=p.parse_args()
 if a.prepare_only:prepare()
 else:require(a.registration_sha256 is not None,'Explicit immutable registration SHA required');execute(a.registration_sha256)

if __name__=='__main__':main()
