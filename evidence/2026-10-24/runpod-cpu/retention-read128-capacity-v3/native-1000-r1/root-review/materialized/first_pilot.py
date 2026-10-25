"""One fresh500/s native qualification; reviewed ownership/closure machinery reused byte-for-byte."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,platform,shutil,socket,stat,sys
HERE=Path(__file__).resolve().parent
PREP=Path('/opt/vectormatch-cpu/experiments/read128-capacity-1000-r1')

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(value,message):
    if not value:raise RuntimeError(message)

def main():
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--freeze-sha256',required=True);p.add_argument('--start-new',action='store_true');a=p.parse_args()
    require(HERE==PREP,'Exact new synthetic namespace required')
    frozen=HERE/'FROZEN.json';require(digest(frozen)==a.freeze_sha256,'Root-frozen source manifest differs')
    pins=json.loads(frozen.read_text())
    for n,row in pins['files'].items():
        q=HERE/n;require(q.is_file()and not q.is_symlink()and q.stat().st_size==row['bytes']and digest(q)==row['sha256']and stat.S_IMODE(q.stat().st_mode)==row['mode'],'Source/package body differs: '+n)
    spec=importlib.util.spec_from_file_location('cpu_read_window32_abab',HERE/'cpu_read_window32_abab.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
    require(digest(m.__file__)=='1d15cd2c53e0914c6d1d203cc486c563be3d2cfdaa1fa159ffaa8ffd231b14c4','Original reviewed lifecycle source differs')
    m.JOB=PREP/'attempt-1000';m.PAIR=m.JOB/'idle-arm';m.ARM=1;m.WINDOWS=[128];m.READ_WINDOW_ORDER=(128,);m.OWNER_PARK_ORDER=(1000000,)
    # PREP inside the original module remains its original path solely for the original absence/boot baseline.
    exec(compile((HERE/'capacity_validators.py').read_text(),str(HERE/'capacity_validators.py'),'exec'),m.__dict__)
    release_path=HERE/'release.json';release=json.loads(release_path.read_text());m.FROZEN_RELEASE_SHA=digest(release_path)
    m.SOURCE_COMMIT=release['sourceCommit'];m.CODE_FINGERPRINT=release['codeFingerprint']
    base=m.load_base()
    def parent_argv(r):
        return [r['java'],'-Dvectormatch.retention.idleMaxParkNs=100000','-Dvectormatch.retention.ownerPollMaxParkNs=1000000']+r['parentJvmArguments']+['-cp',':'.join(r['classPath']),m.MAIN,str(m.PAIR),'maintained-read128-capacity','1000','42000']
    def preflight(b,r):
        require(platform.system()=='Linux'and platform.machine()=='x86_64'and socket.gethostname()=='33ace3d92505'and os.geteuid()==0,'Exact Linux/root/current CPU required')
        b.no_links(PREP);require(not m.JOB.exists()and not m.PAIR.exists(),'Fresh only; no rerun or resume')
        for n,row in pins['files'].items():
            q=HERE/n;b.no_links(q);require(q.stat().st_size==row['bytes']and digest(q)==row['sha256'],'Staged source changed before launch')
        require(digest(r['java'])==r['javaExecutableSha256']and digest(Path(r['java']).parents[1]/'release')==r['jdkReleaseSha256'],'Actual pinned JDK differs')
        for n,row in r['artifacts'].items():
            q=Path(n);b.no_links(q);require(q.stat().st_size==row['bytes']and digest(q)==row['sha256'],'Actual new installed JAR differs')
        observation=json.loads((HERE/'linux-metadata.json').read_text());review=json.loads((HERE/'linux-metadata-root-review.json').read_text())
        require(review['passed']and review['actualLinuxPlansMatchLocal']and review['allSevenActualLoadedOriginsMatchStagedJars']and review['strictOwnedPidAbsentAfterWait']and review['observationSha256']==digest(HERE/'linux-metadata.json'),'Actual Linux metadata closure differs')
        require(observation['actualCodeFingerprint']==r['codeFingerprint']and observation['profileSha256']==r['profileFingerprint']and observation['plans']['1000']['plan']==r['derivedPlan'],'Actual Linux selected plan/code differs')
        require(r['derivedPlan']['arrivals']==20000 and r['derivedPlan']['maxReadOnlyInFlight']==128 and r['derivedPlan']['eventFetchCount']==32 and r['derivedPlan']['admissionRejections']==[],'Exact finite codec admission differs')
        idle=m.strict_idle(b);protected=m.protected_state(b,r)
        minimum=m.minimum_initial_free_bytes(r);require(shutil.disk_usage(m.ROOT).free>=minimum,'Full finite growth/archive/1GiB free-space budget required')
        require(b.memory_headroom()>=8*m.GIB,'8GiB fresh memory headroom required')
        return dict(passed=True,atUtc=b.now(),idle=idle,protectedOriginal=protected,noJavaStarted=True,minimumInitialFreeBytes=minimum,sourceFreezeSha256=a.freeze_sha256,scope='First fresh20000@1000 with common128 qualification of NEW maintained-capacity artifact; no higher-load permission implied by this controller')
    m.parent_argv=parent_argv;m.preflight=preflight
    if not a.start_new:print(json.dumps(preflight(base,release)));return
    result=m.execute(base,release,release_path)
    print(json.dumps(dict(result,newArtifactSourceCommit=release['sourceCommit'],maintainedCapacityPreset=True,rate=1000,allHigherPresetsStillUnexecuted=True)))

if __name__=='__main__':main()
