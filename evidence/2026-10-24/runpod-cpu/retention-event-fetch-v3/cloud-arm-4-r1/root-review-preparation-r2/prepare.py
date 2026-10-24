"""Adapt independent owner review to explicit event page; source-only, no benchmark read."""
from pathlib import Path
import ast,difflib,hashlib,json,shutil
HERE=Path(__file__).resolve().parent
BASE=HERE.parent
OLD=BASE/'owner-cloud-root-review-preparation-r1'
source=OLD/'review_owner_collected.py'
assert hashlib.sha256(source.read_bytes()).hexdigest()=='f59cdda64920de06f556c5108fe8a7f37945b9a84b2dabcc3efda1c3155b23a2'
(HERE/'baseline').mkdir()
shutil.copy2(source,HERE/'baseline/review_owner_collected.py')
for n in ['owner_poll_attestation.py','idle_attestation.py']:shutil.copy2(OLD/n,HERE/n)
shutil.copy2(BASE/'cpu-event-fetch-collection-preparation-r1/LOCAL_PREPARATION_FROZEN.json',HERE/'collector-event-source-freeze.json')
s=source.read_text()
changes=[
('23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884','87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa'),
('977197616ade0283174f2ea6ddfaa700547f6d15','d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'),
('28f6865201389901f26b2c6a7c698622d5d8acc635bad24d09ddadff05777b56','c913796c1af5d09340b5a13df37a2974faa9273691f080590d772d7a9b2042db'),
('owner_cap=(1000000,100000,1000000,100000)[arm_number-1]','owner_cap=1000000;event_page=(16,32,16,32)[arm_number-1]'),
('ROOT_VERIFIED_CLOSED_CPU_OWNER_POLL_ARM_COLLECTION','ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_ARM_COLLECTION'),
("gate['ownerPollMaximumParkNs']==(1000000,100000,1000000,100000)[int(n)-1]","gate['ownerPollMaximumParkNs']==1000000 and gate['eventFetchCount']==(16,32,16,32)[int(n)-1] and gate['sameNewArtifactFunctionalQualified']is True and gate['allOriginalRawCanonicalAndThreeSnapshotsVerified']is True "),
('collector-r2-source-freeze.json','collector-event-source-freeze.json'),
("arm_json('load/admission-plan.json')==release['derivedPlan']","arm_json('load/admission-plan.json')==release['derivedPlans'][str(event_page)]"),
('==(33792,500,4,6144,16,8)','==(33792,500,4,6144,event_page,8)'),
("pair,'idle-window8-long-cuts','42000'","pair,'event-fetch-page-long-cuts',str(event_page),'42000'"),
("arms.append({'ownerPollMaximumParkNs':owner_cap","arms.append({'eventFetchCount':event_page,'ownerPollMaximumParkNs':owner_cap"),
("'actualOwnerAttestation':owner","'eventFetchCount':event_page,'sameNewArtifactFunctionalQualified':True,'allOriginalRawCanonicalAndThreeSnapshotsVerified':True,'threeCheckpointLogsNotIndependentSnapshotRecordDecode':True,'actualOwnerAttestation':owner")]
for old,new in changes:
    assert old in s,old;s=s.replace(old,new)
needle=" require(raw['strictSchedulerTimingAdmission'] is True and raw['localFunctionalDiagnosticOptIn'] is False and len(raw['arms'])==1,'Strict single CPU long scheduler required')"
s=s.replace(needle,needle+"\n require(raw['sameNewArtifactFunctionalQualified']is True and raw['allOriginalRawCanonicalAndThreeSnapshotsVerified']is True and final['sameNewArtifactFunctionalQualified']is True,'First actual new artifact full raw/canonical/three-checkpoint-log qualification absent')")
needle=" require(set(inv['sourceAllowlist'])"
s=s.replace(needle," require(all(x['eventFetchCount']==event_page for x in [success,final,native,raw,receipt]),'Every selected page result must match this manual arm')\n"+needle)
needle=" ids={r['role']:r for r in native['actualArguments']}"
s=s.replace(needle," require(configuration.get('commonEventFetchEnvelope')is True and registration['eventFetchCount']==summary['eventFetchCount']==event_page and registration.get('commonEventFetchEnvelope')is True and summary.get('commonEventFetchEnvelope')is True and summary['maintenanceRpcMetrics']['eventFetchCount']==event_page,'Actual registration/config/summary/coordinator event selection differs')\n"+needle)
ast.parse(s)
(HERE/'review_event_collected.py').write_text(s)
(HERE/'SOURCE_DIFF.patch').write_text(''.join(difflib.unified_diff(source.read_text().splitlines(True),s.splitlines(True),fromfile='baseline/review_owner_collected.py',tofile='review_event_collected.py')))
rows={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in HERE.iterdir() if p.is_file()}
(HERE/'SOURCE_FROZEN.json').write_text(json.dumps(dict(passedSourceSyntaxOnly=True,actualRawRunYet=False,sourceFiles=rows,previousInlineFailureRetained=True,scope='Independent complete outer member/raw/canonical/source/page and33792-row p99 review; three matching checkpoint logs do not claim independent Aeron snapshot-record decoding'),indent=2)+'\n')
print(json.dumps(dict(sourceSha256=hashlib.sha256(s.encode()).hexdigest(),sourceOnly=True)))
