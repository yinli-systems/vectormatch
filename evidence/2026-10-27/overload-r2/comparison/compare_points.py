from pathlib import Path
import json,sys,hashlib
P=Path(__file__).resolve().parent
points={};proofs={};common=None
for rate in [7000,8000]:
 for arm in ['a1','b1','a2','b2']:
  name=f'{rate}-{arm}';folder=P/('analysis-'+name);result=json.loads((folder/'RESULT.json').read_text());environment=json.loads((folder/'environment.json').read_text());registration=json.loads((folder/'native__registration.json').read_text());proof=json.loads((P/('archive-'+name)/'PRIVATE_ASSET_VERIFIED.json').read_text())
  assert result['ratePerSecond']==rate and result['policy']==('PAUSE'if arm.startswith('a')else'CONTINUE')and result['allRawAuditAndThreeNodeColdRestorePassed']
  assert proof['authenticatedFullDownloadVerified']and proof['allOriginalMembersVerified']and proof['privateDraftRelease']==423510304
  binding={k:environment[k]for k in ['sourceCommit','bootId','hostname','cpuMax']};binding.update({k:registration[k]for k in ['code','profile','appointedLeader','syncLevel','ports','activeLoadWorkers','allocatedLogicalWorkers']})
  if common is None:common=binding
  else:assert common==binding,'comparison environment/config/artifact changed'
  points[name]=result;proofs[name]={'assetId':proof['assetId'],'sha256':proof['sha256'],'resultSha256':hashlib.sha256((folder/'RESULT.json').read_bytes()).hexdigest()}
pairs={}
for rate in [7000,8000]:
 values=[]
 for index in [1,2]:
  a=points[f'{rate}-a{index}'];b=points[f'{rate}-b{index}'];defined=bool(a['allArrivalLatency']and b['allArrivalLatency'])
  passed=defined and b['allArrivalLatency']['p99Ns']<a['allArrivalLatency']['p99Ns']and b['inWindowGoodputPerSecond']>=a['inWindowGoodputPerSecond']and b['postFirstOfferConditionalLatency']['p99Ns']<=a['postFirstOfferConditionalLatency']['p99Ns']
  values.append({'pair':index,'bothAllArrivalP99Defined':defined,'registeredDirectionCriterionPassed':bool(passed),'globalP99ReductionPercent':(100*(1-b['allArrivalLatency']['p99Ns']/a['allArrivalLatency']['p99Ns']))if defined else None,'goodputDifferencePerSecond':b['inWindowGoodputPerSecond']-a['inWindowGoodputPerSecond'],'postOfferConditionalP99ChangeNs':b['postFirstOfferConditionalLatency']['p99Ns']-a['postFirstOfferConditionalLatency']['p99Ns']})
 pairs[str(rate)]={'pairs':values,'bothPairsPass':all(v['registeredDirectionCriterionPassed']for v in values),'allFourFiniteCapacityGatesPass':all(points[f'{rate}-{arm}']['finiteGatePassed']for arm in ['a1','b1','a2','b2'])}
report={'sameEnvironmentAndArtifact':common,'points':points,'pairs':pairs,'privateEvidence':proofs,'sustainedCapacityProven':False,'productionSlaProven':False,'scope':'Two finite overload ABAB sequences; independent raw audits and all three cold restores are prerequisites. Exact results retained; no claim that failures qualify capacity.'}
out=P/'COMPARISON.json';assert not out.exists();out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(pairs))
