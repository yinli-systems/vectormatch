from pathlib import Path
import datetime,hashlib,json,subprocess,sys,time,traceback
HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parents[3]
PROOF=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-long-cuts-v3/cloud-long-cut-analysis-r1'
RAW=PROOF.parent/'cloud-long-r1'
SOURCE=PROOF/'long-cut-backlog-preparation-r1/cut_backlog.py'
CONFIG=PROOF/'REPRODUCTION_CONFIG.json'
ORIGINAL=PROOF/'long-cut-backlog-preparation-r1/actual-analysis-attempt-r2/derived/result.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def row(p):
 s=p.stat();return {'bytes':s.st_size,'sha256':sha(p),'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid}
def save(name,value):
 with(HERE/name).open('x')as f:json.dump(value,f,indent=2);f.write('\n')
def snapshot(config):
 return {'analyzer':row(SOURCE),'config':row(CONFIG),'originalResult':row(ORIGINAL),'rawArchiveClosure':{n:row(RAW/n)for n in ['CLOSED.json','INVENTORY.json']},'inputs':{name:{'path':pin['path'],**row(Path(pin['path']))}for name,pin in config['inputs'].items()}}
def main():
 assert sha(SOURCE)=='93d370b126eb743a6bdc98f2c53eec521895a3724710d150827303315fbe2cab'
 assert sha(ORIGINAL)=='b04a9bb0522ecea58813f8d539ca02eb240e7cc19112ff91236a7626d45ba80a'
 config=json.loads(CONFIG.read_text());before=snapshot(config)
 assert len(config['inputs'])==18
 for name,pin in config['inputs'].items():assert all(before['inputs'][name][k]==pin[k]for k in ['bytes','sha256'])
 save('INPUTS_BEFORE.json',before)
 argv=[sys.executable,'-B',str(SOURCE),'--config',str(CONFIG),'--config-sha256',sha(CONFIG),'--output',str(HERE/'derived')]
 save('REGISTRATION.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':argv,'analyzerSourceSha256':sha(SOURCE),'configSha256':sha(CONFIG),'originalResultSha256':sha(ORIGINAL),'runnerSha256':sha(Path(__file__)),'scope':'ONE authorized LOCAL read-only portable reproduction of unchanged finite analyzer against closed18archived inputs; no raw copies/Java/SSH/Git/cloud'})
 started=time.monotonic()
 try:
  with(HERE/'stdout.log').open('xb')as out,(HERE/'stderr.log').open('xb')as err:r=subprocess.run(argv,stdout=out,stderr=err,timeout=60)
  save('EXECUTION.json',{'exitCode':r.returncode,'elapsedSeconds':time.monotonic()-started,'argv':argv})
  assert r.returncode==0,'Original failed subprocess/source/logs retained; no retry'
  after=snapshot(config);save('INPUTS_AFTER.json',after);assert before==after,'Immutable inputs/source changed'
  reproduced_path=HERE/'derived/result.json';actual=json.loads(reproduced_path.read_text());original=json.loads(ORIGINAL.read_text())
  assert set(actual)==set(original)
  paths={}
  for key in original['inputClosure']:
   old,new=original['inputClosure'][key],actual['inputClosure'][key];assert {k:v for k,v in old.items()if k!='path'}=={k:v for k,v in new.items()if k!='path'}
   paths[key]={'originalPath':old['path'],'archivedPath':new['path'],'bytes':old['bytes'],'sha256':old['sha256']}
  def normalized(value):
   result=json.loads(json.dumps(value));result.pop('configSha256')
   for key in result['inputClosure']:result['inputClosure'][key]['path']='<same-input-payload:'+key+'>'
   return result
  a,b=normalized(actual),normalized(original);assert a==b,'Non-path/non-configSHA field mismatch'
  canonical=json.dumps(a,sort_keys=True,separators=(',',':')).encode()
  comparison={'passed':True,'originalResultSha256':sha(ORIGINAL),'reproducedResultSha256':sha(reproduced_path),'originalConfigSha256':original['configSha256'],'relocatedConfigSha256':actual['configSha256'],'onlyAllowedDifferenceFields':['configSha256','inputClosure.<each18key>.path'],'allOtherFieldsExactlyEqualIncludingInputBytesAndSha':True,'fullNormalizedObjectSha256':hashlib.sha256(canonical).hexdigest(),'inputBindings':paths,'actualAnalyzerExecutions':1,'allSourceConfigOriginalAnd18InputsUnchanged':True,'rawArchiveClosureUnchanged':True,'newRawAuditorOrRootBucketCalculationExecuted':False,'noRawPayloadCopied':True,'noJavaSshGitCloudAction':True}
  save('RESULT_COMPARISON.json',comparison)
  save('CLOSED.json',{'passed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'resultSha256':sha(reproduced_path),'comparisonSha256':sha(HERE/'RESULT_COMPARISON.json'),'inputBeforeAfterExactlyEqual':True,'singleAnalyzerExecution':True,'noCapacityPromotion':True,'scope':'Closed authorized portable reproduction; all substantive finite result fields exact'})
  print(json.dumps({'passed':True,'reproducedResultSha256':sha(reproduced_path),'comparisonSha256':sha(HERE/'RESULT_COMPARISON.json'),'closedSha256':sha(HERE/'CLOSED.json')}))
 except BaseException as error:
  save('FAILURE.json',{'passed':False,'error':repr(error),'traceback':traceback.format_exc(),'allFailuresAndInputsRetained':True,'noRetry':True});raise
if __name__=='__main__':main()
