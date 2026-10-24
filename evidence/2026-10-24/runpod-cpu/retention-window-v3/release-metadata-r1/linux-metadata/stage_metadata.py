from pathlib import Path
import base64,datetime,hashlib,importlib.util,json,shutil,subprocess,tarfile,shlex,traceback
base=Path(__file__).resolve().parent.parent;out=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n')
def main():
 assert not (out/'REGISTRATION.json').exists(),'No resubmission/overwrite'
 obs=base/'window-cloud-release-observation-r1';candidate=base/'window-cloud-abab-candidate-r1/release/release.candidate.json'
 assert sha(candidate)=='81e71984f61e63ed6cf941a17305a783929d5230e4d7aee53c2e59b5a569b158'
 lib=out/'inputs/lib';lib.mkdir(parents=True);classes=out/'inputs/classes/io/vectormatch/cluster';classes.mkdir(parents=True)
 expected=json.loads((obs/'REGISTRATION.json').read_text())['inputPins'];names=['cluster-0.1.0-SNAPSHOT.jar','core-0.1.0-SNAPSHOT.jar','aeron-all-1.53.3.jar','agrona-2.6.1.jar']
 for name in names:
  p=obs/'lib'/name;assert sha(p)==expected[str(p)]['sha256'];shutil.copy2(p,lib/name)
 source=obs/'WindowReleaseObservationV3.java';assert sha(source)=='b67b293d56ab0b2e72e5daee6202ac3f1ca8e8b3c1e7053a0f5f8d4489fb76ef';shutil.copy2(source,out/'inputs'/source.name)
 klass=obs/'classes/io/vectormatch/cluster/WindowReleaseObservationV3.class';assert sha(klass)=='254db8351473456f4d4b0388686a3471f58bb412bbb20c124dfc05f449233207';shutil.copy2(klass,classes/klass.name)
 files={str(p.relative_to(out/'inputs')):p for p in sorted((out/'inputs').rglob('*')) if p.is_file()};assert len(files)==6
 rows={n:{'bytes':p.stat().st_size,'sha256':sha(p),'mode':p.stat().st_mode&0o777} for n,p in files.items()}
 bundle=out/'metadata-inputs.tar.gz'
 with bundle.open('xb') as f,tarfile.open(fileobj=f,mode='w:gz',compresslevel=1) as tar:
  for n,p in files.items():tar.add(p,arcname=n,recursive=False)
 c={'root':'/opt/vectormatch-cpu/preparation/window-release-metadata-r1','host':'ed6c0673f5cb','java':'/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java','javaSha256':'9cad3f2620d3ef2ed10b26f922af7e773d54fdaa05f615d6d6df014f3fec4155','releaseSha256':'f83f6dcc966043c93cd498ac8e7ee7c310852074970d62c702e4ad2710002898','jarOrder':names,'rows':rows,'bundleSha256':sha(bundle)}
 spec=importlib.util.spec_from_file_location('cpu_metadata_remote',base/'remote.py');remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
 program=(out/'remote_metadata.py').read_text();command=remote.sshargs()+['python3 -c '+shlex.quote(program)+' '+shlex.quote(base64.b64encode(json.dumps(c).encode()).decode())]
 save(out/'REGISTRATION.json',{'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidateSha256':sha(candidate),'remoteHelperSourceSha256':sha(out/'remote_metadata.py'),'stageSourceSha256':sha(out/'stage_metadata.py'),'remotePySha256':sha(base/'remote.py'),'remoteInlinePythonSource':program,'remoteCommandWithoutSshKeyArguments':command[-1],'inputConfig':c,'scope':'Exclusive metadata-only staging/run authorized by root; no canonical ABAB preparation/controller/cluster/driver/SQL/business start'})
 result=subprocess.run(command,input=bundle.read_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
 (out/'ssh.stdout').write_bytes(result.stdout);(out/'ssh.stderr').write_bytes(result.stderr)
 save(out/'ssh-execution.json',{'exitCode':result.returncode,'completedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stdoutSha256':sha(out/'ssh.stdout'),'stderrSha256':sha(out/'ssh.stderr')})
 assert result.returncode==0,'Metadata SSH failed; preserve all outputs and do not resubmit'
 response=json.loads(result.stdout);assert response['passed'] is True;raw=base64.b64decode(response.pop('observationRawBase64'));assert hashlib.sha256(raw).hexdigest()==response['observationSha256']
 (out/'actual-linux-distribution-observation.json').write_bytes(raw)
 for field,name in [('stdoutBase64','java.stdout'),('stderrBase64','java.stderr')]: (out/name).write_bytes(base64.b64decode(response.pop(field)))
 save(out/'remote-receipt.json',response)
 local=json.loads((obs/'actual-distribution-observation.json').read_text());linux=json.loads(raw)
 for key in local:
  if key=='actualSources':continue
  assert linux[key]==local[key], 'Metadata field differs: '+key
 assert len(linux['actualSources'])==len(local['actualSources'])==4
 for a,b in zip(local['actualSources'],linux['actualSources']):
  assert {k:v for k,v in a.items() if k!='path'}=={k:v for k,v in b.items() if k!='path'}
  assert b['path']==c['root']+'/lib/'+Path(a['path']).name
 assert response['execution']['exitCode']==0 and response['execution']['allInputsUnchanged'] is True and response['execution']['metadataJvmExited'] is True
 assert response['stagedFiles']==rows
 summary={'passed':True,'candidateSha256':sha(candidate),'actualLinuxObservationSha256':sha(out/'actual-linux-distribution-observation.json'),'actualMetadataHelperSourceSha256':sha(out/'remote_metadata.py'),'remoteReceiptSha256':sha(out/'remote-receipt.json'),'allObservationFieldsEqualLocalExceptActualJarPaths':True,'canonicalJavaAndReleaseShaReverifiedBeforeAfter':True,'allInputsUnchangedBeforeAfter':True,'metadataJvmExited':True,'metadataRoot':c['root'],'canonicalBenchmarkPrepStaged':False,'controllerStarted':False,'clusterOrDriverStarted':False,'cpuFunctionalOrPerformanceProven':False,'releaseReady':False,'completedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat()};save(out/'SUCCESS.json',summary);print(json.dumps(summary))
if __name__=='__main__':
 try:main()
 except BaseException as error:
  save(out/'FAILED.json',{'passed':False,'error':repr(error),'traceback':traceback.format_exc(),'noAutomaticRetry':True,'failedAttemptRetained':True});raise
