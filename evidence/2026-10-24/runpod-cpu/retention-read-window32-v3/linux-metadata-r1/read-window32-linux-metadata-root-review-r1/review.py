from pathlib import Path
import json,hashlib,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';P=B/'read-window32-linux-metadata-preparation-r1';E=B/'read-window32-linux-metadata-execution-r1';O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
r=load(E/'remote-receipt.json');s=load(E/'SUCCESS.json');a=load(E/'actual-linux-distribution-observation.json');c=load(P/'metadata-config.json');local=load(B/'read-window32-local-preparation-r1/metadata-r1/observation.json')
assert s['passed'] and r['passed'] and not s['benchmarkExecuted'] and not s['releaseReady'] and not s['performanceEvidence']
assert sha(E/'actual-linux-distribution-observation.json')==r['observationSha256']==s['linuxObservationSha256']=='b9217e7d2adc2e0f1fea742c32fc56ed46984881b2f5405839f23595263efa9f'
assert sha(E/'remote-receipt.json')==s['receiptSha256']
x=r['execution'];registration=r['registration'];command=registration['command']
assert x['exitCode']==0 and not x['timedOut'] and x['metadataJvmExited'] and x['strictOwnedPidAbsentAfterWait'] and not x['processIdentityObservationGap'] and x['allInputsUnchanged']
assert x['ownedParentPid']==x['actualProcessIdentity']['pid']==69431 and x['actualProcessIdentity']['startTicks']==5325814
assert hashlib.sha256(b'\0'.join(v.encode() for v in command)+b'\0').hexdigest()==x['actualProcessIdentity']['commandSha256']
assert x['actualProcessIdentity']['actualExecutable']==registration['actualJavaExecutable']==c['java']
assert x['javaExecutableSha256After']==registration['javaExecutableSha256']==c['javaSha256'] and x['jdkReleaseSha256After']==registration['jdkReleaseSha256']==c['releaseSha256']
assert sha(E/'java.stdout')==x['stdoutSha256'] and sha(E/'java.stderr')==x['stderrSha256']
assert r['stagedFiles']==registration['inputInventory']==c['rows'] and registration['hostname']==c['host']
assert a['sourceCommit']=='605eb43fcafd8fa0a6287304387c93c4d1bbddf6' and a['actualCodeFingerprint']==local['actualCodeFingerprint']=='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea'
assert a['actualMetadataPlatform']['osName']=='Linux' and a['actualMetadataPlatform']['osArch']=='amd64' and a['actualMetadataPlatform']['javaRuntimeVersion'].startswith('21.0.13+9')
assert a['fixedEventFetchCount']==32 and a['selectedWindowPlanDifferenceKeys']=={'fixedPage32':['requestedReadWindow']}
for window in ['8','32']:assert a['plans'][window]==local['plans']['page32-window'+window]
for name,row in a['distributionJars'].items():
 q=P/'inputs/lib'/name;assert sha(q)==row['sha256'] and q.stat().st_size==row['bytes'] and row['path']==c['root']+'/lib/'+name
 assert {k:v for k,v in row.items() if k!='path'}=={k:v for k,v in local['distributionJars'][name].items() if k!='path'}
assert len(a['actualCodeSources'])==7 and len(a['distributionJars'])==4
for row in a['actualCodeSources']:assert {k:v for k,v in row.items() if k!='class'}==a['distributionJars'][Path(row['path']).name]
assert a['noDriverOrClusterStarted'] and not a['nativeUdpOrBusinessSessionStarted'] and not a['cliExecuted'] and not a['performanceEvidence']
ssh=load(E/'ssh-execution.json');assert ssh['exitCode']==0 and not ssh['timedOut'] and sha(E/'ssh.stdout')==ssh['stdoutSha256'] and sha(E/'ssh.stderr')==ssh['stderrSha256']
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),reviewer='root; independent of metadata author',actualLinuxMetadataSha256=sha(E/'actual-linux-distribution-observation.json'),allSixStagedFilesMatchRootReviewedBodies=True,allSevenClassOriginsMatchFourFullJars=True,fixedPage32Window8And32PlansEqualActualLocal=True,actualExactProcessArgvExecutableAndStartIdentityVerified=True,normalExit0AndStrictOwnedPidAbsenceVerified=True,actualMetadataJvmExecuted=True,nativeBenchmarkExecuted=False,nativeQualificationPending=True,performanceEvidence=False,inputPins={str(p.relative_to(B)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(E.iterdir()) if p.is_file()})
with (O/'ROOT_REVIEW.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k!='inputPins'}))
