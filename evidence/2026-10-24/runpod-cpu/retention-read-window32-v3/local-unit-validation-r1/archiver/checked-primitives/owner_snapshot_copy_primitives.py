"""Explicit closed arm2..4 proof archive only; shared A1 bytes referenced immutably."""
import argparse,datetime,hashlib,io,json,os,re,shutil,stat,tarfile,zipfile
from pathlib import Path,PurePosixPath
WORKSPACE=Path('/Users/kevin/Documents/ChatGPT/App 2')
BASE=WORKSPACE/'runtime/cloud/cpu-20261024'
HERE=Path(__file__).resolve().parent
A1=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3/cloud-arm-1-r1'
A1_INVENTORY_SHA='539e722c181f68ac94f40c2aa6ff446e1a5b669963c20e50d63fb2cde5df327f'
A1_CLOSED_SHA='f5500fd4b1ab1b09b4688ca893a0263e30ac5adfb348fdade75b78694492451e'
CODE='23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884'
SOURCE='977197616ade0283174f2ea6ddfaa700547f6d15'
EXCLUDED_PARTS={'__pycache__','.pytest_cache'}
def require(ok,msg):
 if not ok:raise AssertionError(msg)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def save(p,value):
 with p.open('x')as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def row(p):
 s=p.lstat();require(stat.S_ISREG(s.st_mode)and s.st_nlink==1,'Only independent regular files: '+str(p))
 return {'bytes':s.st_size,'sha256':sha(p),'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
def snapshot(root):
 require(root.is_dir()and not root.is_symlink(),'Source root is not regular directory')
 files={};dirs={};excluded=[]
 for p in [root]+sorted(root.rglob('*')):
  rel='.'if p==root else str(p.relative_to(root))
  if any(part in EXCLUDED_PARTS for part in p.relative_to(root).parts):excluded.append(rel);continue
  s=p.lstat();require(not p.is_symlink(),'Source symlink refused: '+str(p))
  if stat.S_ISDIR(s.st_mode):dirs[rel]={'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
  else:files[rel]=row(p)
 return {'files':files,'directories':dirs,'explicitCacheExclusions':excluded}

def copy_tree(source,target,inventory):
 require(not target.exists(),'Never overwrite archive target')
 for name,meta in sorted(inventory['directories'].items(),key=lambda x:len(Path(x[0]).parts)):
  p=target if name=='.'else target/name;p.mkdir(mode=meta['mode'],parents=False)
 for name in inventory['files']:
  p=target/name;require(not p.exists(),'No overwrite');shutil.copy2(source/name,p)
 for name,meta in inventory['directories'].items():
  p=target if name=='.'else target/name;os.chmod(p,meta['mode'])
 require(snapshot(target)==inventory,'Copied payload mode/owner/empty-directory closure differs')

# Review only concrete known credential markers; not a universal secret detector.
MARKERS={
 'private-key-PEM':rb'-----BEGIN '+rb'(?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
 'github-token':rb'gh[pousr]_[A-Za-z0-9]{30,}',
 'aws-access-key-id':rb'(?:AKIA|ASIA)[A-Z0-9]{16}',
 'slack-token':rb'xox[baprs]-[A-Za-z0-9-]{20,}',
 'google-api-key':rb'AIza[A-Za-z0-9_-]{30,}',
 'openai-style-key':rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}',
}
PATTERN=re.compile(b'|'.join(b'(?P<'+k.encode().replace(b'-',b'_')+b'>'+v+b')'for k,v in MARKERS.items()))
SCANNED=[];HITS=[]

def safe_member(name):
 p=PurePosixPath(name);require(name and not p.is_absolute()and'..'not in p.parts,'Unsafe archive scan member');return name

def scan_stream(stream,label):
 h=hashlib.sha256();size=0;tail=b'';hits=set()
 for block in iter(lambda:stream.read(1024**2),b''):
  h.update(block);size+=len(block)
  candidate=tail+block
  if any(prefix in candidate for prefix in (b'-----BEGIN ',b'gh',b'AKIA',b'ASIA',b'xox',b'AIza',b'sk-')):
   for m in PATTERN.finditer(candidate):hits.add(m.lastgroup)
  tail=(tail+block)[-256:]
 if hits:HITS.append({'path':label,'knownMarkerClasses':sorted(hits)})
 SCANNED.append({'path':label,'bytes':size,'sha256':h.hexdigest()})

def scan_file(path,label):
 if path.name.endswith('.tar.gz'):
  with tarfile.open(path,'r|gz')as t:
   for member in t:
    safe_member(member.name)
    if member.isdir():continue
    require(member.isfile(),'Nonregular archive scan member')
    f=t.extractfile(member);nested=label+'!'+member.name
    if member.name.endswith(('.zip','.jar')):
     data=f.read();scan_zip(io.BytesIO(data),nested)
    else:scan_stream(f,nested)
 elif path.suffix in ('.zip','.jar'):
  with path.open('rb')as f:scan_zip(f,label)
 else:
  with path.open('rb')as f:scan_stream(f,label)

def scan_zip(stream,label):
 with zipfile.ZipFile(stream)as z:
  names=set()
  for info in z.infolist():
   safe_member(info.filename);require(info.filename not in names,'Duplicate ZIP member');names.add(info.filename)
   if info.is_dir():continue
   require(info.file_size<=256*1024**2,'Bounded ZIP member review')
   with z.open(info)as f:scan_stream(f,label+'!'+info.filename)


def load_config(path,expected):
 require(sha(path)==expected,'Exact root archive-config SHA');c=json.loads(path.read_text());arm=c['arm']
 frozen=json.loads((HERE/'SOURCE_FROZEN.json').read_text())
 for name,pin in frozen['sourceFiles'].items():require((HERE/name).stat().st_size==pin['bytes']and sha(HERE/name)==pin['sha256'],'Prepared helper source changed')
 require(c['schemaVersion']==1 and type(arm)is int and arm in(2,3,4),'Explicit arm2..4 only')
 require(sha(A1/'INVENTORY.json')==A1_INVENTORY_SHA and sha(A1/'CLOSED.json')==A1_CLOSED_SHA,'Immutable shared A1 roots changed')
 require(c['sharedA1InventorySha256']==A1_INVENTORY_SHA and c['sharedA1ClosedSha256']==A1_CLOSED_SHA,'Exact shared A1 roots required')
 mandatory={'actual-collection','actual-config','config-execution','actual-launch','launch-execution','collection-execution','root-review','root-review-preparation'}
 require(mandatory<=set(c['scopes']) and len(c['scopes'])<=24 and any(k.startswith('close-inspection-')for k in c['scopes']),'Explicit current-arm closed scopes required')
 for name,path in c['scopes'].items():
  require(safe_member(name)==name and'/'not in name,'Flat scope name');source=Path(path);require(source.is_absolute()and '..'not in source.parts and source.is_relative_to(BASE)and not source.is_symlink()and source.is_dir(),'Bounded local scope inside BASE only')
  require(not any(p.is_symlink()for p in[source]+list(source.parents)),'No source parent symlinks')
  if name!='root-review-preparation':require(('arm-'+str(arm))in source.name,'Only current-arm scopes may be copied; shared sources use immutable A1 refs')
 review=Path(c['scopes']['root-review'])/'ROOT_REVIEW.json';require(sha(review)==c['rootReviewSha256'],'Exact actual root review required');r=json.loads(review.read_text());owner=(1000000,100000,1000000,100000)[arm-1]
 require(r['passed']is True and r['arm']==arm and r['sourceCommit']==SOURCE and r['independent4AnchorCodeFingerprint']==CODE and r['allFullOuterMembersVerified']is True and r['allRawInputsUnchanged']is True and r['ownerPollMaximumParkNs']==owner and r['serverDriverMaximumParkNs']==100000,'Same actual source/owner/root closure required')
 require(r['actualOwnerAttestation']['passed']is True and r['actualOwnerAttestation']['actualConfiguredIdleFactoryCreations']==22,'Actual owner22 prerequisite')
 return c,r

def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--config',required=True,type=Path);ap.add_argument('--config-sha256',required=True);args=ap.parse_args();config=args.config.absolute();c,review=load_config(config,args.config_sha256);arm=c['arm']
 target=WORKSPACE/('evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3/cloud-arm-%d-r1'%arm);require(not target.exists(),'New immutable arm archive required');require(shutil.disk_usage(WORKSPACE).free>=1024**3+512*1024**2,'1GiB floor plus bounded copyreserve')
 trees={name:Path(path)for name,path in c['scopes'].items()};collection=trees['actual-collection'];require(sha(trees['root-review-preparation']/'review_owner_collected.py')==review['scriptSha256'],'Actual executed current root helper differs')
 raw=json.loads((collection/'raw/result.json').read_text());final=json.loads((collection/'finalized/LOCAL_COLLECTION_COMPLETE.json').read_text());actual_config=json.loads((collection/'collection/collector-config.json').read_text())
 require(raw['passed']is True and raw['arm']==final['arm']==actual_config['arm']==arm and raw['strictSchedulerTimingAdmission']is True and raw['localFunctionalDiagnosticOptIn']is False and final['passed']is True,'Actual strict current arm proof required')
 require(raw['releaseSha256']==review['releaseSha256']==actual_config['releaseSha256']and len(raw['arms'])==1 and raw['sourceCommit']==SOURCE,'Exact current arm/source/release')
 require(sha(collection/'raw/result.json')==review['rawAuditSha256'],'Reviewed raw result differs');require(sha(trees['actual-config']/'collector-config.json')==sha(collection/'collection/collector-config.json'),'Actual config-copy source differs')
 require(set(actual_config['priorGates'])=={str(n)for n in range(1,arm)},'Exact preceding closed gate/private-push prefix')
 singles={}
 for number,prior in actual_config['priorGates'].items():
  for kind,pathkey,shakey in [('collection-gate','local','sha256'),('private-push','privatePushLocal','privatePushSha256')]:
   path=Path(prior[pathkey]);require(path.is_file()and not path.is_symlink()and path.is_relative_to(BASE)and '..'not in path.parts and sha(path)==prior[shakey],'Prior receipt source bytes changed');singles['prior-gate-receipts/arm-%s-%s.json'%(number,kind)]=path
 for path,input_pin in review['inputs'].items():
  source=Path(path);source=source if source.is_absolute()else WORKSPACE/source;require(source.stat().st_size==input_pin['bytes']and sha(source)==input_pin['sha256'],'Actual reviewed input changed')
 before={name:snapshot(source)for name,source in trees.items()};single_before={name:row(source)for name,source in singles.items()}
 require(len(before['actual-collection']['files'])==c['actualCollectionFiles']and sum(r['bytes']for r in before['actual-collection']['files'].values())==c['actualCollectionBytes'],'Exact current collection count/bytes differs')
 require(sum(len(v['files'])for v in before.values())<=1500 and sum(r['bytes']for v in before.values()for r in v['files'].values())<=512*1024**2,'Finite1500file/512MiB currentarm source closure')
 target.mkdir();save(target/'REGISTRATION.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'arm':arm,'configSha256':args.config_sha256,'sourceTrees':{name:str(path)for name,path in trees.items()},'rootReviewSha256':c['rootReviewSha256'],'priorReceiptSources':{name:str(path)for name,path in singles.items()},'sharedA1InventorySha256':A1_INVENTORY_SHA,'sharedA1ClosedSha256':A1_CLOSED_SHA,'currentArmOnly':True,'noSparseExtraction':True})
 for name,source in trees.items():copy_tree(source,target/name,before[name])
 for name,source in singles.items():
  output=target/name;output.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,output);require(row(output)==single_before[name],'Exact priorreceipt copy')
 after={name:snapshot(source)for name,source in trees.items()};require(before==after and all(row(singles[name])==r for name,r in single_before.items()),'Original currentarm source closure drift')
 save(target/'SOURCE_BEFORE_COPY.json',{'trees':before,'singles':single_before});save(target/'SOURCE_AFTER_COPY.json',{'trees':after,'singles':single_before,'allOriginalsUnchanged':True})
 shared=json.loads((A1/'INVENTORY.json').read_text());keys=['collector-preparation-r1/HISTORICAL_R1_SOURCE_FROZEN.json','collector-preparation-r2/LOCAL_PREPARATION_FROZEN.json','cloud-controller-preparation/LOCAL_PREPARATION_FROZEN.json','actual-staging/STAGE_SUCCESS.json','actual-root-release-freeze/ROOT_FREEZE.json','actual-root-release-freeze/release/release.json','stage-preparation-r1/HELPERS_FROZEN.json','stage-preparation-r2/HELPERS_FROZEN.json']
 # Exact referenced shared subtree rows are recorded even if a historical freeze basename differs.
 shared_rows={name:r for name,r in shared['files'].items()if name in keys or any(name.startswith(prefix)for prefix in ['collector-preparation-r1/','collector-preparation-r2/','cloud-controller-preparation/','collector-peer-review/','stage-preparation-r1/','stage-preparation-r2/','actual-staging/','actual-root-release-freeze/','root-release-preparation/','close-preparation/','next-arm-execution-preparation/','collection-root-execution-preparation/','close-execution-preparation/'])}
 save(target/'IMMUTABLE_SHARED_A1_REFERENCES.json',{'sharedArchive':str(A1),'inventorySha256':A1_INVENTORY_SHA,'closedSha256':A1_CLOSED_SHA,'referencedFileRows':shared_rows,'sharedBodiesNotRecopied':True,'priorPrivatePushReceiptsSeparatelyCopied':True,'noLocalNativeArchiveRechecked':True})
 shutil.copy2(Path(__file__),target/'archive_arm.py');shutil.copy2(config,target/'archiver-config.json');shutil.copy2(HERE/'SOURCE_FROZEN.json',target/'archiver-source-freeze.json')
 helper_sources=target/'archiver-preparation';helper_sources.mkdir()
 for name,pin in json.loads((HERE/'SOURCE_FROZEN.json').read_text())['sourceFiles'].items():
  source=HERE/name;require(source.stat().st_size==pin['bytes']and sha(source)==pin['sha256'],'Frozen helper source drift');shutil.copy2(source,helper_sources/name);require(sha(helper_sources/name)==pin['sha256'],'Full helper body copy binding')
 for path in sorted(target.rglob('*')):
  if path.is_file():scan_file(path,str(path.relative_to(target)))
 save(target/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',{'passed':not HITS,'boundedNamedMarkersOnly':True,'sameNecessaryLiteralPrefixFilterAsClosedA1':True,'markerClasses':sorted(MARKERS),'findings':HITS,'scannedObjects':len(SCANNED),'scannedBytes':sum(r['bytes']for r in SCANNED),'allCopiedFullTarStreamsAndZipJarEntriesReviewed':True,'noLocalNativeArchiveRead':True,'scanned':SCANNED});require(not HITS,'Marker findings retained; do not close')
 metrics=raw['arms'][0]['rawMetrics'];rr=review['arms'][0];owner=(1000000,100000,1000000,100000)[arm-1]
 require(metrics['allArrivalP99Ns']==rr['allArrivalP99Ns']and metrics['acceptedOrdersInArrivalWindow']==rr['acceptedWithinArrivalWindow'],'Root/raw metric coherence')
 label=('A1','B1','A2','B2')[arm-1]
 text=f'''# Closed CPU owner-poll {label} evidence\n\nOne fresh33792@500/s long lineage, source{SOURCE}/code{CODE}; owner requested maximum park{owner}ns and constantserver/driver100000ns/read8/chunk6144/Fetch16/businesscap4/leader0/sync2. Complete actualcollection: {len(before['actual-collection']['files'])} files/{sum(r['bytes']for r in before['actual-collection']['files'].values())}bytes, both originalTARs preserved. Root independently verified{review['outerFiles']}outerfiles/{review['outerDirectories']}directories/{review['outerLogicalBytes']}logicalbytes and{review['rawInputFiles']}rawinputs.\n\nActual all-arrival scheduled-to-reply nearest-rankp99 {rr['allArrivalP99Ns']}ns; acceptedwithin67.584s {rr['acceptedWithinArrivalWindow']}; windowgoodput {rr['arrivalWindowGoodputPerSecond']}/s. Accepted {metrics['confirmedAcceptedUniqueOrders']}; notSent {metrics['notSent']}; unknownObserved {metrics['unknownObserved']}; unknownFinal {metrics['unknownFinal']}; serverRejected {metrics['serverRejected']}; schedulerlate-over20ms {metrics['schedulerLatenessOver20ms']}. Values come from this arm's exact strict raw result and independent root review, not A1constants. One finite arm is not an A/Bspeedup, stability/SLA/100M guarantee or combinedendurance.\n\nCurrent collection/config/launch/close/execution/rootreview/helper and every actual priorcollection-gate/private-push pair are copied byte-exact. Sharedcollector/controller/stage/preparation/historicalfailures are referenced by immutableA1inventory{A1_INVENTORY_SHA}/closure{A1_CLOSED_SHA}, with exact sharedfile rows; their bodies are not recopied. Original absolute paths are preserved; REGISTRATION/SOURCE_BEFORE_COPY map local archive subtrees. The current fullouterTAR also retains all explicit actualstaged39sources and priorreceipts.\n\nCopybefore/after fullSHA/bytes/modes/uid/gid/directory/emptydir closure and knownmarker review include allfullTARstreams and ZIP/JARentries. No sparseextraction, rawauditor/collector/business/JVM rerun, SSH/Git/PGwrite/signals/resources/deletion. No localnative archive rescanned. INVENTORY excludes onlyitself andCLOSED; CLOSED binds it. Allfourarm ABAB interpretation is separate from this currentarm archive.\n'''
 with(target/'README.md').open('x')as output:output.write(text)
 require(all(snapshot(source)==before[name]for name,source in trees.items()),'Closed originals changed after markerreview')
 allrows=snapshot(target);save(target/'INVENTORY.json',{'scope':'Only current explicit closed owner-poll arm%d'%arm,'excludedSelfAndClosure':['INVENTORY.json','CLOSED.json'],'files':allrows['files'],'directories':allrows['directories'],'payloadFileCount':len(allrows['files']),'payloadBytes':sum(r['bytes']for r in allrows['files'].values())})
 for name,r in allrows['files'].items():require(row(target/name)==r,'Final payload SHA/mode/owner drift')
 save(target/'CLOSED.json',{'schemaVersion':1,'passed':True,'arm':arm,'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inventorySha256':sha(target/'INVENTORY.json'),'files':len(allrows['files']),'directories':len(allrows['directories']),'payloadBytes':sum(r['bytes']for r in allrows['files'].values()),'allCurrentOriginalCollectionAndTarsRetained':True,'currentSourceCopyBeforeAfterEqual':True,'fullPayloadShaModesOwnersAndEmptyDirectoryClosureVerified':True,'sharedA1ReferencesImmutable':True,'knownMarkerReviewPassed':True,'noSparseExtraction':True,'noRemoteOrBusinessOrRawAuditRerun':True,'closureExcludes':['INVENTORY.json','CLOSED.json']})
 print(json.dumps({'passed':True,'arm':arm,'inventorySha256':sha(target/'INVENTORY.json'),'closedSha256':sha(target/'CLOSED.json'),'files':len(allrows['files']),'directories':len(allrows['directories']),'payloadBytes':sum(r['bytes']for r in allrows['files'].values())}))
if __name__=='__main__':main()
