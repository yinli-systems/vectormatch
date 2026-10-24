"""Author second-pass read-only artifact verification. This is not an independent peer review."""
from pathlib import Path
import hashlib,json,stat,struct,tarfile,zipfile,datetime
R=Path(__file__).resolve().parent;S=R.parent/'read-window32-linux-metadata-preparation-r1';B=R.parents[3]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,v):
 with(R/name).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
closed=json.loads((S/'CLOSED.json').read_text());inv=json.loads((S/'INVENTORY.json').read_text());frozen=json.loads((S/'SOURCE_FROZEN.json').read_text());config=json.loads((S/'metadata-config.json').read_text());prep=json.loads((S/'PREPARED_NOT_EXECUTED.json').read_text())
assert sha(S/'CLOSED.json')=='f9c4767d3516189fea98617a5ccb7d16d52b34bfabd1fb39a0f4edb41a7cc51c'
assert sha(S/'INVENTORY.json')==closed['inventorySha256'] and sha(S/'SOURCE_FROZEN.json')==closed['sourceFrozenSha256'] and sha(S/'metadata-config.json')==closed['metadataConfigSha256']
expected=set(inv['files'])|{'INVENTORY.json','CLOSED.json'};actual=set();actualdirs=set()
for p in sorted(S.rglob('*')):
 assert not p.is_symlink();name=str(p.relative_to(S));st=p.lstat()
 if p.is_file():actual.add(name)
 elif p.is_dir():actualdirs.add(name)
 else:raise RuntimeError('special file')
assert actual==expected and actualdirs=={row['path']for row in inv['directories']}
for name,row in inv['files'].items():
 p=S/name;st=p.stat();assert {'bytes':st.st_size,'sha256':sha(p),'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}==row
for row in inv['directories']:
 p=S/row['path'];st=p.stat();assert {k:row[k]for k in ['mode','uid','gid','empty']}=={'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid,'empty':not any(p.iterdir())}
for k in ['activeSources','baselineSources']:
 for name,row in frozen[k].items():assert (S/name).stat().st_size==row['bytes']and sha(S/name)==row['sha256']
assert sha(S/'metadata-inputs.tar.gz')==config['bundleSha256']==prep['bundleSha256']
seen=set()
with tarfile.open(S/'metadata-inputs.tar.gz','r:gz')as t:
 for member in t:
  assert member.isfile()and member.name in config['rows']and member.name not in seen;seen.add(member.name)
  body=t.extractfile(member).read();row=config['rows'][member.name];assert len(body)==row['bytes']and member.mode==row['mode']and hashlib.sha256(body).hexdigest()==row['sha256'];assert body==(S/'inputs'/member.name).read_bytes()
assert seen==set(config['rows'])and len(seen)==6
capture=json.loads((S/'provenance/actual-17-classpath.json').read_text());assert len(capture['files'])==17and sha(S/'provenance/actual-17-classpath-bodies.zip')==capture['externalTestClasspathBodiesZipSha256']
with zipfile.ZipFile(S/'provenance/actual-17-classpath-bodies.zip')as z:
 assert len(z.namelist())==17
 for i,(name,row)in enumerate(capture['files'].items()):
  data=z.read(str(i)+'/'+Path(name).name);assert len(data)==row['bytes']and hashlib.sha256(data).hexdigest()==row['sha256']
compiled=json.loads((S/'helper-compile-r1/EXECUTION.json').read_text());registration=json.loads((S/'helper-compile-r1/REGISTRATION.json').read_text());helper=S/'inputs/classes/io/vectormatch/cluster/ReadWindow32LinuxDistributionObservation.class';raw=helper.read_bytes();assert raw[:4]==b'\xca\xfe\xba\xbe'and struct.unpack('>H',raw[6:8])[0]==65and sha(helper)==compiled['class']['sha256']==prep['helperClassSha256'];assert compiled['exitCode']==0and compiled['inputsUnchanged']and compiled['compilerJvmExecuted']and not compiled['metadataJvmExecuted']
# Inspect class constant pool without javap, Java or class execution.
cp=[None]*struct.unpack('>H',raw[8:10])[0];at=10;i=1
while i<len(cp):
 tag=raw[at];at+=1
 if tag==1:
  length=struct.unpack('>H',raw[at:at+2])[0];at+=2;cp[i]=('utf8',raw[at:at+length].decode('utf-8'));at+=length
 elif tag in [3,4]:cp[i]=(tag,raw[at:at+4]);at+=4
 elif tag in [5,6]:cp[i]=(tag,raw[at:at+8]);at+=8;i+=1
 elif tag in [7,8,16,19,20]:cp[i]=(tag,struct.unpack('>H',raw[at:at+2])[0]);at+=2
 elif tag in [9,10,11,12,17,18]:cp[i]=(tag,*struct.unpack('>HH',raw[at:at+4]));at+=4
 elif tag==15:cp[i]=(tag,raw[at],struct.unpack('>H',raw[at+1:at+3])[0]);at+=3
 else:raise RuntimeError('unknown class constant tag')
 i+=1
def utf(i):assert cp[i][0]=='utf8';return cp[i][1]
refs=[]
for entry in cp:
 if entry and entry[0]in [10,11]:
  klass=cp[entry[1]];name_type=cp[entry[2]];refs.append({'class':utf(klass[1]),'name':utf(name_type[1]),'descriptor':utf(name_type[2])})
constructors=[r for r in refs if r['name']=='<init>']
assert not any(r['class'].startswith(('io/aeron/','io/vectormatch/cluster/RetentionBatchOwner','io/vectormatch/cluster/RetentionClient'))for r in constructors)
assert not any(r['name']in ['launch','start','runReadWindow32LongCuts','runEventFetchPageLongCuts','run']and r['class'].startswith('io/')for r in refs)
assert {'java/lang/reflect/Method','java/lang/Class'}<={r['class']for r in refs}
# Recompute the actual four-anchor fingerprint. Agrona's full JAR is separately SHA-pinned; its DirectBuffer anchor comes from aeron-all.
fp=hashlib.sha256();lib=S/'inputs/lib'
anchors=[('io.vectormatch.cluster.RetentionNodeMainV3','cluster-0.1.0-SNAPSHOT.jar'),('io.vectormatch.core.MatchingEngine','core-0.1.0-SNAPSHOT.jar'),('io.aeron.driver.MediaDriver','aeron-all-1.53.3.jar'),('org.agrona.DirectBuffer','aeron-all-1.53.3.jar')]
for classname,jar in anchors:fp.update(classname.encode());fp.update((lib/jar).read_bytes())
assert fp.hexdigest()==frozen['actualApplicationCodeFingerprint']=='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea'
guards=json.loads((S/'GUARDS_EXECUTION.json').read_text());assert guards['exitCode']==0and guards['sourceUnchanged'];text=(S/'guards.stderr').read_text();assert text.count(' ... ok')==17and 'Ran 17 tests'in text and text.rstrip().endswith('OK')
assert not any((S/n).exists()for n in ['actual-linux-distribution-observation.json','remote-receipt.json','SUCCESS.json','REGISTRATION.json'])
assert sha(S/'stage_metadata.py')==prep['stageSourceSha256']and sha(S/'remote_metadata.py')==prep['remoteRunnerSha256']
assert sha(R.parent/'remote.py')=='0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73'
output=R.parent/'read-window32-linux-metadata-execution-r1';assert not output.exists()
command=['python3','-B',str(S/'stage_metadata.py'),'--execute','--root-reviewed-config-sha256',sha(S/'metadata-config.json'),'--execution-output',str(output)]
save('REVIEW.json',{'schemaVersion':1,'scope':'AUTHOR_SECOND_PASS_READ_ONLY_METADATA_PREPARATION_REVIEW','reviewerWasOriginalAuthor':True,'independentPeerReview':False,'passed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'closedSha256':sha(S/'CLOSED.json'),'sourceFrozenSha256':sha(S/'SOURCE_FROZEN.json'),'inventorySha256':sha(S/'INVENTORY.json'),'payloadFiles':len(inv['files']),'directories':len(inv['directories']),'allFileShaSizeModesOwnersAndEmptyDirsVerified':True,'sixCompleteBundleMembersVerified':True,'all17ClasspathBodiesVerified':True,'helperClassMajor':65,'classMethodRefs':refs,'constructorRefs':constructors,'actualApplicationCodeFingerprintRecomputed':fp.hexdigest(),'fingerprintAnchors':anchors,'unusedAgronaJarIndependentlyFullShaPinned':True,'actualCompileExitCode':0,'pureGuardsReadBack':17,'javaTestsSshRemoteExecutedByThisReview':False,'metadataLinuxObservationStillPending':True,'exactFutureStageArgv':command,'futureExecutionOutputCurrentlyAbsent':True,'expectedLinuxHost':'ed6c0673f5cb','expectedJavaPath':config['java'],'expectedLinuxJavaSha256':config['javaSha256'],'expectedLinuxJdkReleaseSha256':config['releaseSha256'],'constraints':['Future runtime facts must come from actual metadata receipt; current source-preparation pending flags remain historical.','Source/constant-pool review supports no agent construction; metadata Plan computations instantiate only temporary in-memory reference/codec objects.','An actual timeout or SSH failure must retain original local and remote scopes; no automatic new attempt under another execution scope.','The helper is not executed by this review; this does not prove future Linux success, native qualification or performance.','Compiler default annotation-processing discovery note is retained; this review does not recompile or execute processors.']})
print(json.dumps({'passed':True,'independentPeerReview':False,'reviewSha256':sha(R/'REVIEW.json'),'freshOutput':str(output),'configSha256':sha(S/'metadata-config.json')}))
