"""Independent byte/schema review of the closed local metadata attempt; no JVM."""
from pathlib import Path
import hashlib, json, stat, datetime

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
LOCAL = BASE / 'event-fetch-metadata-preparation-r1'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text())
def require(ok, msg):
    if not ok: raise RuntimeError(msg)
def save(p, obj):
    with p.open('x') as f: json.dump(obj, f, indent=2, sort_keys=True); f.write('\n')

closed = load(LOCAL/'CLOSED.json')
require(sha(LOCAL/'CLOSED.json') == '400a4a0df83d6c9eac98f3b696603409d55a05f5b5631b98ff0296788909dd2e', 'closure identity')
manifest = load(LOCAL/'MANIFEST.json')
require(sha(LOCAL/'MANIFEST.json') == closed['manifestSha256'], 'manifest identity')
actual_files = {p.relative_to(LOCAL).as_posix() for p in LOCAL.rglob('*') if p.is_file()}
require(actual_files == set(manifest['files'])|{'CLOSED.json','MANIFEST.json'}, 'exact closed file set')
for name, row in manifest['files'].items():
    p = LOCAL/name; s=p.lstat()
    require(stat.S_ISREG(s.st_mode) and not p.is_symlink(), 'regular file '+name)
    require(dict(bytes=s.st_size, mode=stat.S_IMODE(s.st_mode), uid=s.st_uid, gid=s.st_gid, sha256=sha(p)) == row, 'file identity '+name)
directories = {p.relative_to(LOCAL).as_posix(): dict(mode=stat.S_IMODE(p.lstat().st_mode),uid=p.lstat().st_uid,gid=p.lstat().st_gid) for p in LOCAL.rglob('*') if p.is_dir()}
require(directories == manifest['directories'], 'exact directory metadata')
reg = load(LOCAL/'REGISTRATION.json'); after=load(LOCAL/'INPUTS_AFTER.json')
require(after == reg['inputsBefore'], 'before/after inputs')
for name, row in after.items():
    p=Path(name); s=p.lstat()
    require(dict(bytes=s.st_size, mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid,sha256=sha(p)) == row, 'current input '+name)
obs = load(LOCAL/'actual-distribution-observation.json')
require(sha(LOCAL/'actual-distribution-observation.json') == closed['observationSha256'], 'observation identity')
require(closed['passed'] is True and closed['metadataJvmExited'] is True and closed['javaExitCode']==closed['javacExitCode']==0, 'closed success')
require(reg['sourceCommit']==obs['sourceCommit']==closed['sourceCommit']=='d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8', 'source commit')
require(obs['actualCodeFingerprint']==closed['actualCodeFingerprint']=='87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa', 'code identity')
require(obs['profileSha256']=='732201775469861083f9dd0798a465dec1d0ed6bff39ed281dbef58c28b9fc68', 'profile identity')
require(len(obs['actualCodeSources'])==7 and len({r['path'] for r in obs['actualCodeSources']})==3 and len(obs['distributionJars'])==4, 'origins and four JARs')
for name, row in obs['distributionJars'].items():
    p=Path(row['path']); require(p.name==name and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'], 'JAR body '+name)
for row in obs['actualCodeSources']:
    require({k:v for k,v in row.items() if k!='class'}==obs['distributionJars'][Path(row['path']).name], 'runtime origin '+row['class'])
for count, rpc in [('16',4225),('32',2113)]:
    c=obs['plans'][count]['configuration']; p=obs['plans'][count]['plan']
    require(c==dict(arrivals=33792,ratePerSecond=500,windowNs=67584000000,batchCap=4,archiveChunkBytes=6144,readWindow=8,commonReadWindowEnvelope=True,eventFetchCount=int(count),commonEventFetchEnvelope=True), 'actual configuration '+count)
    require(p['admitted'] and not p['admissionRejections'] and p['selectedMaximumEventFetchRpcs']==rpc and p['maximumAllocatedGrowthBytes']==757122377 and p['maximumRawTraceBytes']==185514924, 'actual Plan '+count)
diff=sorted(k for k,v in obs['plans']['16']['plan'].items() if v!=obs['plans']['32']['plan'][k])
require(diff==obs['planDifferenceKeys']==['eventFetchCount','selectedMaximumEventFetchRpcs','selectedMaximumLogicalMaintenanceRpcs'], 'only selected differences')
for count in ['16','32']:
    require({k:v for k,v in obs['plans'][count]['plan'].items() if k not in diff}==obs['commonPlanObservation'], 'common caps')
require(obs['noDriverOrClusterStarted'] and obs['selectionIntentOnly'] and obs['planProbeUsesTemporaryInMemoryReferenceEngineForCodecDerivation'], 'metadata scope')
require(not any(obs[k] for k in ['ownerConstructed','ownerRuntimeObservationAvailable','driverConstructed','clientConstructed','cliExecuted','nativeUdpOrBusinessSessionStarted','performanceEvidence']), 'no execution claims')
for kind in ['java','javac']:
    execution=load(LOCAL/(kind+'-EXECUTION.json'))
    require(execution['exitCode']==0, 'exit '+kind)
save(OUT/'ROOT_REVIEW.json',dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),reviewSourceSha256=sha(Path(__file__)),closedSha256=sha(LOCAL/'CLOSED.json'),manifestSha256=sha(LOCAL/'MANIFEST.json'),observationSha256=sha(LOCAL/'actual-distribution-observation.json'),filesVerified=len(manifest['files']),directoriesVerified=len(directories),actualSevenOriginsVerified=True,allFourJarBodiesVerified=True,allRegisteredInputsStillExact=True,selectedPlanDifferences=diff,metadataOnly=True,benchmarkExecuted=False))
print(json.dumps(dict(passed=True,files=len(manifest['files']),directories=len(directories))))
