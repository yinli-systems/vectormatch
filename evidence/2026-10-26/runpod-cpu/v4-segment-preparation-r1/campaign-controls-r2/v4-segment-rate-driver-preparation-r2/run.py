from pathlib import Path
import sys,json,datetime,subprocess,hashlib
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';W=B/'interbank-v4-worktree';factor='preparation';rate=4000;O=B/f'v4-segment-{factor}-rate-driver-r1';assert not O.exists()
q=json.loads((B/'v4-segment-qualification-500-q1-private-proof-r1/PRIVATE_PUSH.json').read_text());assert q['passed']and q['completeAuthenticatedAssetDownloadVerified']and q['qualifiedNativeSegmentPreparationAndAllActualBindings']
O.mkdir();(O/'REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),factor=factor,sourceSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),rate=rate,arms=['c1','d1','c2','d2'],qualificationPrivateCommit=q['commit'],serialOnly=True,noNativeRetryOrUpwardRate=True),indent=2)+'\n');(O/'executed-rate-driver.py').write_bytes(Path(__file__).read_bytes());step=0
def run(args):
 global step
 step+=1;p=O/f'step-{step:02}.log'
 with p.open('xb')as f:x=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=900)
 if x.returncode:raise RuntimeError(f'step {step} failed;no retry or next arm;'+p.read_text()[-2500:])
for arm in ['c1','d1','c2','d2']:
 if (O/'STOP_REQUESTED').exists():raise RuntimeError('Requested stop before next arm')
 if arm!='c1':
  previous={'d1':'c1','c2':'d1','d2':'c2'}[arm];proof=json.loads((B/f'v4-segment-{factor}-{rate}-{previous}-private-proof-r1/PRIVATE_PUSH.json').read_text());assert proof['passed']and proof['completeAuthenticatedAssetDownloadVerified']and proof['nextWithinRateArm']==arm
 for name in ['stage.py','launch.py']:run(['python3','-B',str(B/'v4-segment-controller-preparation-r1'/name),factor,str(rate),arm])
 run(['python3','-B',str(B/'v4-segment-point-closure-preparation-r1/finish.py'),factor,str(rate),arm])
 root=B/f'v4-segment-{factor}-{rate}-{arm}-closure-r1';v=json.loads((root/'VERIFIED.json').read_text());assert v['nativePassed']and v['independentAuditPassed']and v['analysisPassed'];assert json.loads((root/'ACTUAL_IDLE_PROOF.json').read_text())['passed'];assert json.loads((root/'ACTUAL_BATCH_FLUSH_PROOF.json').read_text())['passed'];assert json.loads((root/'ACTUAL_SEGMENT_PROOF.json').read_text())['passed']
 run(['python3','-B',str(B/'v4-segment-native-archive-preparation-r2/archive.py'),factor,str(rate),arm])
 folder=f'evidence/2026-10-26/runpod-cpu/v4-segment-preparation-r1/{factor}-{rate}-{arm}-native-r1'
 for args in [['git','-C',str(W),'add','--sparse',folder],['git','-C',str(W),'-c','gc.auto=0','-c','maintenance.auto=false','commit','-q','-m',f'Archive qualified {factor} {arm.upper()} with complete private raw evidence'],['python3',str(W/'scripts/check-new-git-blobs.py'),'--repo',str(W),'--base','HEAD^','--head','HEAD'],['git','-C',str(W),'-c','gc.auto=0','push','-q']]:run(args)
 run(['python3','-B',str(B/'v4-segment-native-private-proof-preparation-r2/verify.py'),factor,str(rate),arm])
 a=json.loads((root/'ANALYSIS.json').read_text());s=json.loads((root/'SOURCE_RESULT.json').read_text());audit=json.loads((root/'AUDIT.json').read_text())
 print(json.dumps(dict(factor=factor,completed=arm,fullRawPrivatelyVerified=True,finiteGate=a['finiteAcceptanceGate'],globalP99Ns=a['allArrivalAcceptedP99Ns'],postOfferP99Ns=a['latencyDistributionsConditionalOnAccepted']['firstPositiveOfferReturnToReply']['p99Ns'],goodput=a['arrivalWindowGoodputPerSecond'],actualBatchFlushNs=s['batchFlushSelection']['flushDelayNs'],actualSegmentMode=s['segmentPreparation']['mode'],actualReadBankPolicy=s['readBankDispatchSelection']['policy'],auditedReadYieldTurns=audit['readYieldTurns'])),flush=True)
(O/'RESULT.json').write_text(json.dumps(dict(passed=True,allFourRawPrivatelyVerified=True,allFourSafetyAndCorrectnessGatesPassed=True,noComparisonConclusionYet=True),indent=2)+'\n')
