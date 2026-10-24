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
 require(native['frozenCodeFingerprintIndependentlyRecomputed']=='f78025f91f9e43ad634840b400ab04ed4ae422597c35800984e434dbd1844c8f','Wrong executed code')
 require(native['allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified'] is True and native['allNestedFilesExactlyBoundToOuterArchive'] is True,'Complete nested proof absent')
 require(final['closedArchiveSha256']==receipt['nestedNativeArchive']['sha256'] and final['closedNativeInventorySha256']==receipt['closedNativeInventorySha256'],'Final closure binding')
 for name,key in [('full-closed-round.tar.gz','fullOuterArchive'),('pilot-after-clean-stop.tar.gz','nestedNativeArchive')]:
  p=col/name;require(p.stat().st_size==receipt[key]['bytes'] and sha(p)==receipt[key]['sha256'],'Compressed input mismatch');pins[str(p)]={'bytes':p.stat().st_size,'sha256':sha(p)}
 arm_number=receipt['arm'];require(arm_number in [1,2,3,4],'Canonical arm required')
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
   require(m.isfile(),'Only regular files and directories');r=inv['files'][name];require((m.size,m.mode,m.uid,m.gid)==(r['bytes'],r['mode'],r['uid'],r['gid']),'Regular metadata mismatch')
   h=hashlib.sha256();count=0;f=stream.extractfile(m)
   for part in iter(lambda:f.read(1024*1024),b''):h.update(part);count+=len(part)
   require(count==r['bytes'] and h.hexdigest()==r['sha256'],'Complete member SHA mismatch');files.add(name);logical+=count
 require(files==set(inv['files']) and dirs==set(inv['directories']) and logical==receipt['outerLogicalBytes'],'Exact outer file/empty-directory closure')
 for name,row in raw['inputs'].items():
  p=col/name;require(p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'Audited raw input mismatch')
 arms=[]
 for arm in raw['arms']:
  window=arm['readWindow'];p=col/'raw-files/job/idle-arm/load/arrivals.csv';rows=list(csv.DictReader(p.open()));require(len(rows)==6400,'Every planned arrival required');lat=[];within=0
  for i,r in enumerate(rows):
   require(int(r['arrival_index'])==i and int(r['scheduled_offset_ns'])==i*2000000,'Arrival identity/clock mismatch')
   require(r['status']=='APPLIED' and r['result_code']=='ACCEPTED' and r['reply_replayed']=='false','All-arrival accepted p99 requires every fresh accepted result')
   end=int(r['reply_completion_offset_ns']);lat.append(end-int(r['scheduled_offset_ns']));within+=end<=12800000000
  require(len({r['order_id'] for r in rows})==6400,'6400 distinct fresh accepted IDs required')
  p99=sorted(lat)[math.ceil(.99*len(lat))-1];require(p99==arm['rawMetrics']['allArrivalP99Ns'] and within==arm['rawMetrics']['acceptedOrdersInArrivalWindow'],'Independently recomputed latency/goodput differs')
  require(arm['readPhaseBindings']['actualOfferedHighWater']==window and len(arm['readPhaseBindings']['readPhases'])==6 and len(arm['cycles'])==3,'Actual read windows/phases/cycles differ')
  quality=read(col/'raw-files/job/idle-arm/load/load-result.json');require(quality['schedulerTimingValid'] is True,'CPU scheduler quality invalid')
  arms.append({'maximumParkNs':arm['config']['retentionIdleSelection']['maximumParkNs'],'retainedPostCheckpointEosWarningPairs':arm['retainedPostCheckpointEosWarningPairs'],'readWindow':window,'arrivals':len(rows),'allArrivalP99Ns':p99,'acceptedWithinArrivalWindow':within,'arrivalWindowGoodputPerSecond':within/12.8,'maintenanceCycleWallNs':arm['totalMaintenanceCycleNs'],'offeredHighWater':arm['readPhaseBindings']['actualOfferedHighWater']})
 require(all(p.stat().st_size==r['bytes'] and sha(p)==r['sha256'] for p,r in [(pathlib.Path(n),v) for n,v in pins.items()]),'Evidence changed during root review')
 report={'passed':True,'scope':'Independent local complete outer stream SHA/bytes/mode/owner/empty-dir verification plus all raw input hashes and separate 6400-row p99 calculations. Does not promote sustained capacity.','arm':receipt['arm'],'atUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'outerFiles':len(files),'outerDirectories':len(dirs),'outerLogicalBytes':logical,'rawInputFiles':len(raw['inputs']),'allFullOuterMembersVerified':True,'allRawInputsUnchanged':True,'arms':arms,'inputs':pins,'scriptSha256':sha(pathlib.Path(__file__).resolve())};save(out/'ROOT_REVIEW.json',report);print(json.dumps({k:v for k,v in report.items() if k!='inputs'},indent=2))
if __name__=='__main__':main()
