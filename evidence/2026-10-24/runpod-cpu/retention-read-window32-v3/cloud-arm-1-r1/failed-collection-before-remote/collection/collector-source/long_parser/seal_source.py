from pathlib import Path
import ast, datetime, difflib, hashlib, json, stat

P=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(name,value):
 with(P/name).open('x')as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def file(p):
 st=p.lstat();assert stat.S_ISREG(st.st_mode)and not p.is_symlink()
 return dict(bytes=st.st_size,sha256=sha(p),mode=stat.S_IMODE(st.st_mode),uid=st.st_uid,gid=st.st_gid)
provenance=read(P/'BASELINE_PROVENANCE.json');original=Path(provenance['sourceBaseline'])
for name,pin in provenance['fullBaselineFiles'].items():
 for root in [original,P/'baseline']:
  p=root/name;assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
assert {str(p.relative_to(P/'baseline'))for p in(P/'baseline').rglob('*')if p.is_file()}==set(provenance['fullBaselineFiles'])
completion=read(P/'guards-r1/COMPLETION.json');registration=read(P/'guards-r1/REGISTRATION.json')
assert completion['passed']and completion['exitCode']==0 and completion['actualDistinctGuards']==51 and completion['allInputsUnchanged']
for name,pin in registration['inputs'].items():
 p=P/name;assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
diff=[]
for folder in ['source','tests']:
 old={str(p.relative_to(P/'baseline')):p for p in(P/'baseline'/folder).glob('*.py')}
 new={str(p.relative_to(P)):p for p in(P/folder).glob('*.py')}
 for name in sorted(set(old)|set(new)):
  left=old[name].read_text().splitlines(True)if name in old else[];right=new[name].read_text().splitlines(True)if name in new else[]
  diff.extend(difflib.unified_diff(left,right,fromfile='baseline/'+name,tofile=name))
(P/'SOURCE_DIFF.patch').write_text(''.join(diff))
identical={}
for p in(P/'source').glob('*.py'):
 old=P/'baseline/source'/p.name
 if not old.exists():continue
 def nodes(path):return {n.name:ast.dump(n,include_attributes=False)for n in ast.parse(path.read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
 before,after=nodes(old),nodes(p)
 identical[p.name]=sorted(name for name in before if name in after and before[name]==after[name])
save('UNCHANGED_AST_BINDINGS.json',dict(scope='Pure source AST comparison only, not runtime evidence',identicalTopLevelFunctionsOrClasses=identical,unchangedWholeFiles=[name for name in ['archive_closure.py','idle_inventory.py','setup_audit.py']if(P/'source'/name).read_bytes()==(P/'baseline/source'/name).read_bytes()],newInterfaces=['audit_read_window32_arm','audit_read_window32_phases'],oldInterfacesNotAliased=True))
meta=P/'fixtures/actual-local-distribution-observation.json';obs=read(meta)
assert obs['sourceCommit']=='605eb43fcafd8fa0a6287304387c93c4d1bbddf6'and obs['actualCodeFingerprint']=='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea'and obs['localLinuxExecuted']is False and obs['cloudExecuted']is False
save('METADATA_PROVENANCE.json',dict(scope='Actual local installed-JAR metadata only; not Linux/native qualification',observation=file(meta),originalPath=str(P.parent/'read-window32-local-preparation-r1/metadata-r1/observation.json'),localCandidateClosedSha256='7edce2f9bb8e23af8ec7ff512c7b9134669e291f23b39e8a61153589cb985b2b',localCandidateInventorySha256='602e464420c7f372bacb7280cf104dd79f492b40b18b5d29b83080973f92d965',localArtifactClosureSha256='2d1cd9593ca8d1d38cbe01c50068a2c3d710f9cf479ab20bb022ec1201d6c96a',independentLocalCandidateReviewSha256='402464dd7b3292a11d50d4ca79b53ea29748fd3f42f734cc86c93986279b48b9',newLinuxMetadataPending=True,newNativeBusinessQualificationPending=True))
save('CODEC_FIXTURES.json',dict(scope='SYNTHETIC protocol bytes constructed by Python guard helper; not JVM-captured network/benchmark evidence',generator=file(P/'tests/binary_codec_fixture.py'),fixtures={name:file(P/'fixtures'/name)for name in ['synthetic-fetch32-request.bin','synthetic-max32-chinese.bin','synthetic-max32-astral.bin']},maximumUtf8DetailBytes=128,eventCount=32,applicationReplyBytes=6763,completeMessageBytes=6795,supportedApplicationEnvelopeBytes=6919,supportedCompleteEnvelopeBytes=6951,noActualJvmNetworkOrBusinessSession=True))
pins={str(p.relative_to(P)):file(p)for p in sorted(P.rglob('*'))if p.is_file()}
save('SOURCE_FROZEN.json',dict(schemaVersion=1,scope='SOURCE_ONLY_FIXED_PAGE32_LONG_READ_WINDOW8_32_PARSER',passed=True,sourceCommit=obs['sourceCommit'],actualLocalMetadataCodeFingerprint=obs['actualCodeFingerprint'],sourceFiles=pins,sourceDiffSha256=sha(P/'SOURCE_DIFF.patch'),fullOriginalBaselineUnchanged=True,sourceAndGuardInputPinsUnchanged=True,pureGuardMethods=51,actualGuardCompletionSha256=sha(P/'guards-r1/COMPLETION.json'),runtimeSourceModules=sorted(p.stem for p in(P/'source').glob('*.py')),explicitFixedEventFetchCount=32,selectedReadWindows=[8,32],rawEntry='source/audit_raw.py:audit_read_window32_arm(selected_window,arm_root,event_fetch_count=32,workload=LONG,local_functional_only=False)',phaseEntry='source/read_phase_audit.py:audit_read_window32_phases(...,selected_window,event_fetch_count=32,maximum_read_phases=24,expected_phase_count=24)',noImplicitSelectedPage=True,defaultCpuSchedulerStrict=True,localFunctionalOptInDiagnosticOnly=True,oldConfigGateDisabled=True,newControllerSchemaPending=True,newLinuxMetadataPending=True,newNativeBusinessQualificationPending=True,releaseReady=False,actualRawAuditOrJavaNativeSshGitBusinessExecuted=False,syntheticGuardsNotRuntimeOrPerformanceEvidence=True,postGuardAdditions='Only documentation, provenance, source diff, unchanged-AST comparison and closure; all registered parser/guard/fixture bodies remain byte-exact'))
files={str(p.relative_to(P)):file(p)for p in sorted(P.rglob('*'))if p.is_file()}
directories=[dict(path=str(p.relative_to(P)),mode=stat.S_IMODE(p.lstat().st_mode),uid=p.lstat().st_uid,gid=p.lstat().st_gid,empty=not any(p.iterdir()))for p in sorted(P.rglob('*'))if p.is_dir()]
save('INVENTORY.json',dict(schemaVersion=1,files=files,directories=directories,payloadFiles=len(files),payloadBytes=sum(row['bytes']for row in files.values()),excludedSelfAndClosure=['INVENTORY.json','CLOSED.json']))
save('CLOSED.json',dict(schemaVersion=1,passed=True,scope='CLOSED_SOURCE_ONLY_FIXED_PAGE32_LONG_READ_WINDOW32_PARSER_PREPARATION',atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceCommit=obs['sourceCommit'],actualLocalMetadataCodeFingerprint=obs['actualCodeFingerprint'],inventorySha256=sha(P/'INVENTORY.json'),sourceFreezeSha256=sha(P/'SOURCE_FROZEN.json'),actualPureGuards=51,allPureGuardsPassed=True,fullOriginalBaselineRetainedAndUnchanged=True,allSourceGuardFixtureInputsUnchanged=True,newLinuxMetadataOrNativeQualificationClaimed=False,releaseReady=False,actualRawAuditOrJavaNativeSshGitBusinessExecuted=False))
print(json.dumps(dict(passed=True,sourceFreezeSha256=sha(P/'SOURCE_FROZEN.json'),inventorySha256=sha(P/'INVENTORY.json'),closedSha256=sha(P/'CLOSED.json'),payloadFiles=len(files),directories=len(directories),payloadBytes=sum(row['bytes']for row in files.values()),pureGuards=51)))
