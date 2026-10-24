"""Independent local review: stream every outer member, rehash raw inputs, recompute arrival tails. No SSH or Java."""
import argparse,csv,datetime,hashlib,json,math,pathlib,tarfile,stat
from owner_poll_attestation import validate_owner_bundle
HERE=pathlib.Path(__file__).resolve().parent
CODE='87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa'
SOURCE='d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'
PROFILE='732201775469861083f9dd0798a465dec1d0ed6bff39ed281dbef58c28b9fc68'
OWNER_SHA='868b1f426906e16602e2ad9a0e7c7bba33bb5e80ea950af171a9903ac5dc4fdd'
COLLECTOR_FREEZE_SHA='c913796c1af5d09340b5a13df37a2974faa9273691f080590d772d7a9b2042db'

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
 return h.hexdigest()
def read(p):return json.loads(p.read_text())
def require(v,m):
 if not v:raise ValueError(m)
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--collection-run',type=pathlib.Path,required=True);ap.add_argument('--stage',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);ap.add_argument('--arm',type=int,choices=[1,2,3,4],required=True);a=ap.parse_args();root=a.collection_run.resolve();col=root/'collection';out=a.output.resolve();out.mkdir(exist_ok=False)
 paths=[root/'SUCCESS.json',root/'finalized/LOCAL_COLLECTION_COMPLETE.json',root/'native/result.json',root/'raw/result.json',col/'collection-receipt.json',col/'remote-inventory.stdout.json',a.stage]
 pins={str(p):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths};success,final,native,raw,receipt,inv,stage=map(read,paths)
 require(all(x['passed'] is True for x in [success,final,native,raw,receipt]),'All actual independent collection outcomes must pass')
 require(raw['strictSchedulerTimingAdmission'] is True and raw['localFunctionalDiagnosticOptIn'] is False and len(raw['arms'])==1,'Strict single CPU long scheduler required')
 require(raw['sameNewArtifactFunctionalQualified']is True and raw['allOriginalRawCanonicalAndThreeSnapshotsVerified']is True and final['sameNewArtifactFunctionalQualified']is True,'First actual new artifact full raw/canonical/three-checkpoint-log qualification absent')
 require(native['frozenCodeFingerprintIndependentlyRecomputed']==CODE and native['sourceCommit']==raw['sourceCommit']==SOURCE,'Wrong executed source/code')
 require(native['allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified'] is True and native['allNestedFilesExactlyBoundToOuterArchive'] is True,'Complete nested proof absent')
 require(final['closedArchiveSha256']==receipt['nestedNativeArchive']['sha256'] and final['closedNativeInventorySha256']==receipt['closedNativeInventorySha256'],'Final closure binding')
 for name,key in [('full-closed-round.tar.gz','fullOuterArchive'),('pilot-after-clean-stop.tar.gz','nestedNativeArchive')]:
  p=col/name;require(p.stat().st_size==receipt[key]['bytes'] and sha(p)==receipt[key]['sha256'],'Compressed input mismatch');pins[str(p)]={'bytes':p.stat().st_size,'sha256':sha(p)}
 arm_number=receipt['arm'];require(arm_number==a.arm and all(v['arm']==a.arm for v in [success,final,native,raw]),'Explicit same single arm required');owner_cap=1000000;event_page=(16,32,16,32)[arm_number-1]
 require(all(x['eventFetchCount']==event_page for x in [success,final,native,raw,receipt]),'Every selected page result must match this manual arm')
 require(set(inv['sourceAllowlist'])==set(stage['stagedFiles'])|{'arm-%d-execution-register.json'%arm_number,'arm-%d-execution.stdout'%arm_number,'arm-%d-execution.stderr'%arm_number}|{'release/arm-%d-%s.json'%(n,kind)for n in range(1,arm_number)for kind in ['collection-gate','private-push']},'Explicit source allowlist changed')
 config=read(col/'collector-config.json');require(config['arm']==arm_number and config['ownerPollMaximumParkNs']==owner_cap and config['serverDriverMaximumParkNs']==config['maximumParkNs']==100000,'Actual fixed owner/server factor differs');require(set(config['priorGates'])=={str(n)for n in range(1,arm_number)},'Exact prior gate/private-push prefix')
 pins[str(col/'collector-config.json')]={'bytes':(col/'collector-config.json').stat().st_size,'sha256':sha(col/'collector-config.json')}
 for n,row in config['priorGates'].items():
  require(inv['files']['source/release/arm-%s-collection-gate.json'%n]['sha256']==row['sha256']and inv['files']['source/release/arm-%s-private-push.json'%n]['sha256']==row['privatePushSha256'],'Prior gate/private-push bytes changed')
  gp=col/('raw-files/source/release/arm-%s-collection-gate.json'%n);pp=col/('raw-files/source/release/arm-%s-private-push.json'%n);gate=read(gp);push=read(pp)
  require(sha(gp)==row['sha256']and sha(pp)==row['privatePushSha256']==gate['privatePushReceiptSha256']and gate['arm']==int(n)and gate['frozenReleaseSha256']==config['releaseSha256']and gate['codeFingerprint']==CODE,'Prior exact same-artifact root gate binding')
  require(gate['schemaVersion']==2 and gate['scope']=='ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_ARM_COLLECTION'and gate['collectionComplete']is True and gate['allRawInputsAndFailuresRetained']is True and gate['strictSchedulerTimingAdmission']is True and gate['ownerPollMaximumParkNs']==1000000 and gate['eventFetchCount']==(16,32,16,32)[int(n)-1] and gate['sameNewArtifactFunctionalQualified']is True and gate['allOriginalRawCanonicalAndThreeSnapshotsVerified']is True and gate['serverDriverMaximumParkNs']==100000,'Prior owner gate semantic closure')
  require(push['schemaVersion']==1 and push['scope']=='ROOT_VERIFIED_PRIVATE_EVIDENCE_PUSH'and push['repository']=='yinli-systems/vectormatch'and push['visibility']=='private'and push['pushCompleted']is True and push['remoteCommitVerified']is True and push['fullOriginalEvidencePushed']is True and push['closedArchiveSha256']==gate['closedArchiveSha256']and push['closedNativeInventorySha256']==gate['closedNativeInventorySha256'],'Prior private evidence push required')
  for proof in [gp,pp]:pins[str(proof)]={'bytes':proof.stat().st_size,'sha256':sha(proof)}
 for name,row in stage['stagedFiles'].items():
  actual=inv['files']['source/'+name];require(all(actual[k]==row[k] for k in ['bytes','sha256','mode']),'Staged source mismatch')
 files=set();dirs=set();logical=0
 with tarfile.open(col/'full-closed-round.tar.gz','r|gz') as stream:
  for m in stream:
   name=m.name.rstrip('/');p=pathlib.PurePosixPath(name);require(str(p)==name and not p.is_absolute() and '..' not in p.parts and name not in files|dirs,'Unsafe/duplicate outer member')
   if m.isdir():
    r=inv['directories'][name];require((m.mode,m.uid,m.gid)==(r['mode'],r['uid'],r['gid']),'Directory metadata mismatch');dirs.add(name);continue
   require(m.isfile() and not m.issparse(),'Only ordinary regular files and directories');r=inv['files'][name];require((m.size,m.mode,m.uid,m.gid)==(r['bytes'],r['mode'],r['uid'],r['gid']),'Regular metadata mismatch')
   h=hashlib.sha256();count=0;f=stream.extractfile(m)
   for part in iter(lambda:f.read(1024*1024),b''):h.update(part);count+=len(part)
   require(count==r['bytes'] and h.hexdigest()==r['sha256'],'Complete member SHA mismatch');files.add(name);logical+=count
 require(files==set(inv['files']) and dirs==set(inv['directories']) and logical==receipt['outerLogicalBytes'],'Exact outer file/empty-directory closure')
 for name,row in raw['inputs'].items():
  p=col/name;require(p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'Audited raw input mismatch')
 bindings=read(root/'raw/ORIGINAL_TO_MATERIALIZED_BINDINGS.json');require(bindings['passed']is True,'Original/local metadata projection proof absent')
 for name,r in raw['inputs'].items():
  b=bindings['bindings'][name];original=inv['files'][name[len('raw-files/'):]];p=col/name;st=p.lstat()
  require(b['payloadExact']is True and b['archiveOwnerIsNotLocalOwnerClaim']is True and b['originalArchiveMetadata']=={k:original[k]for k in ['bytes','sha256','mode','uid','gid']},'Original archive projection differs')
  require((st.st_mode&0o777,st.st_uid,st.st_gid)==tuple(b['materializedLocalMetadata'][k]for k in ['mode','uid','gid']) and not p.is_symlink(),'Actual local projection metadata differs')
 # Exact closed bytes are checked above before the pure constructed-owner gate.
 require(sha(HERE/'owner_poll_attestation.py')==OWNER_SHA and sha(HERE/'idle_attestation.py')=='8598dc1bc5d1795c3e088425816d8ce75f08918c37969a46b715da166c7bec24','Unique actual-owner/driver validator source differs')
 freeze_path=HERE/'collector-event-source-freeze.json';freeze=read(freeze_path)
 require(sha(freeze_path)==COLLECTOR_FREEZE_SHA,'Exact corrected collectorR2 source closure')
 for phase,name in [('native','audit_native_artifacts.py'),('raw','audit_raw.py')]:
  for file,key in [('executed-auditor.py',name),('common.py','common.py')]:
   path=root/phase/file;pin=freeze['sourceFiles'][key];require(path.stat().st_size==pin['bytes']and sha(path)==pin['sha256'],'Executed correctedR2 source differs');pins[str(path)]={'bytes':path.stat().st_size,'sha256':sha(path)}
 def closed_json(name):
  p=col/'raw-files'/name;r=inv['files'][name];require(p.is_file()and not p.is_symlink()and p.stat().st_size<=1024**2 and p.stat().st_size==r['bytes']and sha(p)==r['sha256'],'Closed bounded JSON differs: '+name);pins[str(p)]={'bytes':p.stat().st_size,'sha256':sha(p)};return read(p)
 release=closed_json('source/release/release.json');require(sha(col/'raw-files/source/release/release.json')==config['releaseSha256']==stage['releaseSha256']==raw['releaseSha256']==native['releaseSha256']==final['frozenReleaseSha256']==receipt['frozenReleaseSha256'],'All actual release bindings differ')
 require(release['sourceCommit']==SOURCE and release['codeFingerprint']==CODE and release['profileFingerprint']==PROFILE and release['ownerPollValidatorSha256']==OWNER_SHA and stage['stagedFiles']['owner_poll_attestation.py']['sha256']==OWNER_SHA,'Actual new release/source/profile/owner schema differs')
 require(closed_json('job/release.json')==release,'Job source release differs')
 for body,row in release['artifacts'].items():
  path=root/'native/actual-runtime-artifacts'/pathlib.Path(body).name;require(path.stat().st_size==row['bytes']and sha(path)==row['sha256'],'Actual runtimeJAR source differs');pins[str(path)]={'bytes':path.stat().st_size,'sha256':sha(path)}
 h=hashlib.sha256()
 for typ,name in [('io.vectormatch.cluster.RetentionNodeMainV3','cluster-0.1.0-SNAPSHOT.jar'),('io.vectormatch.core.MatchingEngine','core-0.1.0-SNAPSHOT.jar'),('io.aeron.driver.MediaDriver','aeron-all-1.53.3.jar'),('org.agrona.DirectBuffer','aeron-all-1.53.3.jar')]:h.update(typ.encode());h.update((root/'native/actual-runtime-artifacts'/name).read_bytes())
 require(h.hexdigest()==CODE,'Independent actual4anchor JAR fingerprint differs')
 def arm_json(name):return closed_json('job/idle-arm/'+name)
 registration=arm_json('registration.json');configuration=arm_json('load/configuration.json');summary=arm_json('load/load-result.json');observations=arm_json('load/transport-observations.json');require(arm_json('load/admission-plan.json')==release['derivedPlans'][str(event_page)],'Actual JAR-derived plan differs')
 require((configuration['arrivals'],configuration['ratePerSecond'],configuration['batchCap'],configuration['archiveChunkBytes'],configuration['eventFetchCount'],configuration['readWindow'])==(33792,500,4,6144,event_page,8)and configuration['actualCodeSha256']==CODE and configuration['profileSha256']==PROFILE,'Actual fixed long source/config differs')
 require(configuration.get('commonEventFetchEnvelope')is True and registration['eventFetchCount']==summary['eventFetchCount']==event_page and registration.get('commonEventFetchEnvelope')is True and summary.get('commonEventFetchEnvelope')is True and summary['maintenanceRpcMetrics']['eventFetchCount']==event_page,'Actual registration/config/summary/coordinator event selection differs')
 ids={r['role']:r for r in native['actualArguments']};require(set(ids)=={'pilot-parent','window-8-node-0','window-8-node-1','window-8-node-2'},'Exact four actual kernel identities')
 actual_parent=closed_json('job/identity-observation-000.json')['kernelIdentity'];launch=closed_json('job/parent-launch-handle.json');stop=closed_json('job/python-owned-stop.json')
 require(actual_parent['pid']==launch['pid']and actual_parent['arguments']==launch['expectedArguments']and actual_parent['commandSha256']==launch['expectedCommandSha256'],'Actual parent launch/kernel argv differs')
 require(stop['allOwnedStopped']is True and stop['forcedKill']is False and stop['numericPidSignalFallback']is False and stop['errors']==[]and len(stop['reports'])==3 and{r['role']for r in stop['reports']}=={'window-8-node-'+str(n)for n in (0,1,2)},'Actual three owned node stop closure differs')
 for role,record in [('pilot-parent',actual_parent)]+[(r['role'],r['record'])for r in stop['reports']]:
  require(role in ids and all(ids[role][k]==record[k]for k in ['pid','startTicks','arguments','commandSha256']),'Reported/actual kernel identity differs')
  require(hashlib.sha256(b''.join(v.encode()+b'\0'for v in record['arguments'])).hexdigest()==record['commandSha256'],'Kernel fullargv SHA differs')
 pair=config['remotePrep']+'/arm-'+str(arm_number)+'/idle-arm'
 parent_args=[release['java'],'-Dvectormatch.retention.idleMaxParkNs=100000','-Dvectormatch.retention.ownerPollMaxParkNs='+str(owner_cap)]+release['parentJvmArguments']+['-cp',':'.join(release['classPath']),'io.vectormatch.cluster.RetentionCapacityAeronPilotV3',pair,'event-fetch-page-long-cuts',str(event_page),'42000']
 expected_nodes={n:[release['java'],'-Dvectormatch.retention.idleMaxParkNs=100000','--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED','-Xmx256m','-Daeron.cluster.appointed.leader.id=0','-cp',':'.join(release['nodeClassPath']),'io.vectormatch.cluster.RetentionNodeMainV3',str(n),pair,'42000','2',release['profileId'],registration['lineage'],PROFILE,CODE,'bounded-maintenance-v1']for n in (0,1,2)}
 owner=validate_owner_bundle(registration=registration,configuration=configuration,summary=summary,before=arm_json('load/owner-before-close.json'),after=arm_json('load/owner-after-close.json'),parent=ids['pilot-parent'],nodes={n:ids['window-8-node-'+str(n)]for n in(0,1,2)},expected_owner_cap=owner_cap,expected_parent_arguments=parent_args,expected_node_arguments=expected_nodes,node_idle_actuals={n:arm_json('node-%d/idle-observations/idle-000.actual.json'%n)for n in(0,1,2)},parent_idle_actuals=[v['retentionIdlePolicy']for v in observations]+[summary['physicalOfferTape']['lastActualTransportObservation']['retentionIdlePolicy']])
 require(owner==native['ownerPollAttestation']==raw['ownerPollAttestation']==final['ownerPollAttestation'],'Actual constructed-owner gates differ')
 require(all(v['ownerPollMaximumParkNs']==owner_cap and v['serverDriverMaximumParkNs']==100000 for v in [success,final,native,raw]),'Owner factor/server constant report differs')
 arms=[]
 for arm in raw['arms']:
  window=arm['readWindow'];p=col/'raw-files/job/idle-arm/load/arrivals.csv';rows=list(csv.DictReader(p.open()));require(len(rows)==33792,'Every planned arrival required');lat=[];within=0
  for i,r in enumerate(rows):
   require(int(r['arrival_index'])==i and int(r['scheduled_offset_ns'])==i*2000000,'Arrival identity/clock mismatch')
   require(r['status']=='APPLIED' and r['result_code']=='ACCEPTED' and r['reply_replayed']=='false','All-arrival accepted p99 requires every fresh accepted result')
   require(int(r['worker'])==i%128 and r['producer']=='load-w'+str(i%128) and int(r['request_seq'])==1+i//128 and int(r['arrival_offset_ns'])-int(r['scheduled_offset_ns'])<=20000000 and r['unknown_observed_offset_ns']=='' and r['not_sent_reason']=='0' and r['initial_server_admission_status']=='','Every actual arrival identity/scheduler/terminal gate required')
   end=int(r['reply_completion_offset_ns']);lat.append(end-int(r['scheduled_offset_ns']));within+=end<=67584000000
  require({int(r['order_id']) for r in rows}==set(range(2,33794)) and {int(r['command_seq'])for r in rows}==set(range(4,33796)),'33792 distinct fresh IDs and exact command frontier required')
  p99=sorted(lat)[math.ceil(.99*len(lat))-1];require(p99==arm['rawMetrics']['allArrivalP99Ns'] and within==arm['rawMetrics']['acceptedOrdersInArrivalWindow'],'Independently recomputed latency/goodput differs')
  require(arm['readPhaseBindings']['actualOfferedHighWater']==window and len(arm['readPhaseBindings']['readPhases'])==24 and len(arm['cycles'])==12,'Actual read windows/phases/cycles differ')
  quality=read(col/'raw-files/job/idle-arm/load/load-result.json');require(quality['schedulerTimingValid'] is True,'CPU scheduler quality invalid')
  arms.append({'eventFetchCount':event_page,'ownerPollMaximumParkNs':owner_cap,'serverDriverMaximumParkNs':arm['config']['retentionIdleSelection']['maximumParkNs'],'retainedPostCheckpointEosWarningPairs':raw['retainedPostCheckpointEosWarningPairs'],'readWindow':window,'arrivals':len(rows),'allArrivalP99Ns':p99,'acceptedWithinArrivalWindow':within,'arrivalWindowGoodputPerSecond':within/67.584,'maintenanceCycleWallNs':arm['totalMaintenanceCycleNs'],'offeredHighWater':arm['readPhaseBindings']['actualOfferedHighWater']})
 for helper in [HERE/'owner_poll_attestation.py',HERE/'idle_attestation.py',freeze_path,pathlib.Path(__file__).resolve(),root/'raw/ORIGINAL_TO_MATERIALIZED_BINDINGS.json']:pins[str(helper)]={'bytes':helper.stat().st_size,'sha256':sha(helper)}
 require(all(p.stat().st_size==r['bytes'] and sha(p)==r['sha256'] for p,r in [(pathlib.Path(n),v) for n,v in pins.items()]),'Evidence changed during root review')
 report={'passed':True,'sourceCommit':raw['sourceCommit'],'releaseSha256':raw['releaseSha256'],'rawAuditSha256':sha(root/'raw/result.json'),'originalOwnerProjectionVerified':True,'ownerPollMaximumParkNs':owner_cap,'serverDriverMaximumParkNs':100000,'eventFetchCount':event_page,'sameNewArtifactFunctionalQualified':True,'allOriginalRawCanonicalAndThreeSnapshotsVerified':True,'threeCheckpointLogsNotIndependentSnapshotRecordDecode':True,'actualOwnerAttestation':owner,'independent4AnchorCodeFingerprint':h.hexdigest(),'scope':'Independent local complete outer stream SHA/bytes/mode/owner/empty-dir verification plus all raw input hashes and separate33792-row p99 calculations. Does not promote sustained capacity.','arm':receipt['arm'],'atUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'outerFiles':len(files),'outerDirectories':len(dirs),'outerLogicalBytes':logical,'rawInputFiles':len(raw['inputs']),'allFullOuterMembersVerified':True,'allRawInputsUnchanged':True,'arms':arms,'inputs':pins,'scriptSha256':sha(pathlib.Path(__file__).resolve())};save(out/'ROOT_REVIEW.json',report);print(json.dumps({k:v for k,v in report.items() if k!='inputs'},indent=2))
if __name__=='__main__':main()
