"""Seal already-tested local source adapters and complete historical baselines only."""
from pathlib import Path
import ast,datetime,difflib,hashlib,json,stat
HERE=Path(__file__).resolve().parent;BASE=HERE.parent
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 return h.hexdigest()
def row(p):
 s=p.lstat();assert stat.S_ISREG(s.st_mode)and not p.is_symlink()and s.st_nlink==1
 return dict(bytes=s.st_size,sha256=sha(p),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
def files(root):return {str(p.relative_to(root)):row(p)for p in sorted(root.rglob('*'))if p.is_file()}
def save(p,v):
 with p.open('x')as f:json.dump(v,f,sort_keys=True,indent=2);f.write('\n')
baseline=BASE/'cpu-event-fetch-collection-preparation-r1';parser=BASE/'read-window32-long-parser-preparation-r1';controller=BASE/'cpu-read-window32-cloud-preparation-r2';close=BASE/'cpu-read-window32-close-preparation-r1'
assert files(baseline)==files(HERE/'baseline')
assert files(parser)==files(HERE/'long_parser')
assert files(controller)==files(HERE/'controller-source-preparation')
assert files(close)==files(HERE/'close-source-preparation')
assert sha(parser/'SOURCE_FROZEN.json')=='766ef61f32b8c0dfe8010749795637969b319ddcd19e05d8351830d0e02836ad'
assert sha(HERE/'controller-preparation-frozen.json')=='e7f356c95b4f1622f844f8841196ec658daa50b96aba522b55a27da242d25368'
assert sha(HERE/'cpu_read_window32_abab.py')=='d0dbd4c5051ab328e94102e151382d358aa1c5dee115fbc991ad2e0d41fe8c04'
assert sha(HERE/'idle_attestation.py')=='74a666f0087e92de6ce1da311bd73e4941db7cc2b264a472cc84b0512d40032a'
for name in ['owner_poll_attestation.py','owned_linux_base_8eeb.py','shutdown_warning.py','verify_closed_archives.py']:
 assert sha(HERE/name)==sha(baseline/name)
def defs(path):return {n.name:ast.dump(n,include_attributes=False)for n in ast.parse(path.read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
ast_bindings={}
for name in ['common.py','closed_bindings.py','verify_closed_archives.py','audit_native_artifacts.py','audit_raw.py','owner_poll_attestation.py','owned_linux_base_8eeb.py','shutdown_warning.py']:
 old,new=defs(baseline/name),defs(HERE/name);ast_bindings[name]=[n for n in old if old[n]==new.get(n)]
assert {'require','sha','hexsha','relative','egress','egress_progress'}<=set(ast_bindings['common.py'])
assert 'project'in ast_bindings['closed_bindings.py']
assert defs(baseline/'verify_closed_archives.py')==defs(HERE/'verify_closed_archives.py')
save(HERE/'UNCHANGED_FUNCTION_AST_BINDINGS.json',dict(bindings=ast_bindings,completeImported766efParserUnmodified=True,
    completeNativeOuterNestedByteVerifierUnmodified=True,originalToMaterializedBindingFunctionUnmodified=True,
    uniqueOwnerValidatorAndOwnedLinuxBaseAndShutdownClassifierByteUnmodified=True))
origins={'baseline':baseline,'long_parser':parser,'controller-source-preparation':controller,'close-source-preparation':close,
         'parser-and-metadata-root-review':BASE/'read-window32-parser-and-metadata-archive-root-review-r1'}
save(HERE/'BASELINE_PROVENANCE.json',dict(schemaVersion=1,sourceTrees={name:dict(source=str(root),files=files(root))for name,root in origins.items()},
    allOriginalTreesCopiedWithoutExclusions=True,originalsNotModified=True,noActualRawNativeOrLargeBenchmarkBodiesCopied=True))
save(HERE/'SOURCE_BINDINGS.json',dict(schemaVersion=1,sourceCommit='605eb43fcafd8fa0a6287304387c93c4d1bbddf6',codeFingerprint='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea',
    controllerSourceSha256=sha(HERE/'cpu_read_window32_abab.py'),controllerPreparationSha256=sha(HERE/'controller-preparation-frozen.json'),
    parserFreezeSha256=sha(HERE/'long_parser/SOURCE_FROZEN.json'),closeProbeSourceSha256=sha(close/'inspect_closed_read_window32_arm.py'),
    closeSourceFreezeSha256=sha(close/'SOURCE_FROZEN.json'),dynamicIdleHelperSha256=sha(HERE/'idle_attestation.py'),
    exactStagedInitialFileCount55=True,collectorConfigSchemaVersion=6,releaseSchemaVersion=3,closedControllerGateSchemaVersion=3,
    localFourPlanMetadataSha256=sha(HERE/'fixtures/actual-local-distribution-observation.json'),
    realLinuxTwoPlanMetadataSha256=sha(HERE/'fixtures/actual-linux-distribution-observation.json'),minimumInitialFreeBytes2116076873=True))
changed=[];diff=''
for name in ['common.py','owner_bundle.py','audit_native_artifacts.py','audit_raw.py','build_config.py','collect_and_audit.py','collect_closed_round.py','finalize_local_collection.py','frozen_parser.py','idle_attestation.py','telemetry_audit.py','closed_bindings.py','run_guards.py']:
 if sha(baseline/name)!=sha(HERE/name):
  changed.append(name);diff+=''.join(difflib.unified_diff((baseline/name).read_text().splitlines(True),(HERE/name).read_text().splitlines(True),fromfile='baseline/'+name,tofile=name))
diff+=''.join(difflib.unified_diff([], (HERE/'test_read_window32_collection.py').read_text().splitlines(True),fromfile='/dev/null',tofile='test_read_window32_collection.py'))
(HERE/'SOURCE_DIFF.patch').open('x').write(diff)
guard=json.loads((HERE/'guards-r2/completion.json').read_text());authoritative=json.loads((HERE/'guards-parser-r1/COMPLETION.json').read_text())
assert guard['passed']and guard['actualTestsRun']==20 and guard['allInputSourcesUnchanged']
assert authoritative['passed']and authoritative['actualDistinctGuards']==51 and authoritative['allInputsUnchanged']
assert sha(HERE/'guards-parser-r1/source.zip')=='4def95f547bc7ffa98fe87c9ebd4aad4dce4268455bf299909a974535de3b857'
assert '__CONTROLLER_PREPARATION_SHA__'not in(HERE/'common.py').read_text()
assert '__NEW_CLOSE_SOURCE_SHA__'not in(HERE/'collect_and_audit.py').read_text()
current=files(HERE);active={name:pin for name,pin in current.items()if not name.startswith('baseline/')};old={name:pin for name,pin in current.items()if name.startswith('baseline/')}
save(HERE/'LOCAL_PREPARATION_FROZEN.json',dict(schemaVersion=1,status='ROOT_REVIEWABLE_LOCAL_SOURCES_ONLY',scope='SOURCE_ONLY_NEW605_FIXEDPAGE32_SELECTED_READ8_32_STRICT_COLLECTION_ADAPTER',
    sourceCommit='605eb43fcafd8fa0a6287304387c93c4d1bbddf6',codeFingerprint='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea',
    sourceFiles=active,baselineSourceFiles=old,controllerPreparationSha256=sha(HERE/'controller-preparation-frozen.json'),
    controllerSourceSha256=sha(HERE/'cpu_read_window32_abab.py'),closedProbeSha256=sha(close/'inspect_closed_read_window32_arm.py'),
    parserFreezeSha256=sha(HERE/'long_parser/SOURCE_FROZEN.json'),actualTestsRun=20,authoritativeParserGuardTests=51,
    guardAttempt='guards-r2',guardCompletionSha256=sha(HERE/'guards-r2/completion.json'),parserGuardCompletionSha256=sha(HERE/'guards-parser-r1/COMPLETION.json'),
    allRealControllerR2AndCloseAndParserCopiesComplete=True,guardR1FixtureFailureAndSourceZipRetained=True,
    postGuardChangesOnlyDocumentationProvenanceAstDiffAndClosure=True,releaseReady=False,applicationStarted=False,remoteAccessed=False,actualRawAuditExecuted=False))
inventory=files(HERE);dirs={}
for p in[HERE]+sorted(HERE.rglob('*')):
 assert not p.is_symlink()
 if p.is_dir():s=p.stat();dirs[str(p.relative_to(HERE))]=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
save(HERE/'INVENTORY.json',dict(schemaVersion=1,files=inventory,directories=dirs,payloadFiles=len(inventory),payloadBytes=sum(p['bytes']for p in inventory.values())))
save(HERE/'CLOSED.json',dict(schemaVersion=1,passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='CLOSED_SOURCE_ONLY_READ_WINDOW32_STRICT_COLLECTION_PREPARATION',
    inventorySha256=sha(HERE/'INVENTORY.json'),preparationSha256=sha(HERE/'LOCAL_PREPARATION_FROZEN.json'),pureAdapterGuards20=True,pureAuthoritativeParserGuards51=True,
    fullOriginalBaselineAnd766efParserAndCorrectedR2AndCloseCopiesUnchanged=True,realLinuxTwoPlansNotFabricatedIntoFour=True,
    strictTimingDefaultFalseAndAllOriginalRawForceAckCanonicalUnknownGatesRetained=True,releaseReady=False,actualNativeOrRawAuditOrSshJvmGitExecuted=False,rootIndependentReviewRequired=True))
print(json.dumps(dict(passed=True,preparationSha256=sha(HERE/'LOCAL_PREPARATION_FROZEN.json'),closedSha256=sha(HERE/'CLOSED.json'),
    inventorySha256=sha(HERE/'INVENTORY.json'),payloadFiles=len(inventory),directories=len(dirs),payloadBytes=sum(p['bytes']for p in inventory.values()))))
