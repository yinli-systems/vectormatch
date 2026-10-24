"""One fresh metadata-only JVM, no benchmark/controller invocation."""
import base64,datetime,hashlib,json,os,pathlib,platform,shutil,socket,stat,subprocess,sys,tarfile,time,traceback

def require(ok,message):
    if not ok:raise RuntimeError(message)
def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def save(p,value):
    with p.open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def member_ok(member,rows,seen):
    name=member.name;p=pathlib.PurePosixPath(name)
    require(member.isfile() and name in rows and name not in seen and str(p)==name and not p.is_absolute() and '..' not in p.parts,'Tar member not in exclusive regular-file allowlist')
    row=rows[name];require(member.size==row['bytes'] and 0<member.size<8*1024**2 and member.mode==row['mode'],'Tar size/mode differs')
def identity(pid):
    p=pathlib.Path('/proc')/str(pid);before=(p/'stat').read_text();fields=before[before.rfind(')')+2:].split();ticks=int(fields[19]);raw=(p/'cmdline').read_bytes();after=(p/'stat').read_text();require(int(after[after.rfind(')')+2:].split()[19])==ticks,'PID identity changed during capture')
    return {'pid':pid,'startTicks':ticks,'commandSha256':hashlib.sha256(raw).hexdigest(),'argv':raw.rstrip(b'\0').split(b'\0'),'actualExecutable':os.readlink(str(p/'exe'))}
def encoded_identity(row):return {k:v for k,v in row.items() if k!='argv'}
def observe(c):
    root=pathlib.Path(c['root']);require(str(root)=='/opt/vectormatch-cpu/preparation/cpu-read-window32-release-metadata-r1','Wrong metadata root')
    require(platform.system()=='Linux' and platform.machine()=='x86_64' and os.geteuid()==0,'Exact Linux/x86_64/root required')
    for parent in root.parents:require(parent.is_dir() and not parent.is_symlink(),'Unsafe metadata parent')
    require(socket.gethostname()==c['host']=='ed6c0673f5cb','Wrong CPU host');require(not root.exists() and not root.is_symlink(),'Metadata root already exists; preserve, do not resume')
    require(not pathlib.Path('/opt/vectormatch-cpu/preparation/cpu-read-window32-cloud-abab-r1').exists(),'Canonical benchmark preparation unexpectedly exists')
    free=shutil.disk_usage(root.parent).free;require(free>1024**3+sum(r['bytes'] for r in c['rows'].values())+64*1024**2,'Metadata free-space floor')
    java=pathlib.Path(c['java']);release=java.parent.parent/'release'
    require(sha(java)==c['javaSha256'] and sha(release)==c['releaseSha256'],'Canonical JDK identity differs before upload')
    require('JAVA_VERSION="21.0.13"' in release.read_text() and 'OS_NAME="Linux"' in release.read_text(),'Pinned Linux JDK21.0.13 required')
    os.umask(0o077);root.mkdir(mode=0o700);results=root/'results';results.mkdir(mode=0o700)
    try:
        bundle=root/'input-bundle.tar.gz';count=0
        with bundle.open('xb') as f:
            while True:
                b=sys.stdin.buffer.read(1024*1024)
                if not b:break
                count+=len(b);require(count<=16*1024**2,'Metadata upload cap');f.write(b)
        require(sha(bundle)==c['bundleSha256'],'Upload bundle SHA differs');seen=set()
        with tarfile.open(str(bundle),'r:gz') as tar:
            for member in tar:
                member_ok(member,c['rows'],seen);row=c['rows'][member.name];raw=tar.extractfile(member).read();require(hashlib.sha256(raw).hexdigest()==row['sha256'],'Uploaded input SHA differs')
                p=root/member.name;p.parent.mkdir(parents=True,exist_ok=True)
                with p.open('xb') as f:f.write(raw)
                p.chmod(row['mode']);seen.add(member.name)
        require(seen==set(c['rows']),'Missing metadata inputs')
        before={}
        for name,row in c['rows'].items():
            p=root/name;before[name]={'bytes':p.stat().st_size,'mode':stat.S_IMODE(p.stat().st_mode),'sha256':sha(p)};require(before[name]==row,'Extracted input inventory differs')
        command=[str(java),'-Xmx128m','--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','-cp',str(root/'classes')+':'+':'.join(str(root/'lib'/name) for name in c['jarOrder']),'io.vectormatch.cluster.ReadWindow32LinuxDistributionObservation',str(results/'actual-distribution-observation.json')]
        env=os.environ.copy();removed=[]
        for name in ['JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS']:
            if name in env:removed.append(name);env.pop(name)
        registration={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':command,'javaExecutable':str(java),'actualJavaExecutable':str(java.resolve()),'javaExecutableSha256':sha(java),'jdkReleaseSha256':sha(release),'inputInventory':before,'hostname':socket.gethostname(),'freeBytesBefore':free,'removedJavaOptionEnvironmentNames':removed,'scope':'Metadata-only in-memory codec/plan calculation; no MediaDriver, socket, cluster, SQL or business RPC starts'};save(results/'registration.json',registration)
        start=time.monotonic();child=None;observed=None;timeout=False
        with (results/'java.stdout').open('xb') as out,(results/'java.stderr').open('xb') as err:
            child=subprocess.Popen(command,stdout=out,stderr=err,env=env)
            expected=[os.fsencode(x) for x in command]
            for unused in range(100):
                try:
                    current=identity(child.pid)
                    if current['argv']==expected:
                        require(current['actualExecutable']==str(java.resolve()),'Metadata actual executable differs from pinned JDK');observed=current;break
                except FileNotFoundError:pass
                if child.poll() is not None:break
                time.sleep(.005)
            try:status=child.wait(timeout=40)
            except subprocess.TimeoutExpired:
                timeout=True;current=identity(child.pid);require(observed is not None and current==observed,'Cannot prove metadata PID identity for cleanup; preserve, no broad signal')
                child.terminate()
                try:status=child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    require(identity(child.pid)==observed,'Metadata identity changed after TERM');raise RuntimeError('Owned metadata child did not exit after SIGTERM; preserve identity and files, no force kill or retry')
        after={name:{'bytes':(root/name).stat().st_size,'mode':stat.S_IMODE((root/name).stat().st_mode),'sha256':sha(root/name)} for name in c['rows']}
        require((results/'java.stdout').stat().st_size<=4*1024**2 and (results/'java.stderr').stat().st_size<=4*1024**2,'Metadata output cap; partial files retained')
        execution={'exitCode':status,'elapsedSeconds':time.monotonic()-start,'timedOut':timeout,'ownedParentPid':child.pid,'actualProcessIdentity':encoded_identity(observed) if observed else None,'processIdentityObservationGap':observed is None,'allInputsUnchanged':after==before,'javaExecutableSha256After':sha(java),'jdkReleaseSha256After':sha(release),'stdoutSha256':sha(results/'java.stdout'),'stderrSha256':sha(results/'java.stderr'),'metadataJvmExited':True,'strictOwnedPidAbsentAfterWait':not pathlib.Path('/proc',str(child.pid)).exists(),'completedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat()};save(results/'execution.json',execution)
        require(status==0 and not timeout and observed is not None and not pathlib.Path('/proc',str(child.pid)).exists() and after==before and sha(java)==c['javaSha256'] and sha(release)==c['releaseSha256'],'Metadata execution or input/JDK identity failed')
        observed_path=results/'actual-distribution-observation.json';require(observed_path.stat().st_size<1024**2,'Observation output bound');data=json.loads(observed_path.read_text())
        require(data['noDriverOrClusterStarted'] is True,'Unexpected metadata helper scope')
        payload={'passed':True,'registration':registration,'execution':execution,'observationSha256':sha(observed_path),'observationRawBase64':base64.b64encode(observed_path.read_bytes()).decode(),'stdoutBase64':base64.b64encode((results/'java.stdout').read_bytes()).decode(),'stderrBase64':base64.b64encode((results/'java.stderr').read_bytes()).decode(),'stagedFiles':after,'root':str(root),'canonicalBenchmarkPrepStaged':False,'cpuFunctionalOrPerformanceProven':False}
        save(results/'SUCCESS.json',{k:v for k,v in payload.items() if not k.endswith('Base64')});print(json.dumps(payload))
    except BaseException as error:
        failure={'passed':False,'error':repr(error),'traceback':traceback.format_exc(),'partialDirectoryRetained':True,'noAutomaticRetry':True,'root':str(root)}
        if not (results/'FAILED.json').exists():save(results/'FAILED.json',failure)
        print(json.dumps(failure));raise
if __name__=='__main__':observe(json.loads(base64.b64decode(sys.argv[1])))
