from pathlib import Path
import base64, datetime, hashlib, io, json, shlex, stat, struct, tarfile, zipfile
O=Path(__file__).resolve().parent;B=O.parent
P=B/'read-window32-linux-metadata-preparation-r1';E=B/'read-window32-linux-metadata-execution-r1'
ROOT='/opt/vectormatch-cpu/preparation/cpu-read-window32-release-metadata-r1'
OBS='b9217e7d2adc2e0f1fea742c32fc56ed46984881b2f5405839f23595263efa9f'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def check(value,message):
 if not value:raise ValueError(message)
def file(p):
 st=p.lstat();check(stat.S_ISREG(st.st_mode)and not p.is_symlink(),'input not regular')
 return dict(bytes=st.st_size,sha256=sha(p),mode=stat.S_IMODE(st.st_mode),uid=st.st_uid,gid=st.st_gid)
def preparation():
 check(sha(P/'CLOSED.json')=='f9c4767d3516189fea98617a5ccb7d16d52b34bfabd1fb39a0f4edb41a7cc51c','preparation closure differs')
 check(sha(P/'INVENTORY.json')=='64b0adf45d5966b5f7cdfafd6b4fc14eb280753c2672be0c304fda55e5a572a7','preparation inventory differs')
 inv=read(P/'INVENTORY.json');files={str(p.relative_to(P)):file(p)for p in sorted(P.rglob('*'))if p.is_file()and str(p.relative_to(P))not in['CLOSED.json','INVENTORY.json']}
 dirs=[dict(path=str(p.relative_to(P)),mode=stat.S_IMODE(p.lstat().st_mode),uid=p.lstat().st_uid,gid=p.lstat().st_gid,empty=not any(p.iterdir()))for p in sorted(P.rglob('*'))if p.is_dir()]
 check(files==inv['files']and dirs==inv['directories'],'complete preparation bytes/metadata/empty dirs differ')
 check(len(files)==inv['fileCount']==46 and len(dirs)==inv['directoryCount']==9,'preparation member counts differ')
 check(sum(v['bytes']for v in files.values())==inv['bytes']==15907739,'preparation bytes differ')
 return files,dirs
before_preparation=preparation();before_execution={str(p.relative_to(E)):file(p)for p in sorted(E.rglob('*'))if p.is_file()}
check(len(before_execution)==9,'actual execution file inventory differs')
reg=read(E/'REGISTRATION.json');receipt=read(E/'remote-receipt.json');success=read(E/'SUCCESS.json');ssh=read(E/'ssh-execution.json');obs=read(E/'actual-linux-distribution-observation.json');config=read(P/'metadata-config.json')
check(sha(E/'actual-linux-distribution-observation.json')==OBS==receipt['observationSha256']==success['linuxObservationSha256'],'actual observation pin differs')
check(success['passed']is True and success['receiptSha256']==sha(E/'remote-receipt.json'),'success receipt differs')
check(ssh['exitCode']==0 and ssh['timedOut']is False and ssh['noAutomaticRetry']is True and ssh['stdoutSha256']==sha(E/'ssh.stdout')and ssh['stderrSha256']==sha(E/'ssh.stderr'),'actual SSH capture differs')
wire=read(E/'ssh.stdout');check(base64.b64decode(wire.pop('observationRawBase64'),validate=True)==(E/'actual-linux-distribution-observation.json').read_bytes(),'observation decode differs')
for key,name in [('stdoutBase64','java.stdout'),('stderrBase64','java.stderr')]:check(base64.b64decode(wire.pop(key),validate=True)==(E/name).read_bytes(),'actual Java output decode differs')
check(wire==receipt,'decoded SSH receipt differs')
check(reg['configSha256']==sha(P/'metadata-config.json')=='1dae0b808015de83f65d3b046940f41c9fa3f6ee17e5f749f952ae65b3f0369b','actual registration config differs')
check(reg['remoteRunnerSha256']==sha(P/'remote_metadata.py')and reg['remoteHelperSha256']==sha(B/'remote.py'),'actual registered runner/helper differs')
remote_command=shlex.split(reg['command'][-1]);check(remote_command[:3]==['python3','-B','-c']and len(remote_command)==5,'actual remote wrapper argv differs')
check(remote_command[3]==(P/'remote_metadata.py').read_text()and json.loads(base64.b64decode(remote_command[4]))==config,'executed remote source/config bytes differ')
check(config['root']==receipt['root']==ROOT and config['host']==receipt['registration']['hostname']=='ed6c0673f5cb','actual host/root differs')
check(config['rows']==receipt['stagedFiles']==receipt['registration']['inputInventory']and len(config['rows'])==6,'all six actual staged input records differ')
check(sha(P/'metadata-inputs.tar.gz')==config['bundleSha256'],'full input tar pin differs')
with tarfile.open(P/'metadata-inputs.tar.gz')as tar:
 members=tar.getmembers();check(len(members)==len({m.name for m in members})==6,'six exact regular bundle members required')
 check({m.name for m in members}==set(config['rows']),'bundle member set differs')
 for member in members:
  check(member.isfile()and not member.issym()and member.mode==config['rows'][member.name]['mode'],'regular bundle type/mode differs')
  body=tar.extractfile(member).read();pin=config['rows'][member.name]
  check(len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256']and body==(P/'inputs'/member.name).read_bytes(),'full bundle input body differs')
registration=receipt['registration'];execution=receipt['execution'];command=registration['command']
expected=[config['java'],'-Xmx128m','--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','-cp',ROOT+'/classes:'+':'.join(ROOT+'/lib/'+name for name in config['jarOrder']),'io.vectormatch.cluster.ReadWindow32LinuxDistributionObservation',ROOT+'/results/actual-distribution-observation.json']
check(command==expected,'exact actual JVM arguments differ')
identity=execution['actualProcessIdentity'];check(identity['commandSha256']==hashlib.sha256(b'\0'.join(x.encode()for x in command)+b'\0').hexdigest(),'actual full NUL argv SHA differs')
check(identity['pid']==execution['ownedParentPid']==69431 and identity['startTicks']==5325814 and identity['actualExecutable']==registration['actualJavaExecutable']==config['java'],'actual PID/start/executable differs')
check(execution['exitCode']==0 and execution['timedOut']is False and execution['metadataJvmExited']is True and execution['strictOwnedPidAbsentAfterWait']is True and execution['processIdentityObservationGap']is False and execution['allInputsUnchanged']is True,'normal exact child exit/absence or unchanged inputs differs')
check(config['javaSha256']==registration['javaExecutableSha256']==execution['javaExecutableSha256After']=='9cad3f2620d3ef2ed10b26f922af7e773d54fdaa05f615d6d6df014f3fec4155','pinned Linux Java before/after differs')
check(config['releaseSha256']==registration['jdkReleaseSha256']==execution['jdkReleaseSha256After']=='f83f6dcc966043c93cd498ac8e7ee7c310852074970d62c702e4ad2710002898','pinned Linux JDK release before/after differs')
for name,key in [('java.stdout','stdoutSha256'),('java.stderr','stderrSha256')]:check(sha(E/name)==execution[key]and(E/name).stat().st_size==0,'actual Java output hash/empty normal exit differs')
local=read(P/'provenance/local-observation.json');check(local['sourceCommit']==obs['sourceCommit']=='605eb43fcafd8fa0a6287304387c93c4d1bbddf6','actual source commit differs')
for key in ['sourceBaseCommit','actualCodeFingerprint','profileSha256']:check(local[key]==obs[key],'actual local/Linux immutable identity differs')
check(obs['schemaVersion']==2 and obs['fixedEventFetchCount']==32 and set(obs['plans'])=={'8','32'},'explicit actual Linux fixed-page32 schema differs')
for window in ['8','32']:check(obs['plans'][window]==local['plans']['page32-window'+window],'actual fixed-page32 local/Linux full Plan/config differs')
check({k:v for k,v in obs['plans']['8']['plan'].items()if k!='requestedReadWindow'}=={k:v for k,v in obs['plans']['32']['plan'].items()if k!='requestedReadWindow'},'actual selected windows differ beyond requested size')
check(obs['selectedWindowPlanDifferenceKeys']=={'fixedPage32':['requestedReadWindow']},'actual Plan difference keys differ')
check(obs['actualMetadataPlatform']==dict(osName='Linux',osArch='amd64',javaRuntimeVersion='21.0.13+9-LTS',javaVendor='Eclipse Adoptium'),'actual runtime platform differs')
check(len(obs['actualCodeSources'])==len(local['actualCodeSources'])==7 and len(obs['distributionJars'])==len(local['distributionJars'])==4,'seven origins/four distribution JARs required')
for a,b in zip(local['actualCodeSources'],obs['actualCodeSources']):
 check({k:v for k,v in a.items()if k!='path'}=={k:v for k,v in b.items()if k!='path'}and b['path']==ROOT+'/lib/'+Path(a['path']).name,'actual class origin relocation/body differs')
for name,a in local['distributionJars'].items():
 b=obs['distributionJars'][name];p=P/'inputs/lib'/name
 check({k:v for k,v in a.items()if k!='path'}=={k:v for k,v in b.items()if k!='path'}and b['path']==ROOT+'/lib/'+name and sha(p)==b['sha256']and p.stat().st_size==b['bytes'],'actual full distribution JAR differs')
digest=hashlib.sha256()
for name in ['io.vectormatch.cluster.RetentionNodeMainV3','io.vectormatch.core.MatchingEngine','io.aeron.driver.MediaDriver','org.agrona.DirectBuffer']:
 row=next(x for x in obs['actualCodeSources']if x['class']==name);digest.update(name.encode());digest.update((P/'inputs/lib'/Path(row['path']).name).read_bytes())
check(digest.hexdigest()==obs['actualCodeFingerprint']=='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea','independently recomputed four-anchor fingerprint differs')
classpath=read(P/'provenance/actual-17-classpath.json')['files']
with zipfile.ZipFile(P/'provenance/actual-17-classpath-bodies.zip')as z:
 check(len(z.namelist())==len(classpath)==17,'17 full external classpath bodies required')
 for n,(path,pin)in enumerate(classpath.items()):
  body=z.read(str(n)+'/'+Path(path).name);check(len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256'],'captured full classpath body differs')
check(obs['noDriverOrClusterStarted']is True and obs['nativeUdpOrBusinessSessionStarted']is False and obs['cliExecuted']is False and obs['performanceEvidence']is False and receipt['cpuFunctionalOrPerformanceProven']is False and receipt['canonicalBenchmarkPrepStaged']is False,'metadata-only scope differs')
check(preparation()==before_preparation and {str(p.relative_to(E)):file(p)for p in sorted(E.rglob('*'))if p.is_file()}==before_execution,'read inputs changed during review')
result=dict(schemaVersion=1,passed=True,atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='INDEPENDENT_READ_ONLY_ACTUAL_LINUX_READ_WINDOW32_METADATA_REVIEW',sourceCommit=obs['sourceCommit'],actualCodeFingerprint=obs['actualCodeFingerprint'],actualLinuxObservationSha256=OBS,actualRemoteReceiptSha256=sha(E/'remote-receipt.json'),preparationFiles=46,preparationDirectories=9,preparationPayloadBytes=15907739,allPreparationShaSizeModesOwnersEmptyDirectoriesVerified=True,actualExecutionFiles=9,fullActualExecutionInputPins=before_execution,allInputsUnchanged=True,allSixTarMembersAndActualStageInventoriesVerified=True,actualSshStdoutDecodedBodiesEqualAllRawCaptures=True,actualRecordedRemoteSourceAndConfigExact=True,exactPidStartNulArgvExecutableAndJdkBeforeAfterVerified=True,actualMetadataIdentity=identity,normalExit0AndRecordedStrictOwnedPidAbsenceVerified=True,freshLivePidCheckPerformed=False,allSevenClassOriginsAndFourFullJarsVerified=True,independentlyRecomputedFourAnchorFingerprint=obs['actualCodeFingerprint'],all17ClasspathFullBodiesVerified=True,actualLinuxPlansExactlyEqualLocalPage32SelectedPlans=True,actualLocalFourChoiceAndLinuxTwoChoiceSchemasKeptDistinct=True,metadataOnly=True,nativeBusinessQualificationPending=True,performanceEvidence=False,sourcePendingFlagsNotMutated=True,testsGradleJavaSshGitOrNativeAuditExecutedByReviewer=False,scriptSha256=sha(Path(__file__)),limitations=['The recorded exact child was reaped and PID absent in the actual execution receipt; this review does not issue a new SSH /proc check.','The metadata JVM reflects exact config and Plan methods and computes in-memory codec witnesses. It does not start a driver, cluster, business session or benchmark.','Actual Linux metadata exposes two fixed-page32 Plan containers, unlike the four local page/window containers. No extra Linux Plan observations are invented.','Historical source-preparation pending flags remain as generated; actual later execution facts live in the separate execution and review scopes.'])
with(O/'REVIEW.json').open('x')as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({k:result[k]for k in ['passed','actualLinuxObservationSha256','actualCodeFingerprint','actualExecutionFiles','preparationFiles']}))
