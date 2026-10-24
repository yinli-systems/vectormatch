"""Closed local pair: byte-exact SHORT baseline + sole new actual-owner gate. Never admits CPU timing."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,stat,sys,traceback
from run_native_pair import NATIVE,HERE,BASE,CODE,PROFILE,SOURCE_COMMIT,ORDER,need,js,sha,write,load_inputs,arguments,expected_node
from owner_poll_attestation import validate_owner_bundle
AUDIT=BASE/'owner-poll-native-raw-audit-r2'

def load_short():
 pins=js(HERE/'PARSER_BASELINE_BINDINGS.json')['shortSourceFiles'];old={n:sys.modules.get(n)for n in ['common','read_phase_audit','audit_raw']};mods={}
 try:
  for name in ['common','read_phase_audit','audit_raw']:
   f=HERE/'short_parser'/(name+'.py');pin=pins[name+'.py'];need(f.stat().st_size==pin['bytes']and sha(f)==pin['sha256'],'Frozen SHORT parser changed');unique='_owner_poll_short_'+name;spec=importlib.util.spec_from_file_location(unique,f);module=importlib.util.module_from_spec(spec);sys.modules[unique]=module;sys.modules[name]=module;spec.loader.exec_module(module);mods[name]=module
 finally:
  for name,module in old.items():
   if module is None:sys.modules.pop(name,None)
   else:sys.modules[name]=module
 return mods['audit_raw']

def bind_raw(parser,manifest):
 original=parser.raw
 def closed_raw(path):
  path=Path(path);key='native/'+str(path.relative_to(NATIVE));need(key in manifest,'Every consumed SHORT input must be in closedfullmanifest');r=manifest[key];st=path.lstat();need(r['type']=='file'and stat.S_ISREG(st.st_mode)and not path.is_symlink()and st.st_nlink==1,'Original regularnonlinked parserinput');need((st.st_size,st.st_mode&0o777,st.st_uid,st.st_gid)==(r['bytes'],r['mode'],r['uid'],r['gid']),'Original parserinput mode/owner/size');value=original(path);need(len(value)==r['bytes']and hashlib.sha256(value).hexdigest()==r['sha256'],'Original parserinput SHA differs');return value
 parser.raw=closed_raw

def audit(config,config_sha):
 c=load_inputs(config,config_sha);need(not AUDIT.exists(),'Preserve any priorauditattempt');AUDIT.mkdir(mode=0o700)
 capture=js(NATIVE/'closed-originals-r2/completion.json');manifest_path=NATIVE/'closed-originals-r2/manifest.json';archive=NATIVE/'closed-originals-r2/native-originals.tar.gz'
 need(capture['passed']is True and capture['fullShaModeOwnerEmptyDirectoryReadbackVerified']is True and sha(manifest_path)==capture['manifestSha256']and sha(archive)==capture['archiveSha256'],'Full closedcapture readback required before parser');manifest={r['path']:r for r in js(manifest_path)['entries']};parser=load_short();parser.COLLECTION=NATIVE;parser.JOB=NATIVE;bind_raw(parser,manifest)
 reports=[];arms=[]
 try:
  for cap in ORDER:
   root=NATIVE/('owner-'+str(cap));process=NATIVE/('owner-'+str(cap)+'-process');r=parser.audit_arm(8,root);cfg=parser.js(root/'load/configuration.json');summary=parser.js(root/'load/load-result.json');reg=parser.js(root/'registration.json');pid=js(process/'parent-identity.json')['pid'];argv=js(process/'parent-identity.json')['launchArguments'];nodes={};actuals={}
   for n in range(3):
    identity=parser.js(root/('node-%d-identity.json'%n));nodes[n]={'pid':identity['pid'],'arguments':[identity['command']]+identity['arguments']};actuals[n]=parser.js(root/('node-%d/idle-observations/idle-000.actual.json'%n))
   samples=parser.js(root/'load/transport-observations.json');attest=validate_owner_bundle(registration=reg,configuration=cfg,summary=summary,before=parser.js(root/'load/owner-before-close.json'),after=parser.js(root/'load/owner-after-close.json'),parent={'pid':pid,'arguments':argv},nodes=nodes,expected_owner_cap=cap,expected_parent_arguments=arguments(c,cap,root),expected_node_arguments={n:expected_node(c,root,reg,n)for n in range(3)},node_idle_actuals=actuals,parent_idle_actuals=[v['retentionIdlePolicy']for v in samples])
   need(cfg['actualCodeSha256']==reg['codeSha256']==CODE and cfg['profileSha256']==PROFILE,'Same actual newJAR/profile binding');need(parser.js(root/'load/admission-plan.json')==c['shortPlan'],'ActualSHORTplan');need(r['schedulerTimingValidFromRaw']==summary['schedulerTimingValid'],'Reported/localraw schedulertruthdiffers')
   reports.append({'ownerPollMaximumParkNs':cap,'actualOwnerAttestation':attest,**r});arms.append({'ownerPollMaximumParkNs':cap,'serverDriverMaximumParkNs':100000,'arrivals':6400,'accepted':r['rawMetrics']['confirmedAcceptedUniqueOrders'],'rawFunctionalPassed':True,'ownerActualAttestationPassed':attest['passed'],'schedulerTimingValid':r['schedulerTimingValidFromRaw'],'fullNativeArchiveSha256':capture['archiveSha256'],'inventorySha256':capture['manifestSha256']})
  for name,pin in dict(parser.INPUTS).items():need(hashlib.sha256(parser.raw(NATIVE/name)).hexdigest()==pin['sha256'],'Consumed input changed')
  final={'passed':True,'sourceCommit':SOURCE_COMMIT,'codeFingerprint':CODE,'profileSha256':PROFILE,'arms':reports,'auditorInputs':parser.INPUTS,'sameNewArtifact':True,'localPerformanceClaimed':False,'allInputsUnchanged':True,'localFunctionalOnly':True,'parentKernelArgvIndependentlyDecoded':False,'fullNativeArchiveSha256':capture['archiveSha256'],'inventorySha256':capture['manifestSha256'],'scope':'Closed local SHORT6400 functional/wire/phase/canonical/owner proof; schedulerinvalid retained, no A/B speedup or CPU capacity comparison'};write(AUDIT/'result.json',final)
  compact={'schemaVersion':1,'scope':'OWNER_POLL_NEW_ARTIFACT_FUNCTIONAL_PAIR','passed':True,'sourceCommit':SOURCE_COMMIT,'codeFingerprint':CODE,'profileSha256':PROFILE,'arms':arms,'sameNewArtifact':True,'localPerformanceClaimed':False,'allInputsUnchanged':True,'fullAuditResult':{'path':str(AUDIT/'result.json'),'bytes':(AUDIT/'result.json').stat().st_size,'sha256':sha(AUDIT/'result.json')},'sourceFreeze':{'path':str(HERE/'SOURCE_FROZEN_R2.json'),'bytes':(HERE/'SOURCE_FROZEN_R2.json').stat().st_size,'sha256':sha(HERE/'SOURCE_FROZEN_R2.json')}};write(AUDIT/'COMPACT_NATIVE_PROOF.json',compact);print(json.dumps({'passed':True,'compactNativeProofSha256':sha(AUDIT/'COMPACT_NATIVE_PROOF.json'),'localPerformanceClaimed':False}))
 except BaseException as e:write(AUDIT/'FAILED.json',{'passed':False,'error':repr(e),'traceback':traceback.format_exc(),'completedReports':reports,'consumedInputs':parser.INPUTS,'allOriginalsAndFailuresRetained':True,'noRetry':True,'noPerformancePromotion':True});raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--config-sha256',required=True);a=p.parse_args();audit(a.config.resolve(),a.config_sha256)
