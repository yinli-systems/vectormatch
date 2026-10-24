from pathlib import Path
import json,hashlib,ast,difflib,datetime,stat
S=Path(__file__).resolve().parent;B=S.parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,v):
 with(S/name).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
old=S/'baseline/cpu_event_fetch_abab.py';new=S/'cpu_read_window32_abab.py'
def defs(p):return {n.name:ast.dump(n,include_attributes=False)for n in ast.parse(p.read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
a,b=defs(old),defs(new);unchanged=sorted(k for k in a.keys()&b.keys()if a[k]==b[k]);changed=sorted(k for k in a.keys()&b.keys()if a[k]!=b[k]);added=sorted(b.keys()-a.keys())
for name in ['load_base','Registry','Telemetry','strict_idle','protected_state','clean_all','collect_stopped','verify_archive_members','validate_egress','validate_egress_progress','validate_long_summary','validate_private_push','allocation_limit','monitor','node_argv']:assert name in unchanged
save('SOURCE_DELTA.json',{'baselineControllerSha256':sha(old),'controllerSha256':sha(new),'unchangedFunctionOrClassNames':unchanged,'changedFunctionOrClassNames':changed,'addedFunctionsOrClasses':added,'noGlobalReplaceOfDigit8':True,'actualLinuxObservationNotAlteredOrExpanded':True})
patch=''.join(difflib.unified_diff(old.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='baseline/cpu_event_fetch_abab.py',tofile='cpu_read_window32_abab.py'))
with (S/'SOURCE_DIFF.patch').open('x')as f:f.write(patch)
parser=B/'read-window32-long-parser-preparation-r1/SOURCE_FROZEN.json';assert sha(parser)=='766ef61f32b8c0dfe8010749795637969b319ddcd19e05d8351830d0e02836ad';pf=json.loads(parser.read_text());mapping={name:'long-parser/'+Path(name).name for name in pf['sourceFiles']if name.startswith(('source/','tests/'))};assert len(mapping)==12
for original,target in mapping.items():assert sha(S/target)==pf['sourceFiles'][original]['sha256']
source_files={str(p.relative_to(S)):{'bytes':p.stat().st_size,'sha256':sha(p)}for p in sorted((S/'baseline').rglob('*'))if p.is_file()}
save('BASELINE_PROVENANCE.json',{'schemaVersion':1,'originalController':str(B/'cpu-event-fetch-cloud-preparation-r1'),'originalControllerSourceSha256':'eb84eed09cad46c5097c32d980a1629f7c7c7fec3759e904544f7ef9e91e3100','allOriginal27StageableSourceBodiesAndOriginalFreezeCopied':source_files,'newAuthoritativeParserFreezeSha256':sha(parser),'actualLinuxObservationSha256':sha(S/'fixtures/actual-linux-distribution-observation.json'),'actualLinuxReceiptSha256':sha(S/'fixtures/remote-receipt.json'),'actualLocalFourPlanObservationSha256':sha(S/'fixtures/actual-local-distribution-observation.json'),'sourceGenerationNote':'initial adaptation script plus explicit final min-free helper and duplicate-key correction are captured in the authoritative final diff; generation scripts are not runtime inputs'})
for name,count in [('guards-r1',27),('guards-parser-r1',51)]:
 d=json.loads((S/name/'completion.json').read_text());text=(S/name/'stderr').read_text();assert d['exitCode']==0 and d['allInputsUnchanged']and 'Ran '+str(count)+' tests'in text and text.rstrip().endswith('OK')
files=['cpu_read_window32_abab.py','owned_linux_base_8eeb.py','idle_attestation.py','owner_poll_attestation.py','shutdown_warning.py','campaign-qualification-policy.json','release.template.json','test_read_window32_delta.py','PLAN.md','BASELINE_PROVENANCE.json','baseline/cpu_event_fetch_abab.py']+[str(p.relative_to(S))for p in sorted((S/'fixtures').glob('*'))if p.is_file()]+sorted(mapping.values())
files += [str(p.relative_to(S))for p in sorted((S/'test-fixtures').rglob('*'))if p.is_file()]
assert len(files)==len(set(files))==43
rows={name:{'bytes':(S/name).stat().st_size,'sha256':sha(S/name),'mode':stat.S_IMODE((S/name).stat().st_mode)}for name in sorted(files)}
frozen={'schemaVersion':1,'scope':'CPU_READ_WINDOW32_CLOUD_FALSE_READY_SOURCE_PREPARATION','frozenAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceCommit':'605eb43fcafd8fa0a6287304387c93c4d1bbddf6','codeFingerprint':'d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea','controllerSha256':sha(new),'authoritativeParserFreezeSha256':sha(parser),'files':rows,'filesCount':len(rows),'totalBytes':sum(r['bytes']for r in rows.values()),'longParserSourceMapping':mapping,'linuxGuardCommands':[{'scope':'controller','cwd':'.','modules':['test_read_window32_delta'],'tests':27},{'scope':'long-parser','cwd':'long-parser','modules':['test_long_contract','test_phase_baseline','test_read_window32'],'tests':51}],'guardAttempts':{name:{'bytes':(S/name/'completion.json').stat().st_size,'sha256':sha(S/name/'completion.json')}for name in ['guards-r1','guards-parser-r1']},'sourceDiffSha256':sha(S/'SOURCE_DIFF.patch'),'minimumInitialFreeBytes':2116076873,'releaseReady':False,'newArtifactQualificationPendingActualFirstCloudArm':True,'newLinuxMetadataObserved':True,'noPriorNativeSuccessClaimed':True,'noSshJavaGradleNativeGitOrActualRawExecutedHere':True}
save('LOCAL_PREPARATION_FROZEN.json',frozen)
print(json.dumps({'passed':True,'controllerSha256':sha(new),'preparationSha256':sha(S/'LOCAL_PREPARATION_FROZEN.json'),'files':len(rows),'stageFiles':len(rows)+12,'unchangedDefinitions':len(unchanged),'controllerGuards':27,'parserGuards':51}))
