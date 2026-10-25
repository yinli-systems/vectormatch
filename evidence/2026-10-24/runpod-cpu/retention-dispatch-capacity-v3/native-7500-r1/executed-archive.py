from pathlib import Path
import sys,json,hashlib,shutil,tarfile,datetime

R=Path.cwd();B=R/'runtime/cloud/cpu-20261024'
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'))
from scope_tar import tree,verify,sha
rate=int(sys.argv[1]);assert rate in(4000,6000,7000,7500,8000)
O=R/f'evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/native-{rate}-r1'
T=B/f'dispatch-capacity-{rate}-archive-r1';assert not O.exists()and not T.exists()
root=B/f'dispatch-capacity-{rate}-root-review-r1'
review=json.loads((root/'ROOT_REVIEW.json').read_text());raw=json.loads((root/'RAW_AUDIT.json').read_text())
ready=json.loads((root/'READINESS_REVIEW.json').read_text())
assert review['passed']and review['nativeControlPassed']and review['performanceQualified']and raw['passed']and ready['passed']
assert review['fineDispatchCapacityPreset']and raw['fineDispatchCapacityPreset']and review['dispatchOrderPolicy']==raw['dispatchOrderPolicy']=='ROTATING_CONTINUE'
assert raw['codeFingerprint']=='2b8d7594e03f8eeeef7aaf8e07db12c3bb585ba4ba67970d065c7174420fbf68'
names={
    'preparation':f'dispatch-capacity-controller-{rate}-preparation-r1',
    'source-review':f'dispatch-capacity-controller-{rate}-review-r1',
    'stage':f'dispatch-capacity-controller-{rate}-stage-r1',
    'preflight':f'dispatch-capacity-{rate}-preflight-r1',
    'launch':f'dispatch-capacity-{rate}-launch-r1',
    'collection':f'dispatch-capacity-{rate}-collection-r1',
    'root-review':f'dispatch-capacity-{rate}-root-review-r1',
    'review-execution':f'dispatch-capacity-{rate}-review-execution-r1'
}
for p in sorted(B.glob(f'dispatch-capacity-{rate}-probe-r*')):names[p.name]=p.name
shared=['dispatch-capacity-controller-generator-r1','dispatch-capacity-controller-review-preparation-r1',
    'dispatch-capacity-linux-metadata-preparation-r1','dispatch-capacity-linux-metadata-execution-r1',
    'dispatch-capacity-root-review-preparation-r1','dispatch-capacity-runner-r1',
    'dispatch-capacity-scope-tar-preparation-r1','dispatch-capacity-scope-tar-validation-r1',
    'dispatch-capacity-native-archive-preparation-r1','dispatch-capacity-native-private-proof-preparation-r1',
    'read128-capacity-lossless-package-preparation-r1',
    'current-maintained-capacity-streaming-decoder-preparation-r1',
    'current-maintained-capacity-streaming-decoder-validation-r1']
names.update({n:n for n in shared})
prior={6000:4000,7000:6000,7500:7000,8000:7500}.get(rate)
if prior:names['preceding-private-proof']=f'dispatch-capacity-{prior}-private-proof-r1'
else:names['adoption-private-proof']='dispatch-fairness-reporting-private-proof-r1'
assert json.loads((B/'dispatch-capacity-scope-tar-validation-r1/VALIDATION.json').read_text())['passed']
before={label:tree(B/name)for label,name in names.items()}
logical=sum(sum(f['bytes']for f in value['files'].values())for value in before.values())
assert logical<=12*1024**3
# This is local archival packaging. Original remote/native allocation and archive caps are unchanged.
assert shutil.disk_usage(R).free>=1024**3+min(logical,1024**3)
T.mkdir();bundle=T/'all-original-native-and-review-scopes.tar.gz'
with tarfile.open(bundle,'w:gz',compresslevel=1)as t:
    for label,name in names.items():t.add(B/name,arcname='original/'+label,recursive=True)
assert bundle.stat().st_size<=1024**3
full=verify(bundle,before)
for label,name in names.items():assert tree(B/name)==before[label]
(T/'ORIGINAL_SCOPE_INVENTORIES.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n')
(T/'VERIFIED.json').write_text(json.dumps(dict(full,archiveBytes=bundle.stat().st_size,archiveSha256=sha(bundle)),indent=2,sort_keys=True)+'\n')
O.mkdir(parents=True);shutil.copy2(bundle,O/bundle.name)
assert sha(O/bundle.name)==sha(bundle)
(O/'ORIGINAL_SCOPE_INVENTORIES.json').write_text((T/'ORIGINAL_SCOPE_INVENTORIES.json').read_text())
(O/'SOURCE_MIRRORS.json').write_text(json.dumps(dict(sources=names,archiveName=bundle.name,
    archiveBytes=bundle.stat().st_size,archiveSha256=sha(bundle),fullMemberReview=full,
    localOriginalArchive=str(bundle),allSourcesUnchanged=True),indent=2,sort_keys=True)+'\n')
# Small exact original proof/configuration bodies remain directly inspectable beside the complete TAR.
direct=['ROOT_REVIEW.json','RAW_AUDIT.json','READINESS_REVIEW.json']
direct += [f'materialized/attempt-{rate}/idle-arm/load/{n}'for n in ('configuration.json','load-result.json','admission-plan.json')]
direct += [f'materialized/attempt-{rate}/idle-arm/{n}'for n in ('registration.json','capacity-correctness-result.json')]
for n in direct:
    p=O/'root-review'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/n,p);assert sha(p)==sha(root/n)
(O/'RESULTS.json').write_text(json.dumps(dict(rootReview=review,rawAudit=raw,readiness=ready,completeSourceArchive=full),indent=2,sort_keys=True)+'\n')
unit=O.parent/'local-unit-validation-r1'
(O/'SHARED_EVIDENCE_REFERENCES.json').write_text(json.dumps({n:dict(bytes=(unit/n).stat().st_size,sha256=sha(unit/n))for n in ('INVENTORY.json','CLOSED.json')},indent=2,sort_keys=True)+'\n')
shutil.copy2(Path(__file__),O/'executed-archive.py')
p99='unavailable (some original arrivals not accepted)'if review['allArrivalP99Ns']is None else str(review['allArrivalP99Ns'])+'ns'
(O/'README.md').write_text(f'''# Rotating fine-capacity{rate}/s:complete original evidence

One fresh{rate*20}-arrival20s lineage on source566dd2fa8b185caa54f3c1061fcdf0009bc3cfd0,actual code2b8d7594e03f8eeeef7aaf8e07db12c3bb585ba4ba67970d065c7174420fbf68. Accepted{review['confirmedAcceptedUniqueOrders']},notSent{review['notSent']},rejected{review['serverRejected']},observed/final UNKNOWN{review['unknownObserved']}/{review['unknownFinal']}. In-window goodput{review['arrivalWindowGoodputPerSecond']}/s. Global successful-arrival p99{p99};accepted-only conditional p99{review['acceptedOrderConditionalP99Ns']}ns.

Leader0/sync2/read128/page32/batch4/chunk6144/owner1ms/driver100us/W128Q64,ROTATING_CONTINUE,one physical session. Both original-PID2s all-member readiness gates and5s pre-load warm-up passed;no JFR. Three JVMs share one existing CPU container over loopback UDP. No service,wire,durability,queue,permit,raw or native disk cap is enlarged.

All complete original closed-native archives,CSV,wire/frame/index/offer bodies,decoded results,expected identities,source/JAR metadata,controller and process records remain in all-original-native-and-review-scopes.tar.gz. ORIGINAL_SCOPE_INVENTORIES.json records every original SHA/length/mode/owner and directory. SOURCE_MIRRORS.json maps each scope to its original path. scope_tar.py independently streams every member and checks exact coverage,including empty directories. Compressed bundles above32MiB are losslessly split;ORIGINAL_LARGE_FILES.json and lossless_parts.py reconstruct the full compressed archive bytes and SHA. No raw rows are sampled or omitted. Small exact proof/configuration bodies are also directly inspectable.

Local compressed packaging reduces redundant disk/network copies;the complete native runtime inputs and remote originals remain retained. Packaging changes no benchmark or remote resource. Qualification includes79 passing tests and the earlier failed planner attempt. Progress to a higher rate requires all originals privately committed plus the explicit finite exploration gate. These20s observations are not sustained capacity,independent-host network performance,hard realtime or any100M proof. Candidate-codec/reference checks are not an independent matching oracle or binary cold-recovery proof.
''')
sys.path.insert(0,str(B/'read128-capacity-lossless-package-preparation-r1'));import lossless_parts
lossless_parts.partition(O)
(O/'LOSSLESS_PARTS_REVIEW.json').write_text(json.dumps(lossless_parts.verify(O),indent=2,sort_keys=True)+'\n')
inventory=tree(O)
(O/'INVENTORY.json').write_text(json.dumps(inventory,indent=2,sort_keys=True)+'\n')
(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    offeredRate=rate,payloadFiles=len(inventory['files']),inventorySha256=sha(O/'INVENTORY.json'),
    archiveSha256=sha(bundle),archiveBytes=bundle.stat().st_size,
    allOriginalScopeMembersVerified=True,allSourcesUnchanged=True,completeOriginalFiles=full['originalFiles']),indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(passed=True,rate=rate,originalFiles=full['originalFiles'],logicalBytes=logical,
    compressedBytes=bundle.stat().st_size,payloadFiles=len(inventory['files']),inventorySha256=sha(O/'INVENTORY.json'))))
