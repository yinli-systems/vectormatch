"""One six-file metadata stage and one SSH attempt; no cluster/application launch."""
from pathlib import Path
import argparse, base64, datetime, hashlib, importlib.util, json, shlex, shutil, subprocess, tarfile

OUT=Path(__file__).resolve().parent
BASE=OUT.parent
REMOTE_ROOT='/opt/vectormatch-cpu/preparation/cpu-event-fetch-release-metadata-r1'
HELPER='EventFetchDistributionObservation'
COMMIT='d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text())
def save(p,value):
    with p.open('x') as f: json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def require(ok,message):
    if not ok: raise RuntimeError(message)

def compare_observations(local,linux):
    require(set(local)==set(linux),'Observation keys differ')
    for key in local:
        if key not in ['actualCodeSources','distributionJars']:
            require(local[key]==linux[key],'Metadata field differs: '+key)
    require(len(local['actualCodeSources'])==len(linux['actualCodeSources'])==7,'Seven actual class origins required')
    for a,b in zip(local['actualCodeSources'],linux['actualCodeSources']):
        require({k:v for k,v in a.items() if k!='path'}=={k:v for k,v in b.items() if k!='path'},'Runtime origin body differs')
        require(b['path']==REMOTE_ROOT+'/lib/'+Path(a['path']).name,'Runtime origin relocation differs')
    require(set(local['distributionJars'])==set(linux['distributionJars']) and len(local['distributionJars'])==4,'Four distribution JARs required')
    for name,a in local['distributionJars'].items():
        b=linux['distributionJars'][name]
        require({k:v for k,v in a.items() if k!='path'}=={k:v for k,v in b.items() if k!='path'},'Distribution JAR body differs')
        require(Path(a['path']).name==name and b['path']==REMOTE_ROOT+'/lib/'+name,'Distribution JAR relocation differs')

def prepare(local,expected):
    actual=local/'actual-distribution-observation.json'
    require(sha(actual)==expected,'Root-reviewed observation SHA required')
    observation=load(actual);closed=load(local/'CLOSED.json');compiled=load(local/'COMPILED_HELPER.json')
    require(sha(local/'CLOSED.json')=='400a4a0df83d6c9eac98f3b696603409d55a05f5b5631b98ff0296788909dd2e','Reviewed local closure required')
    require(sha(local/'MANIFEST.json')==closed['manifestSha256'] and closed['observationSha256']==expected,'Local closure binding')
    require(closed['passed'] and closed['metadataJvmExited'] and closed['javaExitCode']==closed['javacExitCode']==0,'Successful closed metadata attempt required')
    require(closed['sourceCommit']==observation['sourceCommit']==COMMIT and observation['noDriverOrClusterStarted'] is True,'Source/scope binding')
    require(len(observation['actualCodeSources'])==7 and len(observation['distributionJars'])==4,'Actual origin/JAR count')
    root_review=BASE/'event-fetch-metadata-root-review-r1/ROOT_REVIEW.json'
    review=load(root_review)
    require(review['passed'] and review['closedSha256']==sha(local/'CLOSED.json') and review['observationSha256']==expected,'Independent local root review required')
    inputs=OUT/'inputs';inputs.mkdir();(inputs/'lib').mkdir()
    classes=inputs/'classes/io/vectormatch/cluster';classes.mkdir(parents=True)
    origins={}
    for name,row in observation['distributionJars'].items():
        source=Path(row['path'])
        require(source.name==name and source.is_file() and not source.is_symlink() and source.stat().st_size==row['bytes'] and sha(source)==row['sha256'],'Installed JAR identity '+name)
        origins[name]=source;shutil.copy2(source,inputs/'lib'/name)
    for row in observation['actualCodeSources']:
        require({k:v for k,v in row.items() if k!='class'}==observation['distributionJars'][Path(row['path']).name],'Class origin not bound to full JAR body')
    source=local/(HELPER+'.java');klass=local/'classes/io/vectormatch/cluster'/(HELPER+'.class')
    require(not source.is_symlink() and not klass.is_symlink() and str(klass)==compiled['classFile'],'Helper paths')
    require(source.stat().st_size==compiled['source']['bytes'] and sha(source)==compiled['source']['sha256']==closed['helperSourceSha256'],'Helper source')
    require(klass.stat().st_size==compiled['class']['bytes'] and sha(klass)==compiled['class']['sha256']==closed['helperClassSha256'],'Precompiled helper class')
    shutil.copy2(source,inputs/source.name);shutil.copy2(klass,classes/klass.name)
    paths={p.relative_to(inputs).as_posix():p for p in sorted(inputs.rglob('*')) if p.is_file()}
    require(len(paths)==6,'Exactly six payload files')
    rows={n:dict(bytes=p.stat().st_size,sha256=sha(p),mode=p.stat().st_mode&0o777) for n,p in paths.items()}
    bundle=OUT/'metadata-inputs.tar.gz'
    with bundle.open('xb') as f,tarfile.open(fileobj=f,mode='w:gz',compresslevel=1) as tar:
        for name,p in paths.items():tar.add(p,arcname=name,recursive=False)
    config=dict(root=REMOTE_ROOT,host='ed6c0673f5cb',java='/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java',
        javaSha256='9cad3f2620d3ef2ed10b26f922af7e773d54fdaa05f615d6d6df014f3fec4155',
        releaseSha256='f83f6dcc966043c93cd498ac8e7ee7c310852074970d62c702e4ad2710002898',
        jarOrder=sorted(origins),rows=rows,bundleSha256=sha(bundle))
    save(OUT/'metadata-config.json',config)
    save(OUT/'PREPARED_NOT_EXECUTED.json',dict(localObservationPath=str(actual),localObservationSha256=expected,
        localClosedSha256=sha(local/'CLOSED.json'),localRootReviewSha256=sha(root_review),sourceCommit=COMMIT,
        helperSourceSha256=sha(source),helperClassSha256=sha(klass),remoteRunnerSha256=sha(OUT/'remote_metadata.py'),
        stageSourceSha256=sha(Path(__file__)),configSha256=sha(OUT/'metadata-config.json'),bundleSha256=sha(bundle),
        files=6,sshExecuted=False,javaExecutedHere=False,releaseReady=False))
    print(json.dumps(dict(prepared=True,configSha256=sha(OUT/'metadata-config.json'))))

def execute(expected):
    config_path=OUT/'metadata-config.json';require(sha(config_path)==expected,'Reviewed config SHA')
    prepared=load(OUT/'PREPARED_NOT_EXECUTED.json')
    require(sha(OUT/'remote_metadata.py')==prepared['remoteRunnerSha256'] and sha(Path(__file__))==prepared['stageSourceSha256'],'Frozen stage/runner source')
    require(not (OUT/'REGISTRATION.json').exists(),'No resubmission')
    config=load(config_path);bundle=OUT/'metadata-inputs.tar.gz'
    require(sha(bundle)==config['bundleSha256'] and config['root']==REMOTE_ROOT and len(config['rows'])==6,'Frozen bundle/config')
    remote_path=BASE/'remote.py';require(sha(remote_path)=='0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73','Canonical SSH helper')
    spec=importlib.util.spec_from_file_location('event_fetch_metadata_remote',remote_path);remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
    command=remote.sshargs()+['python3 -B -c '+shlex.quote((OUT/'remote_metadata.py').read_text())+' '+shlex.quote(base64.b64encode(json.dumps(config).encode()).decode())]
    save(OUT/'REGISTRATION.json',dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),configSha256=expected,
        remoteRunnerSha256=sha(OUT/'remote_metadata.py'),remoteHelperSha256=sha(remote_path),scope='One metadata-only JVM; no driver, cluster, business RPC, database or new resource',command=command))
    try:
        result=subprocess.run(command,input=bundle.read_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
        stdout,stderr,status=result.stdout,result.stderr,result.returncode;timed_out=False
    except subprocess.TimeoutExpired as error:
        stdout,stderr,status=error.stdout or b'',error.stderr or b'',None;timed_out=True
    with (OUT/'ssh.stdout').open('xb') as f:f.write(stdout)
    with (OUT/'ssh.stderr').open('xb') as f:f.write(stderr)
    save(OUT/'ssh-execution.json',dict(exitCode=status,timedOut=timed_out,stdoutSha256=sha(OUT/'ssh.stdout'),stderrSha256=sha(OUT/'ssh.stderr'),noAutomaticRetry=True))
    require(status==0 and not timed_out,'Preserve failed SSH attempt; do not retry')
    response=json.loads(stdout);require(response['passed'] is True,'Remote metadata failed')
    raw=base64.b64decode(response.pop('observationRawBase64'),validate=True)
    require(hashlib.sha256(raw).hexdigest()==response['observationSha256'],'Observation SHA differs')
    with (OUT/'actual-linux-distribution-observation.json').open('xb') as f:f.write(raw)
    for field,name in [('stdoutBase64','java.stdout'),('stderrBase64','java.stderr')]:
        with (OUT/name).open('xb') as f:f.write(base64.b64decode(response.pop(field),validate=True))
    save(OUT/'remote-receipt.json',response);execution=response['execution']
    require(execution['exitCode']==0 and execution['metadataJvmExited'] and execution['strictOwnedPidAbsentAfterWait'] and execution['allInputsUnchanged'],'Normal reaped exit and unchanged inputs required')
    require(execution['processIdentityObservationGap'] is False and execution['actualProcessIdentity']['pid']==execution['ownedParentPid'],'Actual /proc argv/start/executable identity required')
    local_path=Path(prepared['localObservationPath']);require(sha(local_path)==prepared['localObservationSha256'],'Local reference unchanged')
    compare_observations(load(local_path),json.loads(raw))
    require(response['stagedFiles']==config['rows'],'Staged file bodies differ')
    save(OUT/'SUCCESS.json',dict(passed=True,linuxObservationSha256=sha(OUT/'actual-linux-distribution-observation.json'),receiptSha256=sha(OUT/'remote-receipt.json'),
        actualLocalAndLinuxPlansSelectionAndSourcesEqualExceptPaths=True,metadataJvmExited=True,strictOwnedPidAbsent=True,processIdentityObserved=True,releaseReady=False,benchmarkExecuted=False))
    print(json.dumps(dict(passed=True,observationSha256=sha(OUT/'actual-linux-distribution-observation.json'))))

if __name__=='__main__':
    p=argparse.ArgumentParser(allow_abbrev=False);mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-only',action='store_true');mode.add_argument('--execute',action='store_true')
    p.add_argument('--local-observation-directory',type=Path);p.add_argument('--local-observation-sha256');p.add_argument('--root-reviewed-config-sha256')
    a=p.parse_args()
    if a.prepare_only:
        require(a.local_observation_directory and a.local_observation_sha256,'Local observation arguments required')
        prepare(a.local_observation_directory.resolve(),a.local_observation_sha256)
    else:
        require(a.root_reviewed_config_sha256,'Reviewed config required');execute(a.root_reviewed_config_sha256)
