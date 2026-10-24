import sys,hashlib,json,traceback,ast
from pathlib import Path
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;NATIVE=OUT.parent;WORK=NATIVE.parents[2];BASE=WORK.parents[3]
sys.path.insert(0,str(OUT/'source'))
import audit_raw as audit
require=audit.require
# Load only frozen native wrapper function definitions. Never execute its top-level launch code.
original=NATIVE/'run_native.py';tree=ast.parse(original.read_text());defs=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.Import,ast.ImportFrom))]
module=ast.Module(body=defs,type_ignores=[]);namespace={'__name__':'readonly_native_function_seam','JAVA':(BASE/'.tools/jdk/bin/java').resolve(),'MAX_ALLOC':589327865,'OUT':NATIVE}
exec(compile(module,str(original),'exec'),namespace)
audit.COLLECTION=NATIVE;audit.JOB=None
reports=[];instances=[];failure=None
try:
 for maximum in [1000000,100000]:
  arm=NATIVE/'arms'/f'park-{maximum}';report=audit.audit_arm(8,arm);reports.append({'maximumParkNs':maximum,**report})
  process=json.loads((NATIVE/f'arm-{maximum}-process/parent-identity.json').read_text());reg=json.loads((arm/'registration.json').read_text())
  expected_code='f78025f91f9e43ad634840b400ab04ed4ae422597c35800984e434dbd1844c8f'
  require(report['config']['actualCodeSha256']==reg['codeSha256']==expected_code,'Actual same-distribution code fingerprint differs')
  for node in range(3):
   identity=json.loads((arm/f'node-{node}-identity.json').read_text());value=json.loads((arm/f'node-{node}/idle-observations/idle-000.actual.json').read_text())
   checked=namespace['validate_idle'](value,maximum,node,identity['pid']);instances.append({'arm':maximum,**checked})
   observed=namespace['ps'](identity['pid']);require(observed['returnCode']==1 and not observed['stdout'].strip(),'Native owned node still present')
  samples=json.loads((arm/'load/transport-observations.json').read_text());require(samples,'No actual owner samples')
  for sample in samples:namespace['validate_idle'](sample['retentionIdlePolicy'],maximum,-1,process['pid'])
  instances.append({'arm':maximum,**namespace['validate_idle'](samples[-1]['retentionIdlePolicy'],maximum,-1,process['pid']),'sampleCount':len(samples)})
 warnings=[{'maximumParkNs':r['maximumParkNs'],'node':n['member'],**n['postSnapshotWarningClassification']} for r in reports for n in r['nodeLogs'] if n['postSnapshotWarningClassification']['warningCount']]
 require(len(warnings)==2 and all(w['maximumParkNs']==100000 and w['node'] in (1,2) for w in warnings),'Observed warning inventory differs from frozen attempt')
 require(sum(i['factoryCreations'] for i in instances)==44,'Both arms must attest22 creations each')
 result={'readOnlyAuditPassed':True,'originalStrictOuterGateStillFailed':True,'rootReviewAndCPUReleasePending':True,'localFunctionalOnly':True,'speedupOrCapacityClaimed':False,'hardRealtimeGuaranteed':False,'codeFingerprint':expected_code,'arms':reports,'actualConfiguredInstanceWitnesses':instances,'warningsRetained':warnings,'warningAfterSigtermTimestampIndependentlyProven':False,'auditorInputs':audit.INPUTS,'baselineAdaptationScope':'See SOURCE_PROVENANCE.json and exact adaptation.diff; no raw input or original failed gate was changed.'}
except BaseException:
 result={'readOnlyAuditPassed':False,'originalStrictOuterGateStillFailed':True,'traceback':traceback.format_exc(),'completedArmReports':reports,'auditorInputs':audit.INPUTS};failure=True
p=OUT/'result.json'
with p.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({'passed':result['readOnlyAuditPassed'],'resultSha256':hashlib.sha256(p.read_bytes()).hexdigest(),'completedArms':len(reports),'inputs':len(audit.INPUTS),'warningCounts':len(result.get('warningsRetained',[]))}),flush=True)
if failure:print(result['traceback']);raise SystemExit(1)
