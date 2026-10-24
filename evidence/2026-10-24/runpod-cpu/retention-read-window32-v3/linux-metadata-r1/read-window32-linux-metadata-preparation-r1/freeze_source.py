from pathlib import Path
import ast,datetime,difflib,hashlib,json,shutil,struct,tarfile,zipfile
S=Path(__file__).resolve().parent;BASE=S.parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,v):
 with(S/name).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
shutil.copy2(BASE/'event-fetch-linux-metadata-preparation-r1/remote-receipt.json',S/'provenance/earlier-observed-linux-metadata-receipt.json')
changes=[('remote_metadata.py','remote_metadata.py'),('stage_metadata.py','stage_metadata.py'),('test_metadata_guards.py','test_metadata_guards.py'),('ReadWindow32DistributionObservation.java','inputs/ReadWindow32LinuxDistributionObservation.java')]
patch=''
for old,new in changes:
 patch+=''.join(difflib.unified_diff((S/'baseline'/old).read_text().splitlines(True),(S/new).read_text().splitlines(True),fromfile='baseline/'+old,tofile=new))
(S/'SOURCE_DIFF.patch').write_text(patch)
config=json.loads((S/'metadata-config.json').read_text());prepared=json.loads((S/'PREPARED_NOT_EXECUTED.json').read_text());compile=json.loads((S/'helper-compile-r1/EXECUTION.json').read_text())
assert sha(S/'metadata-config.json')==prepared['configSha256'] and sha(S/'metadata-inputs.tar.gz')==config['bundleSha256']==prepared['bundleSha256']
assert sha(S/'remote_metadata.py')==prepared['remoteRunnerSha256'] and sha(S/'stage_metadata.py')==prepared['stageSourceSha256']
assert compile['exitCode']==0 and compile['classMajor']==65 and compile['inputsUnchanged'] and compile['compilerJvmExecuted'] and not compile['metadataJvmExecuted']
assert prepared['compilerJvmExecuted'] and not any(prepared[k]for k in ['metadataJvmExecuted','sshExecuted','linuxExecuted','cloudExecuted','releaseReady'])
seen=set();members=[]
with tarfile.open(S/'metadata-inputs.tar.gz','r:gz')as tar:
 for m in tar:
  assert m.isfile() and m.name not in seen and m.name in config['rows'];seen.add(m.name);row=config['rows'][m.name];body=tar.extractfile(m).read();assert len(body)==row['bytes'] and m.mode==row['mode'] and hashlib.sha256(body).hexdigest()==row['sha256'];assert body==(S/'inputs'/m.name).read_bytes();members.append({'path':m.name,'bytes':m.size,'sha256':row['sha256'],'mode':m.mode})
assert seen==set(config['rows'])and len(seen)==6
for p in [S/'remote_metadata.py',S/'stage_metadata.py',S/'test_metadata_guards.py']:ast.parse(p.read_text())
guards=json.loads((S/'GUARDS_EXECUTION.json').read_text());assert guards['exitCode']==0 and guards['sourceUnchanged'];assert 'Ran 17 tests' in(S/'guards.stderr').read_text()and (S/'guards.stderr').read_text().rstrip().endswith('OK')
# The helper must observe platform facts rather than copying the previous macOS-only flags.
helper=(S/'inputs/ReadWindow32LinuxDistributionObservation.java').read_text();assert 'System.getProperty("os.name")'in helper and 'System.getProperty("os.arch")'in helper and 'getDeclaredMethod("readWindow32Config"'in helper and 'getMethod("commonReadWindow32Plan"'in helper
assert 'localLinuxExecuted'in(S/'baseline/ReadWindow32DistributionObservation.java').read_text() and 'localLinuxExecuted'not in helper
for forbidden in ['new MediaDriver','new RetentionBatchOwnerV3','new RetentionClientV3','runReadWindow32LongCuts(','runEventFetchPageLongCuts(']:assert forbidden not in helper
active=['remote_metadata.py','stage_metadata.py','test_metadata_guards.py','compile_helper.py','run_guards.py','adapt.py','freeze_source.py','inputs/ReadWindow32LinuxDistributionObservation.java','inputs/classes/io/vectormatch/cluster/ReadWindow32LinuxDistributionObservation.class']
save('SOURCE_FROZEN.json',{'schemaVersion':1,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'SOURCE_ONLY_READ_WINDOW32_LINUX_METADATA_PREPARATION','sourceCommit':'605eb43fcafd8fa0a6287304387c93c4d1bbddf6','actualApplicationCodeFingerprint':'d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea','activeSources':{n:{'bytes':(S/n).stat().st_size,'sha256':sha(S/n)}for n in active},'baselineSources':{str(p.relative_to(S)):{'bytes':p.stat().st_size,'sha256':sha(p)}for p in sorted((S/'baseline').glob('*'))},'sourceDiffSha256':sha(S/'SOURCE_DIFF.patch'),'metadataConfigSha256':sha(S/'metadata-config.json'),'bundleSha256':sha(S/'metadata-inputs.tar.gz'),'bundleFullMembersVerified':members,'full17ClasspathCaptureSha256':sha(S/'provenance/actual-17-classpath-bodies.zip'),'helperCompilerExecutionSha256':sha(S/'helper-compile-r1/EXECUTION.json'),'pureGuardExecutionSha256':sha(S/'GUARDS_EXECUTION.json'),'purePythonGuardsPassed':17,'helperClassMajor':65,'compilerJvmExecuted':True,'metadataJvmExecuted':False,'linuxExecuted':False,'cloudExecuted':False,'sshExecuted':False,'actualLinuxMetadataPending':True,'actualLinuxObservationGenerated':False,'benchmarkReleaseReady':False,'nativeFunctionalOrPerformanceProof':False,'actualResultsMustUseFreshSiblingScope':True})
print(json.dumps({'sourceFrozenSha256':sha(S/'SOURCE_FROZEN.json'),'configSha256':sha(S/'metadata-config.json'),'bundleBytes':(S/'metadata-inputs.tar.gz').stat().st_size,'payloadBytes':sum(r['bytes']for r in config['rows'].values()),'pureGuards':17}))
