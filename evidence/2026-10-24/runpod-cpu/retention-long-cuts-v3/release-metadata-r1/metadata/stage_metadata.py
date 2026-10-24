"""Default local preparation only; explicit frozen config SHA is required for future root-controlled metadata SSH."""
from pathlib import Path
import argparse,base64,datetime,hashlib,importlib.util,json,shutil,shlex,subprocess,sys,tarfile,traceback
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;BASE=OUT.parents[1]
VALIDATION=BASE/'retention-long-cuts-v3-worktree/runtime/long-cuts-local-validation'
REMOTE_ROOT='/opt/vectormatch-cpu/preparation/cpu-long-cuts-release-metadata-r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')

def prepare():
    observation=VALIDATION/'distribution-observation-r1';actual=observation/'actual-distribution-observation.json'
    assert sha(actual)=='185b06b904f0d498f88371b621f4f443b99e03b87790b9c61811f724fb412ec4'
    registration=json.loads((observation/'registration.json').read_text())
    source=observation/'LongCutsDistributionObservation.java'
    assert sha(source)==registration['helperSource']['sha256']
    complete=json.loads((observation/'completion.json').read_text());assert complete['passed'] and complete['noNativeExecution']
    klass=observation/'classes/io/vectormatch/cluster/LongCutsDistributionObservation.class'
    assert complete['helperClasses']==[dict(path=str(klass),bytes=klass.stat().st_size,sha256=sha(klass))]
    inputs=OUT/'inputs';inputs.mkdir(exist_ok=False);lib=inputs/'lib';lib.mkdir();classes=inputs/'classes/io/vectormatch/cluster';classes.mkdir(parents=True)
    for row in registration['jars']:
        src=Path(row['path']);assert src.stat().st_size==row['bytes'] and sha(src)==row['sha256'];shutil.copy2(src,lib/src.name)
    shutil.copy2(source,inputs/source.name);shutil.copy2(klass,classes/klass.name)
    paths={str(p.relative_to(inputs)):p for p in sorted(inputs.rglob('*')) if p.is_file()};assert len(paths)==6
    rows={name:dict(bytes=p.stat().st_size,sha256=sha(p),mode=p.stat().st_mode&0o777) for name,p in paths.items()}
    bundle=OUT/'metadata-inputs.tar.gz'
    with bundle.open('xb') as f,tarfile.open(fileobj=f,mode='w:gz',compresslevel=1) as tar:
        for name,p in paths.items():tar.add(p,arcname=name,recursive=False)
    names=[Path(r['path']).name for r in registration['jars']]
    config=dict(root=REMOTE_ROOT,host='ed6c0673f5cb',java='/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java',javaSha256='9cad3f2620d3ef2ed10b26f922af7e773d54fdaa05f615d6d6df014f3fec4155',releaseSha256='f83f6dcc966043c93cd498ac8e7ee7c310852074970d62c702e4ad2710002898',jarOrder=names,rows=rows,bundleSha256=sha(bundle))
    save(OUT/'metadata-config.json',config)
    save(OUT/'PREPARED_NOT_EXECUTED.json',dict(actualLocalObservationSha256=sha(actual),javaHelperSourceSha256=sha(source),javaHelperClassSha256=sha(klass),remoteRunnerSourceSha256=sha(OUT/'remote_metadata.py'),metadataConfigSha256=sha(OUT/'metadata-config.json'),bundleSha256=sha(bundle),explicitFiles=6,releaseReady=False,SSHExecuted=False,JavaExecutedHere=False,controllerOrBenchmarkStarted=False))
    print(json.dumps(dict(prepared=True,executed=False,metadataConfigSha256=sha(OUT/'metadata-config.json'))))

def execute(expected):
    config_path=OUT/'metadata-config.json';assert expected and sha(config_path)==expected,'Exact root-reviewed immutable metadata config SHA required'
    prepared=json.loads((OUT/'PREPARED_NOT_EXECUTED.json').read_text());assert sha(OUT/'remote_metadata.py')==prepared['remoteRunnerSourceSha256']
    config=json.loads(config_path.read_text());bundle=OUT/'metadata-inputs.tar.gz';assert sha(bundle)==config['bundleSha256']
    assert config['root']==REMOTE_ROOT and len(config['rows'])==6
    remote_path=BASE/'remote.py';spec=importlib.util.spec_from_file_location('long_metadata_remote',remote_path);remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
    program=(OUT/'remote_metadata.py').read_text();command=remote.sshargs()+['python3 -c '+shlex.quote(program)+' '+shlex.quote(base64.b64encode(json.dumps(config).encode()).decode())]
    save(OUT/'REGISTRATION.json',dict(createdAtUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),configSha256=expected,remoteRunnerSourceSha256=sha(OUT/'remote_metadata.py'),stageSourceSha256=sha(Path(__file__)),remoteConnectionHelperSha256=sha(remote_path),inputConfig=config,remoteInlinePythonSource=program,scope='Root-controlled one-shot metadata-only JVM; no driver, cluster, benchmark controller, business RPC or PG'))
    result=subprocess.run(command,input=bundle.read_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
    (OUT/'ssh.stdout').write_bytes(result.stdout);(OUT/'ssh.stderr').write_bytes(result.stderr)
    save(OUT/'ssh-execution.json',dict(exitCode=result.returncode,stdoutSha256=sha(OUT/'ssh.stdout'),stderrSha256=sha(OUT/'ssh.stderr')))
    assert result.returncode==0,'Metadata SSH failed; preserve original attempt; never retry'
    response=json.loads(result.stdout);assert response['passed'] is True
    raw=base64.b64decode(response.pop('observationRawBase64'));assert hashlib.sha256(raw).hexdigest()==response['observationSha256']
    (OUT/'actual-linux-distribution-observation.json').write_bytes(raw)
    for field,name in [('stdoutBase64','java.stdout'),('stderrBase64','java.stderr')]: (OUT/name).write_bytes(base64.b64decode(response.pop(field)))
    save(OUT/'remote-receipt.json',response)
    local=json.loads((VALIDATION/'distribution-observation-r1/actual-distribution-observation.json').read_text());linux=json.loads(raw)
    assert set(local)==set(linux)
    for key in local:
        if key!='actualCodeSources':assert linux[key]==local[key],key
    for a,b in zip(local['actualCodeSources'],linux['actualCodeSources']):
        assert {k:v for k,v in a.items() if k!='path'}=={k:v for k,v in b.items() if k!='path'}
        assert b['path']==REMOTE_ROOT+'/lib/'+Path(a['path']).name
    assert len(local['actualCodeSources'])==len(linux['actualCodeSources'])==5
    assert response['execution']['exitCode']==0 and response['execution']['allInputsUnchanged'] and response['execution']['metadataJvmExited']
    assert response['stagedFiles']==config['rows']
    save(OUT/'SUCCESS.json',dict(passed=True,actualLinuxObservationSha256=sha(OUT/'actual-linux-distribution-observation.json'),remoteReceiptSha256=sha(OUT/'remote-receipt.json'),actualLocalPlansAndClassSourcesEqualExceptPaths=True,metadataJvmExited=True,releaseReady=False,controllerOrBenchmarkStarted=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(allow_abbrev=False);parser.add_argument('--execute',action='store_true');parser.add_argument('--root-reviewed-config-sha256');a=parser.parse_args()
    try:
        if a.execute:execute(a.root_reviewed_config_sha256)
        else:
            assert a.root_reviewed_config_sha256 is None;prepare()
    except BaseException as e:
        save(OUT/'FAILED.json',dict(error=repr(e),traceback=traceback.format_exc(),attemptRetained=True,noAutomaticRetry=True));raise
