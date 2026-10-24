"""Independent local review: stream every outer member, rehash raw inputs, recompute arrival tails. No SSH or Java."""
import argparse,csv,datetime,hashlib,json,math,pathlib,tarfile

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
 ap=argparse.ArgumentParser();ap.add_argument('--collection-run',type=pathlib.Path,required=True);ap.add_argument('--stage',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);a=ap.parse_args();root=a.collection_run.resolve();col=root/'collection';out=a.output.resolve();out.mkdir(exist_ok=False)
 paths=[root/'SUCCESS.json',root/'finalized/LOCAL_COLLECTION_COMPLETE.json',root/'native/result.json',root/'raw/result.json',col/'collection-receipt.json',col/'remote-inventory.stdout.json',a.stage]
 pins={str(p):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths};success,final,native,raw,receipt,inv,stage=map(read,paths)
 require(all(x['passed'] is True for x in [success,final,native,raw,receipt]),'All actual independent collection outcomes must pass')
 require(raw['strictSchedulerTimingAdmission'] is True and raw['localFunctionalDiagnosticOptIn'] is False and len(raw['arms'])==1,'Strict single CPU long scheduler required')
 require(native['frozenCodeFingerprintIndependentlyRecomputed']=='6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8','Wrong executed code')
 require(native['allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified'] is True and native['allNestedFilesExactlyBoundToOuterArchive'] is True,'Complete nested proof absent')
 require(final['closedArchiveSha256']==receipt['nestedNativeArchive']['sha256'] and final['closedNativeInventorySha256']==receipt['closedNativeInventorySha256'],'Final closure binding')
 for name,key in [('full-closed-round.tar.gz','fullOuterArchive'),('pilot-after-clean-stop.tar.gz','nestedNativeArchive')]:
  p=col/name;require(p.stat().st_size==receipt[key]['bytes'] and sha(p)==receipt[key]['sha256'],'Compressed input mismatch');pins[str(p)]={'bytes':p.stat().st_size,'sha256':sha(p)}
 arm_number=receipt['arm'];require(arm_number==1,'Canonical arm required')
 require(set(inv['sourceAllowlist'])==set(stage['stagedFiles'])|{'arm-%d-execution-register.json'%arm_number,'arm-%d-execution.stdout'%arm_number,'arm-%d-execution.stderr'%arm_number}|{'release/arm-%d-collection-gate.json'%n for n in range(1,arm_number)},'Explicit source allowlist changed')
 config=read(col/'collector-config.json')
 for n,row in config['priorGates'].items():
  require(inv['files']['source/release/arm-%s-collection-gate.json'%n]['sha256']==row['sha256'],'Prior gate evidence changed')
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
  arms.append({'maximumParkNs':arm['config']['retentionIdleSelection']['maximumParkNs'],'retainedPostCheckpointEosWarningPairs':raw['retainedPostCheckpointEosWarningPairs'],'readWindow':window,'arrivals':len(rows),'allArrivalP99Ns':p99,'acceptedWithinArrivalWindow':within,'arrivalWindowGoodputPerSecond':within/67.584,'maintenanceCycleWallNs':arm['totalMaintenanceCycleNs'],'offeredHighWater':arm['readPhaseBindings']['actualOfferedHighWater']})
 require(all(p.stat().st_size==r['bytes'] and sha(p)==r['sha256'] for p,r in [(pathlib.Path(n),v) for n,v in pins.items()]),'Evidence changed during root review')
 report={'passed':True,'sourceCommit':raw['sourceCommit'],'releaseSha256':raw['releaseSha256'],'rawAuditSha256':sha(root/'raw/result.json'),'originalOwnerProjectionVerified':True,'scope':'Independent local complete outer stream SHA/bytes/mode/owner/empty-dir verification plus all raw input hashes and separate33792-row p99 calculations. Does not promote sustained capacity.','arm':receipt['arm'],'atUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'outerFiles':len(files),'outerDirectories':len(dirs),'outerLogicalBytes':logical,'rawInputFiles':len(raw['inputs']),'allFullOuterMembersVerified':True,'allRawInputsUnchanged':True,'arms':arms,'inputs':pins,'scriptSha256':sha(pathlib.Path(__file__).resolve())};save(out/'ROOT_REVIEW.json',report);print(json.dumps({k:v for k,v in report.items() if k!='inputs'},indent=2))
if __name__=='__main__':main()
