from pathlib import Path
S=Path(__file__).resolve().parent
remote=(S/'baseline/remote_metadata.py').read_text().replace('cpu-event-fetch-release-metadata-r1','cpu-read-window32-release-metadata-r1').replace('cpu-event-fetch-cloud-abab-r1','cpu-read-window32-cloud-abab-r1').replace('EventFetchDistributionObservation','ReadWindow32LinuxDistributionObservation')
remote=remote.replace("if current['argv']==expected:observed=current;break","if current['argv']==expected:\n                        require(current['actualExecutable']==str(java.resolve()),'Metadata actual executable differs from pinned JDK');observed=current;break")
(S/'remote_metadata.py').write_text(remote)
stage=(S/'baseline/stage_metadata.py').read_text().replace('cpu-event-fetch-release-metadata-r1','cpu-read-window32-release-metadata-r1').replace('EventFetchDistributionObservation','ReadWindow32LinuxDistributionObservation').replace('d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8','605eb43fcafd8fa0a6287304387c93c4d1bbddf6').replace("'event_fetch_metadata_remote'","'read_window32_metadata_remote'")
start=stage.index('def compare_observations(');end=stage.index('\ndef execute(',start)
functions='''def compare_observations(local,linux):
    expected_keys={'schemaVersion','sourceCommit','sourceBaseCommit','actualCodeFingerprint','profileSha256','actualCodeSources','distributionJars','plans','selectedWindowPlanDifferenceKeys','fixedEventFetchCount','reflectedConfigAndPlanMethods','actualMetadataPlatform','noDriverOrClusterStarted','nativeUdpOrBusinessSessionStarted','cliExecuted','performanceEvidence','planProbeUsesTemporaryInMemoryReferenceEngineForCodecDerivation','scope'}
    require(set(linux)==expected_keys,'Exact Linux observation schema required')
    require(linux['schemaVersion']==2 and linux['sourceCommit']==local['sourceCommit']==COMMIT,'Source/schema binding differs')
    for key in ['sourceBaseCommit','actualCodeFingerprint','profileSha256']:
        require(local[key]==linux[key],'Metadata field differs: '+key)
    require(linux['actualCodeFingerprint']=='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea','Pinned four-JAR fingerprint differs')
    require(linux['fixedEventFetchCount']==32,'Comparison must keep event page32 fixed')
    require(linux['reflectedConfigAndPlanMethods']==['RetentionCapacityAeronPilotV3.readWindow32Config(int,int)','RetentionCapacityPlanV3.commonReadWindow32Plan(int,int,Profile,int,int,long,long)'],'Actual reflected methods differ')
    require(set(linux['plans'])=={'8','32'},'Both fixed-page32 windows required')
    for window in ['8','32']:
        require(linux['plans'][window]==local['plans']['page32-window'+window],'Actual selected window Plan/config differs: '+window)
    require(linux['selectedWindowPlanDifferenceKeys']=={'fixedPage32':['requestedReadWindow']},'Only requested window may differ')
    platform=linux['actualMetadataPlatform']
    require(set(platform)=={'osName','osArch','javaRuntimeVersion','javaVendor'} and platform['osName']=='Linux' and platform['osArch']=='amd64' and platform['javaRuntimeVersion'].startswith('21.0.13+9') and isinstance(platform['javaVendor'],str) and 0<len(platform['javaVendor'])<=128,'Observed platform/JDK is not pinned Linux x86_64 JDK21.0.13+9')
    require(linux['noDriverOrClusterStarted'] is True and linux['nativeUdpOrBusinessSessionStarted'] is False and linux['cliExecuted'] is False and linux['performanceEvidence'] is False and linux['planProbeUsesTemporaryInMemoryReferenceEngineForCodecDerivation'] is True,'Metadata-only scope differs')
    require(linux['scope']=='Installed-JAR metadata/class origins and prospective in-memory codec/Plan calculations only; no native pilot, runtime-agent consumption or performance proof','Metadata scope differs')
    require(len(local['actualCodeSources'])==len(linux['actualCodeSources'])==7,'Seven actual class origins required')
    for a,b in zip(local['actualCodeSources'],linux['actualCodeSources']):
        require({k:v for k,v in a.items() if k!='path'}=={k:v for k,v in b.items() if k!='path'},'Runtime origin body differs')
        require(b['path']==REMOTE_ROOT+'/lib/'+Path(a['path']).name,'Runtime origin relocation differs')
    require(set(local['distributionJars'])==set(linux['distributionJars']) and len(local['distributionJars'])==4,'Four distribution JARs required')
    for name,a in local['distributionJars'].items():
        b=linux['distributionJars'][name]
        require({k:v for k,v in a.items() if k!='path'}=={k:v for k,v in b.items() if k!='path'},'Distribution JAR body differs')
        require(Path(a['path']).name==name and b['path']==REMOTE_ROOT+'/lib/'+name,'Distribution JAR relocation differs')

def validate_preparation_inputs(local,expected):
    actual=local/'metadata-r1/observation.json'
    require(sha(actual)==expected=='212a58a80575f82cb165e09c87040709d8c471d86ca8a0fa30e80f5ac351fa7c','Root-reviewed observation SHA required')
    require(sha(local/'CLOSED.json')=='7edce2f9bb8e23af8ec7ff512c7b9134669e291f23b39e8a61153589cb985b2b','Reviewed local closure required')
    closed=load(local/'CLOSED.json');observation=load(actual)
    require(sha(local/'INVENTORY.json')==closed['inventorySha256'] and sha(local/'LOCAL_ARTIFACT_CLOSURE.json')==closed['localArtifactClosureSha256'],'Local closure binding')
    require(closed['sourceCommit']==observation['sourceCommit']==COMMIT and observation['noDriverOrClusterStarted'] is True,'Source/scope binding')
    require(len(observation['actualCodeSources'])==7 and len(observation['distributionJars'])==4,'Actual origin/JAR count')
    root_review=OUT/'provenance/root-source-review.json';review=load(root_review)
    require(review['passed'] and review['sourceCommit']==COMMIT and review['localArtifactClosureSha256']==sha(local/'LOCAL_ARTIFACT_CLOSURE.json') and review['actualDistinctTests']==58 and review['actualXmlReports']==10 and review['unitFinalFailedErrorsSkipped']==0,'Independent reviewed candidate required')
    for row in observation['actualCodeSources']:
        require({k:v for k,v in row.items() if k!='class'}==observation['distributionJars'][Path(row['path']).name],'Class origin not bound to full JAR body')
    for name,row in observation['distributionJars'].items():
        source=Path(row['path']);target=OUT/'inputs/lib'/name
        require(source.name==name and source.is_file() and not source.is_symlink() and source.stat().st_size==row['bytes'] and sha(source)==row['sha256'],'Installed JAR identity '+name)
        require(target.is_file() and not target.is_symlink() and target.read_bytes()==source.read_bytes(),'Copied input JAR differs '+name)
    compiled=load(OUT/'helper-compile-r1/EXECUTION.json');registration=load(OUT/'helper-compile-r1/REGISTRATION.json')
    require(compiled['exitCode']==0 and compiled['inputsUnchanged'] and compiled['classMajor']==65 and compiled['compilerJvmExecuted'] and not compiled['metadataJvmExecuted'] and not compiled['applicationTestsExecuted'] and not compiled['linuxExecuted'] and not compiled['cloudExecuted'],'Only successful javac preparation is admissible')
    source=OUT/'inputs'/(HELPER+'.java');klass=OUT/'inputs/classes/io/vectormatch/cluster'/(HELPER+'.class')
    for p,row in [(source,compiled['source']),(klass,compiled['class'])]:
        require(not p.is_symlink() and p.is_file() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'Compiled helper source/class differs')
    require(compiled['classFile']==str(klass),'Compiled helper path differs')
    for name,row in registration['inputs'].items():
        p=Path(name);require(p.is_file() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'Compiler input changed')
    capture=load(OUT/'provenance/actual-17-classpath.json');body=OUT/'provenance/actual-17-classpath-bodies.zip'
    require(len(capture['files'])==17 and sha(body)==capture['externalTestClasspathBodiesZipSha256'],'Full17 classpath capture differs')
    import zipfile
    with zipfile.ZipFile(body) as z:
        require(len(z.namelist())==17,'Full17 classpath body count differs')
        for i,(name,row) in enumerate(capture['files'].items()):
            raw=z.read(str(i)+'/'+Path(name).name);require(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'Captured classpath body differs')
    return actual,observation,root_review,source,klass

def prepare(local,expected):
    actual,observation,root_review,source,klass=validate_preparation_inputs(local,expected)
    inputs=OUT/'inputs';paths={p.relative_to(inputs).as_posix():p for p in sorted(inputs.rglob('*')) if p.is_file()}
    require(len(paths)==6,'Exactly six payload files')
    rows={n:dict(bytes=p.stat().st_size,sha256=sha(p),mode=p.stat().st_mode&0o777) for n,p in paths.items()}
    bundle=OUT/'metadata-inputs.tar.gz'
    with bundle.open('xb') as f,tarfile.open(fileobj=f,mode='w:gz',compresslevel=1) as tar:
        for name,p in paths.items():tar.add(p,arcname=name,recursive=False)
    config=dict(root=REMOTE_ROOT,host='ed6c0673f5cb',java='/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java',
        javaSha256='9cad3f2620d3ef2ed10b26f922af7e773d54fdaa05f615d6d6df014f3fec4155',
        releaseSha256='f83f6dcc966043c93cd498ac8e7ee7c310852074970d62c702e4ad2710002898',
        jarOrder=sorted(observation['distributionJars']),rows=rows,bundleSha256=sha(bundle))
    save(OUT/'metadata-config.json',config)
    save(OUT/'PREPARED_NOT_EXECUTED.json',dict(localObservationPath=str(actual),localObservationSha256=expected,
        localClosedSha256=sha(local/'CLOSED.json'),localRootReviewSha256=sha(root_review),sourceCommit=COMMIT,
        helperSourceSha256=sha(source),helperClassSha256=sha(klass),remoteRunnerSha256=sha(OUT/'remote_metadata.py'),
        stageSourceSha256=sha(Path(__file__)),configSha256=sha(OUT/'metadata-config.json'),bundleSha256=sha(bundle),
        full17LocalClasspathCaptureSha256=sha(OUT/'provenance/actual-17-classpath-bodies.zip'),
        files=6,compilerJvmExecuted=True,metadataJvmExecuted=False,sshExecuted=False,linuxExecuted=False,cloudExecuted=False,releaseReady=False))
    print(json.dumps(dict(prepared=True,configSha256=sha(OUT/'metadata-config.json'))))
'''
stage=stage[:start]+functions+stage[end:]
stage=stage.replace('def execute(expected):','def execute(expected,execution_out):')
stage=stage.replace("    require(not (OUT/'REGISTRATION.json').exists(),'No resubmission')","    require(execution_out is not None and not execution_out.exists() and execution_out.parent.resolve()==OUT.parent.resolve(),'Fresh sibling execution scope required; no resubmission')")
# Keep frozen preparation immutable; all actual results land exclusively in the selected fresh sibling.
start=stage.index('def execute(');end=stage.index("\nif __name__",start);block=stage[start:end]
block=block.replace("    save(OUT/'REGISTRATION.json'", "    execution_out.mkdir(mode=0o700)\n    save(execution_out/'REGISTRATION.json'")
for name in ['ssh.stdout','ssh.stderr','ssh-execution.json','actual-linux-distribution-observation.json','java.stdout','java.stderr','remote-receipt.json','SUCCESS.json']:
 block=block.replace("OUT/'"+name+"'","execution_out/'"+name+"'")
block=block.replace('(OUT/name).open','(execution_out/name).open')
block=block.replace('actualLocalAndLinuxPlansSelectionAndSourcesEqualExceptPaths=True','actualFixedPage32PlansSourcesAndPinnedFourJarsMatchLocalReference=True')
block=block.replace('releaseReady=False,benchmarkExecuted=False','releaseReady=False,benchmarkExecuted=False,metadataJvmExecuted=True,linuxMetadataExecuted=True,performanceEvidence=False')
stage=stage[:start]+block+stage[end:]
stage=stage.replace("p.add_argument('--root-reviewed-config-sha256')","p.add_argument('--root-reviewed-config-sha256');p.add_argument('--execution-output',type=Path)")
stage=stage.replace('execute(a.root_reviewed_config_sha256)','execute(a.root_reviewed_config_sha256,a.execution_output.resolve() if a.execution_output else None)')
(S/'stage_metadata.py').write_text(stage)
