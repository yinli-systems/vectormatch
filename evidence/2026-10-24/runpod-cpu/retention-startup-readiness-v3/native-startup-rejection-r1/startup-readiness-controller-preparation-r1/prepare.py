from pathlib import Path
import json,hashlib,shutil,ast,tarfile
B=Path(__file__).resolve().parent.parent;O=Path(__file__).resolve().parent;S=B/'read128-capacity-controller-1000-preparation-r1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();actual=json.loads((B/'startup-readiness-linux-metadata-execution-r1/actual-linux-observation.json').read_text());review=json.loads((B/'startup-readiness-linux-metadata-root-review-r2/ROOT_REVIEW.json').read_text());assert review['passed']and review['allEightActualLoadedOriginsMatchStagedJars']
for n in json.loads((S/'FROZEN.json').read_text())['files']:
 if n not in('first_pilot.py','release.json','linux-metadata.json','linux-metadata-root-review.json'):shutil.copy2(S/n,O/n)
shutil.copy2(B/'startup-readiness-linux-metadata-execution-r1/actual-linux-observation.json',O/'linux-metadata.json');shutil.copy2(B/'startup-readiness-linux-metadata-root-review-r2/ROOT_REVIEW.json',O/'linux-metadata-root-review.json');r=json.loads((S/'release.json').read_text());r.update(sourceCommit='023b8e178b0c0dab29666e754ec07cbad85da36b',codeFingerprint=actual['actualCodeFingerprint'],scope='ALL_MEMBER_READINESS_FIXED_READ128_CAPACITY_1000_20S');old='/opt/vectormatch-cpu/tools/cpu-read128-capacity-metadata-r1';new='/opt/vectormatch-cpu/tools/cpu-startup-readiness-metadata-r1';rows=json.loads((B/'startup-readiness-linux-metadata-preparation-r1/metadata-config.json').read_text())['rows'];r['artifacts']={p.replace(old,new):dict(bytes=rows['lib/'+Path(p).name]['bytes'],sha256=rows['lib/'+Path(p).name]['sha256'])for p in r['artifacts']};r['classPath']=[p.replace(old,new)for p in r['classPath']];r['nodeClassPath']=[p.replace(old,new)for p in r['nodeClassPath']];r['derivedPlan']=actual['plans']['1000']['plan'];r['derivedPlans']={'128':r['derivedPlan']};r['readinessContract']=actual['readinessContract'];(O/'release.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
s=(S/'first_pilot.py').read_text().replace('read128-capacity-1000-r1','readiness-capacity-1000-r1').replace('allSevenActualLoadedOriginsMatchStagedJars','allEightActualLoadedOriginsMatchStagedJars');needle='    base=m.load_base()';addition='''    from readiness_validation import validate_readiness
    original_validate=m.validate_result
    def validate_with_readiness(b,registry,r):
        result=original_validate(b,registry,r)
        cfg=m.json_bounded(b,m.PAIR/'load/configuration.json');warm=m.json_bounded(b,m.PAIR/'preload-warmup.json');reg=m.json_bounded(b,m.PAIR/'registration.json')
        require(reg['allMemberStartupReadinessRequired']is True and reg['allMemberPreloadReadinessRequired']is True and reg['readinessQuietPeriodNs']==2000000000 and reg['readinessDeadlineNs']==45000000000,'Actual application readiness registration differs')
        nodes={member:next(row['identity']['pid']for row in registry.records.values()if row['role']=='window-128-node-'+str(member))for member in range(3)}
        first=m.json_bounded(b,m.PAIR/'startup-readiness.json');last=m.json_bounded(b,m.PAIR/'preload-readiness.json');reports=[validate_readiness(doc,nodes,cfg['scheduledOriginMonotonicNs'])for doc in [first,last]]
        require(first['endedMonotonicNs']<=warm['startedMonotonicNs']and warm['endedMonotonicNs']<=last['startedMonotonicNs'],'Actual startup/setup/warmup/preload readiness order differs')
        result['actualAllMemberReadinessGates']=reports;return result
    m.validate_result=validate_with_readiness
''';assert needle in s;s=s.replace(needle,addition+needle);(O/'first_pilot.py').write_text(s)
files={}
for n in list(json.loads((S/'FROZEN.json').read_text())['files'])+['readiness_validation.py']:
 p=O/n
 if p.suffix=='.py':ast.parse(p.read_text())
 p.chmod(0o644);files[n]=dict(bytes=p.stat().st_size,mode=420,sha256=sha(p))
(O/'FROZEN.json').write_text(json.dumps(dict(schemaVersion=1,files=files,scope='One fresh1000/s native qualification on new all-member readiness artifact; no increase until complete raw/private closure'),indent=2,sort_keys=True)+'\n')
with tarfile.open(O/'source-package.tar.gz','w:gz')as t:
 for n in list(files)+['FROZEN.json']:t.add(O/n,arcname=n,recursive=False)
print(json.dumps(dict(passed=True,codeFingerprint=r['codeFingerprint'],freezeSha256=sha(O/'FROZEN.json'),files=len(files))))
