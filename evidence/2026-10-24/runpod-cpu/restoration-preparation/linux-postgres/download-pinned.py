from pathlib import Path
import datetime,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[5];STAGE=Path(__file__).resolve().parent
ARTIFACT='embedded-postgres-binaries-linux-amd64';VERSION='18.6.0'
EXPECTED='008ee189eaa7ca2b58bd01dd950291e638b998392cf982297acd4779ec898ac1'
BASE='https://repo.maven.apache.org/maven2/io/zonky/test/postgres/'+ARTIFACT+'/'+VERSION+'/'+ARTIFACT+'-'+VERSION

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write_new(name,obj):
 with (STAGE/name).open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
plan={'schemaVersion':1,'purpose':'LOCAL_ONLY_PINNED_LINUX_POSTGRES_ARTIFACT_PREPARATION','coordinate':'io.zonky.test.postgres:'+ARTIFACT+':'+VERSION,'expectedSha256':EXPECTED,'startedAtUtc':utc(),'bootstrapSourcePath':'scripts/bootstrap-postgres.py','bootstrapSourceRevision':'e1db2e755a834234efb60b7a1ed291b31ce33c16','bootstrapSourceSha256':sha(ROOT/'runtime/cloud/cpu-20261024/app-restore-worktree/scripts/bootstrap-postgres.py'),'downloaderSha256':sha(Path(__file__)),'urls':[BASE+s for s in ['.jar','.jar.sha256','.pom']],'executeLinux':False,'cloudActions':False}
write_new('download-plan.json',plan)
commands=[]
for suffix in ['.jar','.jar.sha256','.pom']:
 name=ARTIFACT+'-'+VERSION+suffix;target=STAGE/name;partial=STAGE/(name+'.partial')
 assert not target.exists() and not partial.exists()
 argv=['curl','-fsSL','--connect-timeout','20','--max-time','120','--retry','2',BASE+suffix,'-o',str(partial)]
 r={'argv':argv,'startedAtUtc':utc()}
 result=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 r.update(exitCode=result.returncode,completedAtUtc=utc(),output=result.stdout)
 commands.append(r)
 if result.returncode:
  write_new('download-result.json',{'passed':False,'commands':commands,'completedAtUtc':utc()});sys.exit(result.returncode)
 partial.rename(target)
jar=STAGE/(ARTIFACT+'-'+VERSION+'.jar');published=(STAGE/(ARTIFACT+'-'+VERSION+'.jar.sha256')).read_text().strip()
actual=sha(jar)
r={'schemaVersion':1,'passed':actual==EXPECTED==published,'completedAtUtc':utc(),'commands':commands,'pinnedSha256':EXPECTED,'publishedSha256':published,'actualSha256':actual,'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(STAGE.glob(ARTIFACT+'-*')) if p.is_file()},'artifactVersionNotExecuted':True,'runtimeAbiCompatibilityNotTested':True,'cloudActions':False}
write_new('download-result.json',r);print(json.dumps(r,indent=2));sys.exit(0 if r['passed'] else 1)
