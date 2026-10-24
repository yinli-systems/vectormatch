#!/usr/bin/env python3
"""Independent Python binary cache/event verification; no Java/matching/network/database execution."""
from pathlib import Path,PurePosixPath
import hashlib,json,struct,itertools,collections,traceback,zipfile,stat
ROOT=Path('/Users/kevin/Documents/ChatGPT/App 2');JOB=ROOT/'runtime/cloud/cpu-20261024/original-full-ledger-offline-r1';OUT=Path(__file__).resolve().parent
EXPECTED_ENGINE='ea7b98a23a30b5ddde84db4520e3e915fd07a73900e2c3aa41ee28c8614b5b65';EXPECTED_BUNDLE='a7aaa3659ca9dd9ac3f3081eaf222d44a565a13287bc0d272373340411247608';INPUTS={}
def require(v,m):
 if not v:raise AssertionError(m)
def read(p):
 b=p.read_bytes();INPUTS[str(p)]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};return b
def js(p):return json.loads(read(p))
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
class Reader:
 def __init__(self,b):self.b=b;self.p=0;self.strings=0
 def take(self,n):
  require(0<=n<=len(self.b)-self.p,'Truncated binary field');v=self.b[self.p:self.p+n];self.p+=n;return v
 def number(self,fmt):return struct.unpack('>'+fmt,self.take(struct.calcsize('>'+fmt)))[0]
 def i(self):return self.number('i')
 def q(self):return self.number('q')
 def byte(self):return self.number('b')
 def count(self,maximum=10000000):
  n=self.i();require(0<=n<=maximum,'Invalid bounded item count');return n
 def text(self):
  n=self.i()
  if n==-1:return None
  require(0<=n<=65536 and n<= (len(self.b)-self.p)//2,'Invalid UTF16BE code-unit length');self.strings+=1;return self.take(n*2).decode('utf-16-be','strict')
 def enum(self,names,nullable=False):
  n=self.byte()
  if n==-1 and nullable:return None
  require(0<=n<len(names),'Invalid signed enum ordinal');return names[n]
def command(r):
 kind=r.byte();require(kind in (0,1,2),'Unknown cached command');v={'accountId':r.q(),'producerId':r.text(),'requestSeq':r.q()}
 if kind==0:v.update(asset=r.enum(['BASE','QUOTE'],True),amount=r.q())
 elif kind==1:v.update(clientOrderId=r.text(),side=r.enum(['BUY','SELL'],True),priceTicks=r.q(),quantityLots=r.q(),timeInForce=r.enum(['GTC','IOC'],True))
 else:v['orderId']=r.q()
 return kind,v
def result(r):return {'code':r.enum(['ACCEPTED','REJECTED','INVALID_REQUEST','IDEMPOTENCY_CONFLICT','STALE_SEQUENCE']),'reason':r.text(),'commandSeq':r.q(),'orderId':r.q(),'remainingQuantity':r.q(),'tradeCount':r.i()}
def snapshot(data):
 require(hashlib.sha256(data[:-32]).digest()==data[-32:],'Original snapshot inner SHA');r=Reader(data[:-32]);require((r.i(),r.i())==(0x564D4331,2),'Original snapshot format');cache=r.i();limits=[r.i() for _ in range(4)];require(cache==1024 and all(1<=n<=10000000 for n in limits),'Original explicit cache/limits')
 counters=dict(zip(['commandSeq','eventSeq','marketSeq','nextOrderId','totalBase','totalQuote'],[r.q() for _ in range(6)]));require((counters['commandSeq'],counters['eventSeq'],counters['marketSeq'])==(4609,6214,6194),'Original snapshot counters')
 accounts={}
 for _ in range(r.count(limits[0])):
  aid=r.q();balances=[r.q() for _ in range(4)];require(aid>0 and aid not in accounts and all(n>=0 for n in balances),'Account closure');accounts[aid]=balances
 require(sum(x[0]+x[1] for x in accounts.values())==counters['totalBase'] and sum(x[2]+x[3] for x in accounts.values())==counters['totalQuote'],'Snapshot account conservation')
 orders={}
 for _ in range(r.count(limits[2])):
  oid,aid,client=r.q(),r.q(),r.text();side=r.enum(['BUY','SELL']);price,original,remaining=r.q(),r.q(),r.q();tif=r.enum(['GTC','IOC']);status=r.enum(['OPEN','PARTIALLY_FILLED','FILLED','CANCELLED','EXPIRED']);accepted=r.q()
  require(0<oid<counters['nextOrderId'] and oid not in orders and aid in accounts and price>0 and 0<=remaining<=original and original>0 and 0<accepted<=4609,'Order structural bounds');orders[oid]={'accountId':aid,'clientOrderId':client,'side':side,'priceTicks':price,'originalQuantity':original,'remainingQuantity':remaining,'timeInForce':tif,'status':status,'acceptedCommandSeq':accepted}
 producers={};entries={};kinds=collections.Counter()
 for _ in range(r.count(limits[1])):
  aid,name,high=r.q(),r.text(),r.q();key=(aid,name);require(aid>0 and key not in producers and high>0,'Producer identity/high water');n=r.count(cache);previous=0
  for _ in range(n):
   kind,cmd=command(r);res=result(r);require(cmd['accountId']==aid and cmd['producerId']==name and previous<cmd['requestSeq']<=high,'Cached producer/sequence binding');previous=cmd['requestSeq'];seq=res['commandSeq'];require(0<seq<=4609 and seq not in entries,'Cached result command sequence');entries[seq]={'command':cmd,'result':res};kinds[kind]+=1
  require(n==0 or previous==high,'Permanent producer high water');producers[key]={'highWater':high,'cached':n}
 require(r.p==len(r.b) and set(entries)==set(range(1,4610)),'All binary bytes and contiguous cached command history');return {'counters':counters,'cachePerProducer':cache,'limits':limits,'accountCount':len(accounts),'orderCount':len(orders),'producerCount':len(producers),'cachedCommands':len(entries),'commandKinds':dict(kinds),'utf16StringsDecodedStrictly':r.strings},entries

def main():
 reg=js(JOB/'REGISTRATION.json');require(reg['originalSourceCommit']=='e1db2e755a834234efb60b7a1ed291b31ce33c16','Original source revision')
 for name,row in reg['inputs'].items():
  p=Path(name);require(p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'Registered pristine input differs: '+name)
 bundle=ROOT/'runtime/cloud/cpu-20261024/app-restore-build/bundle';manifest_path=bundle/'DEPLOYMENT.json';manifest=js(manifest_path);require(sha(manifest_path)==EXPECTED_BUNDLE and len(manifest['files'])==85,'Exact pristine 85-path manifest')
 for name,digest in manifest['files'].items():
  q=PurePosixPath(name);require(not q.is_absolute() and '..' not in q.parts,'Unsafe bundle path');p=bundle/name;require(p.is_file() and not p.is_symlink() and sha(p)==digest,'Pristine manifest file differs: '+name)
 actual={str(p.relative_to(bundle)) for p in bundle.rglob('*') if p.is_file()};require(actual==set(manifest['files'])|{'DEPLOYMENT.json'},'Pristine bundle exact file closure')
 for name in ['core/src/main/java/io/vectormatch/core/MatchingEngine.java','projector/src/main/java/io/vectormatch/projector/PostgresEventStore.java']:
  require(sha(ROOT/name)==manifest['sourceSha256'][name],'Authoritative original format/encoder source differs');read(ROOT/name)
 java=js(JOB/'java-arguments.json');javac=js(JOB/'javac-arguments.json');cp=java[java.index('-cp')+1].split(':');cp_paths=[Path(p) for p in cp];require(cp_paths[0]==JOB/'classes' and java[java.index('-cp')+2]=='OriginalFullLedgerOffline','Helper exact classpath/main')
 jars=cp_paths[1:];require(len(jars)==10 and set(jars)==set((bundle/'dist/projector/lib').glob('*.jar')) and javac[javac.index('-cp')+1].split(':')==[str(p) for p in jars],'All and only ten exact classpath JARs')
 for p in jars:require(sha(p)==manifest['files'][str(p.relative_to(bundle))]==reg['inputs'][str(p)]['sha256'],'Classpath JAR manifest/registration binding')
 classes={}
 for p in sorted((JOB/'classes').glob('*.class')):
  b=read(p);require(b[:4]==bytes.fromhex('cafebabe') and struct.unpack('>H',b[6:8])[0]==65 and b'OriginalFullLedgerOffline.java' in b,'JDK21 helper class/source-file binding');classes[p.name]=INPUTS[str(p)]
 require(set(classes)=={'OriginalFullLedgerOffline.class','OriginalFullLedgerOffline$Entry.class'},'Exact helper class directory closure')
 original=Path(java[-3]);pg=Path(java[-2]);derived=JOB/'run-r1';original_bytes=read(original);require(hashlib.sha256(original_bytes).hexdigest()==EXPECTED_ENGINE,'Original canonical input SHA');parsed,entries=snapshot(original_bytes)
 data=read(derived/'derived-command-results.ndjson');count=0
 for count,line in enumerate(data.splitlines(),1):
  row=json.loads(line);require(set(row)=={'commandSeq','command','expectedAndActualResult','replayed'} and row['commandSeq']==count and row['command']==entries[count]['command'] and row['expectedAndActualResult']==entries[count]['result'] and row['replayed'] is False,'Derived command/result differs from parsed original cache at '+str(count))
 require(count==4609,'All 4609 cached command/results independently matched')
 require(read(derived/'derived-canonical-engine.bin')==original_bytes,'Exact final full engine bytes');pg_bytes=read(pg);event_bytes=read(derived/'derived-events.ndjson');new_hash=hashlib.sha256();old_hash=hashlib.sha256();event_seq=market_seq=trades=0
 for number,(payload,line) in enumerate(itertools.zip_longest(event_bytes.splitlines(),pg_bytes.splitlines()),1):
  require(payload is not None and line is not None,'Derived/PG event row count differs');event=json.loads(payload);row=json.loads(line);require(set(event)=={'accountId','detail','eventSeq','makerOrderId','marketSeq','orderId','priceTicks','quantityLots','side','takerOrderId','type'},'Event payload key set')
  require(event['eventSeq']==row['eventSeq']==number and event['marketSeq']==row['marketSeq'] and event['type']==row['eventType'],'Every PG typed column/event identity')
  require(payload.decode('utf8','strict')==row['originalJacksonReencoding'],'Every original canonical Jackson payload string');digest=hashlib.sha256(payload).hexdigest();require(digest==row['storedPayloadSha256']==row['reencodedPayloadSha256'],'Every stored/reencoded payload SHA');require(event==json.loads(row['databaseJsonbText']),'Every PG JSONB semantic payload')
  require(all(type(event[k]) is int for k in ['accountId','eventSeq','makerOrderId','marketSeq','orderId','priceTicks','quantityLots','takerOrderId']),'Typed integer event fields');event_seq=number
  if event['marketSeq']!=0:market_seq+=1;require(event['marketSeq']==market_seq,'Public market sequence continuity')
  else:require(event['type']=='DEPOSIT','Private zero market sequence type')
  trades+=event['type']=='TRADE';new_hash.update(struct.pack('>i',len(payload)));new_hash.update(payload);t=event['type'].encode('ascii','strict');old_hash.update(struct.pack('>qqi',number,event['marketSeq'],len(t)));old_hash.update(t);old_hash.update(bytes.fromhex(digest))
 require((event_seq,market_seq,trades)==(6214,6194,1551),'Full event/market/trade counters');require(new_hash.hexdigest()=='2446bb44701b323158846b6f1ddf1f592d7c8e1ad19bed989905dbe155f47324','Canonical framed event ledger SHA');require(old_hash.hexdigest()=='5a438910c3c1c7af02dd9e494754341cd03664cf315eaec68d56824e69a24226','Prior PG framed ledger SHA')
 passed=js(derived/'PASS.json');require(passed['passed'] is True and passed['framedCanonicalEventLedgerSha256']==new_hash.hexdigest(),'Root PASS receipt binding')
 for name,row in passed['actualSources'].items():require(sha(Path(row['path']))==row['sha256'] and Path(row['path']).stat().st_size==row['bytes'] and Path(row['path']) in jars,'Actual original loaded class-source JAR binding')
 for name,row in reg['inputs'].items():require(sha(Path(name))==row['sha256'],'Input changed during independent audit')
 report={'passed':True,'scope':'Independent Python binary cache and ledger verification only; no matching algorithm reimplementation, no Java execution, SSH, SQL, cluster or business RPC. Historical derivation on copied inputs, not new command execution or durability proof.','pristineBundleManifestSha256':EXPECTED_BUNDLE,'pristineBundleFilesVerified':85,'exactClasspathJars':{str(p):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in jars},'helperClassesObservedPostRunBeforeAndAfterAudit':classes,'registeredJavaExecutableAndReleaseUnchanged':True,'javacExecutableCurrentOnly':{'path':javac[0],'bytes':Path(javac[0]).stat().st_size,'sha256':sha(Path(javac[0])),'limitation':'Javac executable was not included in pre-run registration; current artifact frozen only, no pre-compile hash attestation.'},'parsedOriginalSnapshot':parsed,'all4609OriginalCachedCommandResultsExactlyMatchDerivedRows':True,'all6214DerivedCanonicalPayloadsPgTypedColumnsStoredHashesAndJsonbMatch':True,'eventSeq':event_seq,'marketSeq':market_seq,'trades':trades,'framedCanonicalEventLedgerSha256':new_hash.hexdigest(),'previousPgFramedLedgerSha256':old_hash.hexdigest(),'completeFinalEngineBytesMatch':True,'snapshotSha256':EXPECTED_ENGINE,'inputsRead':INPUTS}
 (OUT/'PASS.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['passed','eventSeq','marketSeq','trades','framedCanonicalEventLedgerSha256','previousPgFramedLedgerSha256']},indent=2))
if __name__=='__main__':
 try:main()
 except BaseException as error:
  (OUT/'failure.json').write_text(json.dumps({'passed':False,'error':repr(error),'traceback':traceback.format_exc(),'inputsRead':INPUTS,'noJavaNetworkOrDatabaseExecution':True},indent=2)+'\n');raise
