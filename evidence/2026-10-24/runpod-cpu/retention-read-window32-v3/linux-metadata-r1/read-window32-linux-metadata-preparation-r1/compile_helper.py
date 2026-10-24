"""Only javac runs here; the new metadata main and application tests are never invoked."""
from pathlib import Path
import hashlib,json,subprocess,datetime,time,struct
OUT=Path(__file__).resolve().parent;BASE=OUT.parents[3];JDK=BASE/'.tools/jdk';SOURCE=OUT/'inputs/ReadWindow32LinuxDistributionObservation.java'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pin(p):return {'bytes':p.stat().st_size,'sha256':sha(p)}
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def main():
 out=OUT/'helper-compile-r1';out.mkdir();classes=OUT/'inputs/classes';classes.mkdir()
 jars=sorted((OUT/'inputs/lib').glob('*.jar'));assert len(jars)==4
 argv=[str(JDK/'bin/javac'),'--release','21','-encoding','UTF-8','-cp',':'.join(str(p)for p in jars),'-d',str(classes),str(SOURCE)]
 inputs={str(p):pin(p)for p in [SOURCE,*jars,JDK/'bin/javac',JDK/'bin/java',JDK/'release']}
 save(out/'REGISTRATION.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':argv,'inputs':inputs,'compilerJvmExecutedIntended':True,'metadataJvmExecutedIntended':False,'linuxExecuted':False,'cloudExecuted':False})
 start=time.monotonic()
 with(out/'stdout').open('xb')as stdout,(out/'stderr').open('xb')as stderr:r=subprocess.run(argv,cwd=OUT,stdout=stdout,stderr=stderr,timeout=120)
 p=classes/'io/vectormatch/cluster/ReadWindow32LinuxDistributionObservation.class';major=struct.unpack('>H',p.read_bytes()[6:8])[0]if p.exists()else None
 same=all(pin(Path(p))==row for p,row in inputs.items())
 save(out/'EXECUTION.json',{'exitCode':r.returncode,'durationSeconds':time.monotonic()-start,'inputsUnchanged':same,'source':pin(SOURCE),'class':pin(p)if p.exists()else None,'classFile':str(p),'classMajor':major,'compilerJvmExecuted':True,'metadataJvmExecuted':False,'applicationTestsExecuted':False,'linuxExecuted':False,'cloudExecuted':False,'stdoutSha256':sha(out/'stdout'),'stderrSha256':sha(out/'stderr')})
 assert r.returncode==0 and same and major==65
 print(json.dumps({'passed':True,'classMajor':major,'classSha256':sha(p),'compilerJvmExecuted':True,'metadataJvmExecuted':False}))
if __name__=='__main__':main()
