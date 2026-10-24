import hashlib,json,csv,stat,sys,datetime,math
from pathlib import Path
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';A=B/'long-native-audit-preparation-r1';N=B/'retention-long-cuts-v3-worktree/runtime/long-cuts-local-validation/native-r1';O=B/'long-cuts-root-native-review-r1'
sys.dont_write_bytecode=True;sys.path.insert(0,str(A/'source'));import archive_closure
sha=archive_closure.sha

def need(v,m):
 if not v:raise AssertionError(m)
def js(p):return json.loads(p.read_text())
result=A/'audit-r2/result.json';need(sha(result)=='68d3cda87612b9c7369c20558f474b75b6c77b890fc32d1a2cdbdb223824161a','audited result pin');v=js(result)
need(v['readOnlyAuditPassed']is True and v['originalSchedulerTimingValid']is False and v['lateOver20ms']==26 and v['capacityClaimed']is False,'qualified result')
need(v['sourceCommit']=='bcf49c10b77a14708b53d3fc6c115a6a3b834408'and v['actualCodeFingerprintIndependentlyRecomputed']=='6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8','source identity')
f=A/'SOURCE_FROZEN_FOR_REVIEW_R3.json';need(sha(f)=='8b9da7bc0de3ee3fa6e07cf622628436c153398cd29242e5d90d7ab45cb380d7','reviewed R3 source')
for name,r in js(f)['files'].items():need(sha(A/name)==r['sha256']and(A/name).stat().st_size==r['bytes'],'source '+name)
mp=N/'closed-originals/manifest.json';need(sha(mp)=='b6239c05b7949f844971f2b1dd6e416ba2ce80769eff245623ad4405bacacea7','manifest');m=js(mp)
readback=archive_closure.verify_archive(N/'closed-originals/native-originals.tar.gz',m,'b73ad6c3333007f6938eb6989ab528461d83b17b6d3ab0170d6d805e5c56cc3b')
by={r['path'][len('native/'):]:r for r in m['entries']if r['type']=='file'}
need(len(v['auditorInputs'])==80,'80 inputs')
for name,r in v['auditorInputs'].items():
 p=N/name;s=p.lstat();e=by[name]
 need(stat.S_ISREG(s.st_mode)and s.st_size==r['bytes']==e['bytes']and sha(p)==r['sha256']==e['sha256']and(stat.S_IMODE(s.st_mode),s.st_uid,s.st_gid)==(e['mode'],e['uid'],e['gid']),'input '+name)
arm=N/'arm-100000-long-cuts';rows=list(csv.DictReader((arm/'load/arrivals.csv').open()));need(len(rows)==33792,'33k rows');ids=set();cmds=set();lat=[];late=within=0
for i,r in enumerate(rows):
 need(int(r['arrival_index'])==i and int(r['scheduled_offset_ns'])==i*2000000 and int(r['worker'])==i%128 and r['producer']=='load-w'+str(i%128)and int(r['request_seq'])==1+i//128,'schedule/identity')
 need(r['status']=='APPLIED'and r['result_code']=='ACCEPTED'and r['reply_replayed']=='false'and r['unknown_observed_offset_ns']==''and r['not_sent_reason']=='0'and r['initial_server_admission_status']=='','terminal')
 ids.add(int(r['order_id']));cmds.add(int(r['command_seq']));end=int(r['reply_completion_offset_ns']);lat.append(end-int(r['scheduled_offset_ns']));within+=end<=67584000000;late+=int(r['arrival_offset_ns'])-int(r['scheduled_offset_ns'])>20000000
need(ids==set(range(2,33794))and cmds==set(range(4,33796))and late==26,'unique frontiers/scheduler')
need(sorted(lat)[math.ceil(len(lat)*.99)-1]==v['arm']['rawMetrics']['allArrivalP99Ns']and within==v['arm']['rawMetrics']['acceptedOrdersInArrivalWindow'],'raw timing recompute')
need(len(v['arm']['cycles'])==12 and len(v['arm']['readPhaseBindings']['readPhases'])==24 and len(v['arm']['equivalentFullLoadCuts'])==10,'exact cuts')
need(v['setup']['hashValidation']['businessReplyHashIntentionallyEmpty']is True and v['setup']['hashValidation']['positionHashIndependentlyRederivedFromRawPositionWire']is False,'setup qualification')
ref=arm/'reference-final.bin';final=js(arm/'final-position.json');need(sha(ref)==final['combinedSha256'],'final reference bytes')
review=B/'long-cuts-root-source-review-r1/ROOT_REVIEW.json';need(sha(review)=='a9561e676b19892a58590b16fc51b6e63962261aede70858fa0d48b0d8bd23db','root source/artifact proof')
receipt={'rootReviewPassed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Qualified LOCAL CLOSED long native functional/canonical evidence; scheduler-invalid. No CPU timing/capacity result.','sourceCommit':v['sourceCommit'],'actualCodeFingerprint':v['actualCodeFingerprintIndependentlyRecomputed'],'sourceReviewSha256':sha(review),'authoritativeRawAuditSha256':sha(result),'reviewedParserFreezeSha256':sha(f),'rootFullArchiveReadback':readback,'originalInputsRehashed':80,'uniqueOriginalArrivalsIndependentlyCounted':33792,'exactMaintenanceCycles':12,'exactReadPhases':24,'homogeneousFullLoadCuts':10,'schedulerTimingValid':False,'lateOver20msIndependentlyCounted':late,'setupPositionHashIndependentRawDerivationClaimed':False,'originalFailedAuditRetained':(A/'audit-r1/failure.json').is_file(),'businessOrJavaSshExecuted':False,'performanceOrHardRealtimeClaimed':False,'finalReferenceBytesSha256':sha(ref)}
with(O/'ROOT_REVIEW.json').open('x')as f:json.dump(receipt,f,indent=2);f.write('\n')
print(json.dumps(receipt))
