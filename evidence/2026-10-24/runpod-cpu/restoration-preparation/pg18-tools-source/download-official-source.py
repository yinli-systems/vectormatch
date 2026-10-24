from pathlib import Path
import datetime,hashlib,json,re,subprocess,sys
STAGE=Path(__file__).resolve().parent
BASE='https://ftp.postgresql.org/pub/source/v18.6/'
SOURCE='postgresql-18.6.tar.bz2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write_new(name,obj):
 with (STAGE/name).open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
write_new('download-plan.json',{'schemaVersion':1,'startedAtUtc':utc(),'purpose':'LOCAL_ONLY_OFFICIAL_POSTGRESQL_18_6_TOOL_SOURCE_PREPARATION','sourceVersion':'18.6','primaryIndex':BASE,'primarySources':['https://www.postgresql.org/docs/18/install-make.html','https://www.postgresql.org/docs/18/install-requirements.html','https://www.postgresql.org/docs/18/app-pgcontroldata.html'],'urls':[BASE+SOURCE+'.sha256',BASE+SOURCE],'scriptSha256':sha(Path(__file__)),'cloudActions':False,'compile':False})
commands=[]
for name in [SOURCE+'.sha256',SOURCE]:
 target=STAGE/name;partial=STAGE/(name+'.partial');assert not target.exists() and not partial.exists()
 argv=['curl','-fsSL','--proto','=https','--tlsv1.2','--max-redirs','3','--connect-timeout','20','--max-time','180','--retry','2','-w','%{http_code} %{url_effective}',BASE+name,'-o',str(partial)]
 r={'argv':argv,'startedAtUtc':utc()};process=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 r.update(exitCode=process.returncode,completedAtUtc=utc(),httpStatusAndFinalUrl=process.stdout,stderr=process.stderr);commands.append(r)
 if process.returncode:
  write_new('download-result.json',{'passed':False,'commands':commands});sys.exit(process.returncode)
 if process.stdout!='200 '+BASE+name:raise ValueError('unexpected HTTP status or final source host')
 partial.rename(target)
checksum=(STAGE/(SOURCE+'.sha256')).read_text();m=re.fullmatch(r'([a-f0-9]{64})\s+\*?'+re.escape(SOURCE)+r'\s*',checksum)
if not m:raise ValueError('unexpected official checksum format')
actual=sha(STAGE/SOURCE);expected=m.group(1)
result={'schemaVersion':1,'passed':actual==expected,'completedAtUtc':utc(),'sourceVersion':'18.6','publishedSha256':expected,'actualSha256':actual,'sourceBytes':(STAGE/SOURCE).stat().st_size,'checksumFileSha256':sha(STAGE/(SOURCE+'.sha256')),'commands':commands,'cloudActions':False,'sourceCompiled':False}
write_new('download-result.json',result);print(json.dumps(result,indent=2));sys.exit(0 if result['passed'] else 1)
