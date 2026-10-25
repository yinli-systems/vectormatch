"""One explicit arm of fixed read32/128 ABAB. Default readonly. Each next arm requires actual raw/private gate."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,platform,shutil,socket,stat,sys
HERE=Path(__file__).resolve().parent
PREP=Path('/opt/vectormatch-cpu/experiments/read-window128-abab-r1')
ORDER=(32,128,32,128)
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(v,msg):
    if not v:raise RuntimeError(msg)
def main():
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--freeze-sha256',required=True);p.add_argument('--arm',type=int,choices=(1,2,3,4),required=True);p.add_argument('--prior-gate-sha256');p.add_argument('--start-new',action='store_true');a=p.parse_args();require(HERE==PREP,'Exact campaign namespace required')
    require(digest(HERE/'FROZEN.json')==a.freeze_sha256,'Exact root source freeze required');pins=json.loads((HERE/'FROZEN.json').read_text())
    for n,row in pins['files'].items():
        q=HERE/n;require(q.is_file()and not q.is_symlink()and q.stat().st_size==row['bytes']and digest(q)==row['sha256']and stat.S_IMODE(q.stat().st_mode)==row['mode'],'Staged source/package differs: '+n)
    spec=importlib.util.spec_from_file_location('cpu_read_window32_abab',HERE/'cpu_read_window32_abab.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);require(digest(m.__file__)=='1d15cd2c53e0914c6d1d203cc486c563be3d2cfdaa1fa159ffaa8ffd231b14c4','Original lifecycle source differs')
    m.JOB=PREP/('arm-'+str(a.arm));m.PAIR=m.JOB/'idle-arm';m.ARM=a.arm;m.READ_WINDOW_ORDER=ORDER;m.OWNER_PARK_ORDER=(1000000,)*4;m.WINDOWS=[ORDER[a.arm-1]]
    exec(compile((HERE/'capacity_validators.py').read_text(),str(HERE/'capacity_validators.py'),'exec'),m.__dict__)
    path=HERE/'release.json';release=json.loads(path.read_text());m.FROZEN_RELEASE_SHA=digest(path);m.SOURCE_COMMIT=release['sourceCommit'];m.CODE_FINGERPRINT=release['codeFingerprint'];base=m.load_base()
    def parent_argv(r):return [r['java'],'-Dvectormatch.retention.idleMaxParkNs=100000','-Dvectormatch.retention.ownerPollMaxParkNs=1000000']+r['parentJvmArguments']+['-cp',':'.join(r['classPath']),m.MAIN,str(m.PAIR),'read-window128-capacity',str(ORDER[a.arm-1]),'42000']
    def fresh_lineage(b,registration):
        for n in range(1,a.arm):
            previous=json.loads((PREP/('arm-'+str(n))/'idle-arm/registration.json').read_text());require(previous['lineage']!=registration['lineage']and previous['codeSha256']==registration['codeSha256'],'Distinct fresh lineages under same new artifact required')
        return True
    def preflight(b,r):
        require(platform.system()=='Linux'and platform.machine()=='x86_64'and socket.gethostname()=='33ace3d92505'and os.geteuid()==0,'Exact current CPU/Linux/root required');b.no_links(PREP);require(not m.JOB.exists()and not m.PAIR.exists(),'Fresh one attempt only; no resume/rerun')
        for n,row in pins['files'].items():
            q=HERE/n;b.no_links(q);require(q.stat().st_size==row['bytes']and digest(q)==row['sha256']and stat.S_IMODE(q.stat().st_mode)==row['mode'],'Staged source differs')
        require(digest(r['java'])==r['javaExecutableSha256']and digest(Path(r['java']).parents[1]/'release')==r['jdkReleaseSha256'],'Pinned JDK differs')
        for n,row in r['artifacts'].items():
            q=Path(n);b.no_links(q);require(q.stat().st_size==row['bytes']and digest(q)==row['sha256'],'New loaded JAR differs')
        observation=json.loads((HERE/'linux-metadata.json').read_text());review=json.loads((HERE/'linux-metadata-root-review.json').read_text());require(review['passed']and review['actualLinuxPlansMatchLocal']and review['allSevenActualLoadedOriginsMatchStagedJars']and review['strictOwnedPidAbsentAfterWait']and review['observationSha256']==digest(HERE/'linux-metadata.json'),'Actual Linux metadata/review differs');require(observation['actualCodeFingerprint']==r['codeFingerprint']and observation['profileSha256']==r['profileFingerprint']and all(observation['plans'][k]['plan']==r['derivedPlans'][k]for k in['32','128']),'Actual Linux source/plans differ')
        plans=[dict(r['derivedPlans'][k])for k in['32','128']]
        for v in plans:require(v.pop('requestedReadWindow')in(32,128)and v['maxReadOnlyInFlight']==128 and v['arrivals']==20000 and v['admissionRejections']==[],'Exact finite common128 codec admission required')
        require(plans[0]==plans[1]and r['readWindowOrder']==list(ORDER)and r['preloadWarmupMillis']==5000 and r['instrumentationEnabled']is False,'Common budgets/order/warmup/no-instrumentation differ')
        prior=None
        if a.arm==1:require(a.prior_gate_sha256 is None,'First arm cannot substitute old qualification')
        else:
            gate_path=HERE/('arm-'+str(a.arm-1)+'-gate.json');b.no_links(gate_path);require(a.prior_gate_sha256 is not None and digest(gate_path)==a.prior_gate_sha256,'Exact prior root/raw/private gate required');g=json.loads(gate_path.read_text());require(g['passed']and g['scope']=='ROOT_CLOSED_RAW_PRIVATE_READ128_ARM'and g['arm']==a.arm-1 and g['readWindow']==ORDER[a.arm-2]and g['codeFingerprint']==r['codeFingerprint']and g['sourceFreezeSha256']==('bec3b804629c8c97e3ca55af0a32cdbde9239a66377cc8e5ef7c6f1fa8ae7b8c' if a.arm==2 else a.freeze_sha256) and g['releaseSha256']==digest(path)and g['all20000RawOutcomesVerified']and g['strictSchedulerValid']and g['allOriginalNativeAndRawPrivateGitBlobsVerified'],'Prior actual same-new-artifact root qualification differs')
            previous=PREP/('arm-'+str(a.arm-1));completion=json.loads((previous/'completion.json').read_text());after=json.loads((previous/'after-clean-stop.json').read_text());require(completion['passed']and completion['allOwnedStopped']and completion['errors']==[],'Previous actual closure incomplete');archive=previous/'pilot-after-clean-stop.tar.gz';require(archive.stat().st_size==after['archive']['archive']['bytes']and m.digest(archive)==after['archive']['archive']['sha256']==g['closedNativeArchiveSha256'],'Previous full native original differs');m.verify_archive_members(archive,after['archive']['inventory']);prior=dict(passed=True,arm=a.arm-1,gateSha256=a.prior_gate_sha256,privateCommit=g['privateCommit'])
        idle=m.strict_idle(b);protected=m.protected_state(b,r);minimum=m.minimum_initial_free_bytes(r);require(shutil.disk_usage(m.ROOT).free>=minimum,'Full derived growth/archive/1GiB space floor required');require(b.memory_headroom()>=8*m.GIB,'Fresh8GiB memory headroom required')
        return dict(passed=True,atUtc=b.now(),arm=a.arm,readWindow=ORDER[a.arm-1],sourceFreezeSha256=a.freeze_sha256,releaseSha256=digest(path),noJavaStarted=True,idle=idle,protectedOriginal=protected,priorArm=prior,minimumInitialFreeBytes=minimum,scope='Fixed20000@1000,common128,5second equal pre-load warm-up,uninstrumented ABAB; no capacity ceiling or hard realtime')
    m.parent_argv=parent_argv;m.preflight=preflight;m.validate_fresh_lineage=fresh_lineage
    if not a.start_new:print(json.dumps(preflight(base,release)));return
    result=m.execute(base,release,path);print(json.dumps(dict(result,sourceCommit=release['sourceCommit'],commonReadWindow128Envelope=True,sourceFreezeSha256=a.freeze_sha256,allRawQualificationStillRequired=True)))
if __name__=='__main__':main()
