"""Closed local owner proof copy/stream review only: no subprocess or original mutation."""
from pathlib import Path,PurePosixPath
import datetime,hashlib,io,json,os,re,shutil,stat,tarfile,zipfile
HERE=Path(__file__).resolve().parent
BASE=HERE.parent
WORKSPACE=BASE.parents[2]
OUT=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3/local-native-validation-r1'
def need(ok,message):
 if not ok:raise AssertionError(message)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb')as source:
  for block in iter(lambda:source.read(1024**2),b''):h.update(block)
 return h.hexdigest()
def write(path,value):
 with path.open('x')as target:json.dump(value,target,indent=2);target.write('\n')
def pin(path):
 s=path.lstat();need(stat.S_ISREG(s.st_mode)and not path.is_symlink()and s.st_nlink==1,'Regular independent source required')
 return {'bytes':s.st_size,'sha256':sha(path),'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid}
def census(root):
 files={};directories={}
 for path in [root]+sorted(root.rglob('*')):
  relative=str(path.relative_to(root));s=path.lstat();need(not path.is_symlink(),'Links refused')
  if stat.S_ISDIR(s.st_mode):directories[relative]={'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid}
  else:files[relative]=pin(path)
 return {'source':str(root),'files':files,'directories':directories}
def matching_census(root,expected):
 actual=census(root);return actual['files']==expected['files']and actual['directories']==expected['directories']
def safe(name):
 p=PurePosixPath(name);need(name==str(p)and not p.is_absolute()and '..'not in p.parts,'Unsafe member path');return name
PATTERN=re.compile(rb'(?P<privateKey>-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----)|(?P<githubToken>gh[pousr]_[A-Za-z0-9]{30,})|(?P<awsAccess>(?:AKIA|ASIA)[A-Z0-9]{16})|(?P<runpodToken>rpa_[A-Za-z0-9]{20,})|(?P<openaiToken>sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,})|(?P<slackToken>xox[baprs]-[A-Za-z0-9-]{20,})')

# Every alternative in the exact original pattern starts with one of these literals.
# Prefix-free blocks cannot match; their full bytes are still hashed and counted.
ORIGINAL_PATTERN=PATTERN
FAST_PREFIXES=(b'-----BEGIN ',b'gh',b'AKIA',b'ASIA',b'rpa_',b'sk-',b'xox')
class PrefixFilteredPattern:
 def finditer(self,data):
  if not any(prefix in data for prefix in FAST_PREFIXES):return iter(())
  return ORIGINAL_PATTERN.finditer(data)
PATTERN=PrefixFilteredPattern()

SCANNED=[];FINDINGS=[];ZIP_REVIEWS=[]
def scan(stream,label):
 h=hashlib.sha256();count=0;tail=b'';hits=set()
 for block in iter(lambda:stream.read(1024**2),b''):
  h.update(block);both=tail+block
  for match in PATTERN.finditer(both):hits.add((match.lastgroup,max(0,count-len(tail)+match.start())))
  count+=len(block);tail=both[-256:]
 for kind,offset in sorted(hits):FINDINGS.append({'path':label,'kind':kind,'offset':offset,'classification':'REQUIRES_REVIEW_NO_AUTOMATIC_REDACTION'})
 result={'path':label,'bytes':count,'sha256':h.hexdigest()};SCANNED.append(result);return result

def zip_scan(data,label):
 need(len(data)<=32*1024**2,'Bounded ZIP/JAR body');rows=[];seen=set()
 with zipfile.ZipFile(io.BytesIO(data))as archive:
  for entry in archive.infolist():
   safe(entry.filename.rstrip('/'));need(entry.filename not in seen,'Duplicate ZIP entry');seen.add(entry.filename)
   if entry.is_dir():continue
   need(entry.file_size<=32*1024**2,'Bounded ZIP entry')
   with archive.open(entry)as stream:row=scan(stream,label+'!'+entry.filename)
   need(row['bytes']==entry.file_size,'ZIP entry length');rows.append(row)
 ZIP_REVIEWS.append({'path':label,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'allEntriesReadWithCrcAndSha':True,'entries':rows})

def copy_scope(name,expected):
 source=Path(expected['source']);need(matching_census(source,expected),'Closed scope drift beforecopy '+name);target=OUT/name
 for relative,r in sorted(expected['directories'].items(),key=lambda pair:len(Path(pair[0]).parts)):
  directory=target if relative=='.'else target/relative;directory.mkdir(parents=True,exist_ok=True);directory.chmod(r['mode'])
 for relative,r in expected['files'].items():
  output=target/relative;need(not output.exists(),'Never overwrite copy');shutil.copy2(source/relative,output);need(pin(output)==r and pin(source/relative)==r,'Exact copy SHA/mode/owner drift')
 need(matching_census(target,expected),'Copied scope full directory/file closure '+name)

def main():
 plan=json.loads((HERE/'COPY_PLAN.json').read_text());need(shutil.disk_usage(WORKSPACE).free>plan['bounds']['freeBytesFloor']+160*1024**2,'Free copy floor')
 manifest_path=BASE/'owner-poll-local-native-r1/closed-originals-r2/manifest.json';need(sha(manifest_path)==plan['fullManifestSha256'],'Exact native manifest');manifest=json.loads(manifest_path.read_text());entries=manifest['entries'];byname={r['path']:r for r in entries}
 need(len(entries)==len(byname)==306,'Exact306member closure');omitted={r['path']for r in plan['recordingOmissions']};need(len(omitted)==18,'Exact18recording omissions');need({r['path']for r in entries if r['type']=='file'and r['path'].endswith('.rec')}==omitted,'Onlyrec omissions')
 need(OUT.is_dir()and not(OUT/'CLOSED.json').exists(),'Preserve existing incomplete-only archive')
 for name,scope in plan['scopes'].items():need(matching_census(OUT/name,scope)and matching_census(Path(scope['source']),scope),'Original completed scope copy drift')
 copied=[r for r in entries if r['type']=='file'and r['path']not in omitted]
 for r in copied:
  expected={k:r[k]for k in ['bytes','sha256','mode','uid','gid']}
  need(pin(OUT/'materialized'/r['path'])==pin(Path(r['source']))==expected,'Previously copied nonrecording binding drift')
 need(len(copied)==251 and sum(r['bytes']for r in copied)==77776079,'Exact previous copied closure')
 need((OUT/'MATERIALIZED_COPY_BINDINGS.json').is_file()and(OUT/'RECORDING_BODY_OMISSIONS.json').is_file(),'Prior copy plan receipts required')
 archive=OUT/'closed-native/native-originals.tar.gz';need(pin(archive)['sha256']==plan['fullTarSha256']and archive.stat().st_size==plan['fullTarBytes'],'Full native TAR copy SHA');seen=set();member_rows=[]
 with tarfile.open(archive,'r|gz')as tar:
  for member in tar:
   name=safe(member.name);need(name in byname and name not in seen,'Native exact memberclosure');seen.add(name);r=byname[name];need((member.mode,member.uid,member.gid)==(r['mode'],r['uid'],r['gid']),'Native TAR mode/owner')
   if member.isdir():need(r['type']=='directory','Native directorytype');continue
   need(member.isfile()and r['type']=='file'and member.size==r['bytes'],'Native filetype/size');stream=tar.extractfile(member)
   if name.endswith(('.zip','.jar')):
    data=stream.read();row=scan(io.BytesIO(data),'fullTAR!'+name);zip_scan(data,'fullTAR!'+name)
   else:row=scan(stream,'fullTAR!'+name)
   need(row['bytes']==r['bytes']and row['sha256']==r['sha256'],'Native full memberSHA');member_rows.append({'path':name,'sha256':row['sha256'],'bytes':row['bytes']})
 need(seen==set(byname),'Allfiles/dirs/emptydirs nativeclosure');write(OUT/'FULL_NATIVE_TAR_REVIEW.json',{'passed':True,'archiveSha256':plan['fullTarSha256'],'all306MembersShaSizeModeUidGidAndDirectoryClosureVerified':True,'entries':306,'files':269,'directories':37,'logicalBytes':2493695183,'noSparseExtraction':True,'fileRows':member_rows})
 # Scan materialized and metadata bodies; the deliberately partial21B R1 TAR is bytes only.
 for path in sorted(OUT.rglob('*')):
  if not path.is_file()or path==archive:continue
  label=str(path.relative_to(OUT))
  with path.open('rb')as stream:scan(stream,label)
  if path.suffix in ('.zip','.jar'):zip_scan(path.read_bytes(),label)
 write(OUT/'ZIP_JAR_ENTRY_REVIEW.json',{'passed':True,'occurrences':len(ZIP_REVIEWS),'entryOccurrences':sum(len(r['entries'])for r in ZIP_REVIEWS),'reviews':ZIP_REVIEWS})
 write(OUT/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',{'passed':not FINDINGS,'boundedKnownMarkerReviewOnly':True,'findings':FINDINGS,'scannedObjects':len(SCANNED),'scannedBytes':sum(r['bytes']for r in SCANNED),'fullTarAndZipJarEntriesIncluded':True,'noPrivateKeyEnvironmentOrPgBodyRequested':True,'scanned':SCANNED});need(not FINDINGS,'Marker findings preserved for review; archive notclosed')
 for name,scope in plan['scopes'].items():need(matching_census(Path(scope['source']),scope),'Closed source drift aftercopy')
 for r in copied:need(pin(Path(r['source']))=={k:r[k]for k in ['bytes','sha256','mode','uid','gid']},'Nonrecording source changed afterreview')
 original_source=json.loads((OUT/'materialized/preparation/SOURCE_FROZEN_R2.json').read_text());need(original_source['original25SourcesAndBothFreezesUnchanged']is True,'R2source binding');raw=json.loads((OUT/'raw-audit/COMPACT_NATIVE_PROOF.json').read_text());need(raw['passed']is True and raw['localPerformanceClaimed']is False and[r['schedulerTimingValid']for r in raw['arms']]==[True,False],'Qualified functionalonly scope')
 (OUT/'README.md').open('x').write('''# Local owner-poll native functional pair\n\nThe first local evidence-copy wrapper reached its180s limit while scanning the2.493GB recording stream for known markers. All251 nonrecording copies had completed and remain unchanged. The timeout tool observation/source/registration are preserved in archiver/. A separateR2 review resumes only the already-copied incomplete proof, verifies full SHA/mode/owner closure, and applies the same regex only when a necessary literal prefix exists in a block. Prefix-free blocks are fully hashed/counted too. This is an archival retry, not a business or raw-audit rerun.\n\nTwo fresh SHORT6400 lineages use the same new source9771976/artifact23586ccc, server-driver100us, read8/chunk6144/Fetch16/businesscap4, leader0/sync2/42000. Parent owner requested maximum park is1ms then100us. All6400 original arrivals perarm were accepted; canonical/reference/all3replica checks and actual constructed owner/22factory objects passed. These are two separate6400 histories, not one12800 endurance run.\n\nThe1ms arm had0 scheduler arrivals over20ms late and the100us arm had40: scheduler timing is valid only for the firstarm. The entire local pair is FUNCTIONAL_ONLY, with no performance comparison, capacity promotion, measuredsleep guarantee or100M claim. Local parent argv comes from the owned launch handle and ps observations, not independently decoded kernel NUL argv. Native zero-UNKNOWN closure is not a new injected UNKNOWN/replay scenario; separate unit evidence covers wire/failure/credit cases.\n\nThe full306member archive contains269files/37directories,2,493,695,183 logical bytes. All18 recording bodies remain intact inside closed-native/native-originals.tar.gz. Their exact paths/SHA/bytes/modes/owners are listed in RECORDING_BODY_OMISSIONS.json; only these18 bodies are omitted from the materialized subset. All251 nonrecording native/input/preparation members (77,776,079bytes), all72 consumed raw inputs, actual JAR/JDK inputs, runtime source/config/freezes, guard source ZIPs/logs, process identity/monitoring and closed lifecycle receipts are materialized via source copies. No TAR/sparse extraction occurred. Implicit materialized prefix containers are newly created local directories; original directory rows preserve modes/owners.\n\nHistorical failures are retained without relabeling: root rawexecution-r1 failed beforelaunch from wrapper syntax; r2 failed capture because Python3.9 streamingtar rejected compresslevel, leaving103303B manifest and21B partialTAR; r3 retains its preparationfailure and then actual successfulR2 capture/audit. The original4runtimehelpers/config, original25source bytes and oldsource/parserfreezes remain exact. R2 uses an outer gzip stream and keeps failedR1 bodies under prior-derived-failures/capture-r1, outside native/. Three new real streamfixtures passed, alongside18 historical pureguards. The complete source/guard attempts and original failed scripts remain preserved.\n\nRoot execution1/2/3, full rawR2audit/compact proof and independent fullTar+72input+12800CSV review are copied unchanged. This archive independently verifies complete TAR member SHA/size/mode/uid/gid/directory closure, all source-copy SHA/size/mode/uid/gid, full known-marker and JAR/ZIP entry review. It does not rerun the raw auditor or any business/Java/SSH/Git action. Original source/receipts retain absolute provenance paths; MATERIALIZED_COPY_BINDINGS maps them into the archive. MANIFEST excludes only itself and CLOSED; CLOSED binds it.\n''')
 inventory=census(OUT);need(len(inventory['files'])<512 and sum(r['bytes']for r in inventory['files'].values())<160*1024**2,'Finite copied proof bounds');write(HERE/'COPY_COMPLETE_R2.json',{'passed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceScopesUnchanged':True,'materializedFiles':251,'fullNativeEntries':306,'logicalBytes':2493695183,'recordingBodiesOnlyInTar':18,'knownMarkerFindings':0,'resumedOnlyAfterRegisteredLocalArchiverTimeout':True,'sameRegexNecessaryLiteralPrefixFilterOnly':True,'payloadFilesBeforeArchiverLogs':len(inventory['files']),'payloadBytesBeforeArchiverLogs':sum(r['bytes']for r in inventory['files'].values()),'freeBytes':shutil.disk_usage(WORKSPACE).free});print((HERE/'COPY_COMPLETE_R2.json').read_text())
if __name__=='__main__':main()
