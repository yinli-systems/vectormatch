#!/usr/bin/env python3
"""Close the already copied proof after classifying three public Netty fixture hits."""
from pathlib import Path
import hashlib,json,shutil,datetime,subprocess
ROOT=Path('/Users/kevin/Documents/ChatGPT/App 2');WORK=ROOT/'runtime/cloud/cpu-20261024/retention-integration-worktree'
SOURCE=WORK/'build/integration-validation';DEST=ROOT/'evidence/2026-10-24/runpod-cpu/retention-integration-v3/validation-r1'
SELECTED=('r1','r2','test-db-r1');sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
assert not (DEST/'completion.json').exists() and not (DEST/'proof-inventory.json').exists()
review=json.loads((DEST/'credential-marker-review.json').read_text());assert review['hitCount']==len(review['hits'])==3
classification=DEST/'tool-validation/netty-public-probe-key-review/classification.json';classified=json.loads(classification.read_text())
assert classified['publicProbingKeySha256']=='67153216753676a99069a64f0986ef7015efed5eca8d545261c6c1aa9e9117c8'
assert len(classified['entries'])==3 and all(e['publicProbingKeyExactBytesPresent'] is True for e in classified['entries'])
expected={e['entry'] for e in classified['entries']}
assert {hit['path'].split('!')[-1] for hit in review['hits']}==expected
assert {hit['pattern'] for hit in review['hits']}=={'complete-private-key-pem'}
assert len(review['uniqueJarSha256Inventories'])==77 and len(review['jarOccurrences'])==104
copy_manifest={};directories={};copied=0
for selection in SELECTED:
 source=SOURCE/selection;destination=DEST/selection
 source_files={str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
 dest_files={str(p.relative_to(destination)) for p in destination.rglob('*') if p.is_file()}
 assert source_files==dest_files,'Source file set changed after copy'
 assert {str(p.relative_to(source)) for p in source.rglob('*') if p.is_dir()}=={str(p.relative_to(destination)) for p in destination.rglob('*') if p.is_dir()}
 for p in [source,*sorted(source.rglob('*'))]:
  assert not p.is_symlink();rel=str(p.relative_to(SOURCE));target=DEST/rel
  if p.is_dir():assert target.stat().st_mode&0o777==p.stat().st_mode&0o777;directories[rel]={'mode':p.stat().st_mode&0o777};continue
  item={'bytes':p.stat().st_size,'sha256':sha(p),'mode':p.stat().st_mode&0o777}
  assert item=={'bytes':target.stat().st_size,'sha256':sha(target),'mode':target.stat().st_mode&0o777}
  copy_manifest[rel]=item;copied+=item['bytes']
assert copied<512*1024**2 and shutil.disk_usage(ROOT).free>1024**3
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=WORK,text=True).strip()=='2bda894886937c589d9f1b28e2a23132bca3188b'
assert not subprocess.check_output(['git','status','--porcelain=v1'],cwd=WORK,text=True).strip()
shutil.copy2(Path(__file__),DEST/'tool-validation/close-retention-integration-validation-r1.py')
classification_summary={'originalReviewSha256':sha(DEST/'credential-marker-review.json'),'originalHitCountRetained':3,'reviewedPublicLibraryFixtureHits':3,'unresolvedHits':0,'userCredentialFindingsInInspectedScope':0,'classificationSha256':sha(classification),'publishedPrimarySource':'https://github.com/netty/netty/blob/netty-4.2.19.Final/handler/src/main/java/io/netty/handler/ssl/SslUtils.java','scopeUnchanged':'Initial77uniqueJARs/104occurrences plus sourceZIP/text/classes/small-native proof; native content-marker exclusions remain explicit. Additional public pinned Netty source files are SHA-bound in classification.','noGeneralSecretAbsenceGuarantee':True}
with (DEST/'credential-marker-classification.json').open('x') as f:json.dump(classification_summary,f,indent=2);f.write('\n')
with (DEST/'tool-validation/first-pass-marker-stop.json').open('x') as f:
 json.dump({'recordedAfterActualExitUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':['python3','runtime/cloud/cpu-20261024/archive-retention-integration-validation-r1.py'],'observedExitCode':1,'error':'Known credential-marker hits require review; no successful completion receipt','sourceScriptSha256':sha(DEST/'tool-validation/archive-retention-integration-validation-r1.py'),'originalReviewSha256':sha(DEST/'credential-marker-review.json'),'sourceCopiedSuccessfullyBeforeMarkerStop':True,'noTestsRerun':True,'copyNotRepeatedByCloser':True},f,indent=2);f.write('\n')
scope={'sourceWorktree':str(WORK),'sourceDirectories':list(SELECTED),'sourceBranch':'codex/retention-integration','sourceCommit':'2bda894886937c589d9f1b28e2a23132bca3188b','sourceCopyFileCount':len(copy_manifest),'copiedRegularBytes':copied,'sourceCopyFiles':copy_manifest,'sourceCopyDirectories':directories,'allCopiedBytesModesAndDirectorySetsRecheckedAfterClassification':True,'originalSparseNativeTreesCopied':False,'originalSparseNativeTreesDeleted':False,'nativeArchives':'Closed gzip/tar only; original manifests bind full logical file bytes, modes and empty directories','noSshOrCloudOperations':True,'noTestsRerunForCopy':True,'localFreeBytesAfter':shutil.disk_usage(ROOT).free,'closedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat()}
with (DEST/'source-scope.json').open('x') as f:json.dump(scope,f,indent=2);f.write('\n')
readme='''# Isolated V3 integration validation

Source branch `codex/retention-integration`, commit `2bda894886937c589d9f1b28e2a23132bca3188b`, was privately pushed. Main was not merged by this operation.

`r1` preserves the failed forced run: two functional observation recorders attempted CREATE_NEW twice on the same open path. Both failures, original source, exact class/JAR inputs, XML/logs and all six native trees remain archived. `r2` preserves the bounded recorder fix and successful forced run: 291/291 tests, zero failures/errors/skips; 23/23 actionable tasks executed. All nine native completion receipts passed and stopped. PostgreSQL tests used a fresh dedicated local database, not the existing application schema.

Only already closed compressed native archives were copied here, never the roughly 25 GB of original sparse native trees. Every copied file SHA256, size and mode was checked against its frozen source, including directory closure. Existing archive manifests separately verify every logical archive byte, modes and empty directories. `r2/tested-source-commit-comparison.json` verifies all 239 tested materialized files against the pushed commit; only the integration validation document was added after testing.

The first known-marker inspection retained three complete PEM hits and stopped. They are the byte-exact, publicly published Netty 4.2.19.Final `SslUtils.PROBING_KEY` TLS capability fixture, inlined in three pinned library classes. Official tag sources, their hashes and exact constant/class comparisons are in `tool-validation/netty-public-probe-key-review`; the original three-hit review remains unchanged. Zero inspected hits remain unresolved or classified as user credentials. The first stop and final classified closure are separate receipts.

The review covers all entries of 77 unique JAR contents across 104 occurrences, exact source ZIPs, text/receipts/logs, classes and small native binary proofs. Native text/small proofs were inspected through their retained original paths after matching archive member hashes. Large Aeron recordings/mapped files were excluded from content-marker inspection, with exact paths/hashes/reasons retained; full archive readback and synthetic source/reference provenance are preserved. This is a bounded known-pattern review, not a general guarantee that arbitrary secrets cannot exist. No original PGDATA, SSH/private credential files, API secret files or host filesystem snapshots were selected. The only downloaded files are the explicitly pinned public Netty sources used to classify the three library fixtures.

This is local integration evidence. It does not establish independent-host throughput, external durability or any 100M result. The integrated artifact differs from frozen e3 used by the CPU chunk ABAB experiment. No deployment or default promotion occurred here. No tests were rerun for copying or credential classification.
'''
with (DEST/'README.md').open('x') as f:f.write(readme)
files={};dirs={}
for p in sorted(DEST.rglob('*')):
 assert not p.is_symlink();rel=str(p.relative_to(DEST))
 if p.is_dir():dirs[rel]={'mode':p.stat().st_mode&0o777}
 elif p.is_file():files[rel]={'bytes':p.stat().st_size,'sha256':sha(p),'mode':p.stat().st_mode&0o777}
 else:raise RuntimeError('Nonregular proof destination')
for rel,spec in copy_manifest.items():assert files[rel]==spec
inventory={'schemaVersion':1,'files':files,'directoriesIncludingEmpty':dirs,'totalRegularBytes':sum(v['bytes'] for v in files.values()),'inventorySelfAndCompletionExcluded':['proof-inventory.json','completion.json'],'allCopiedFileBytesModesDirectorySetsMatchFrozenSources':True}
with (DEST/'proof-inventory.json').open('x') as f:json.dump(inventory,f,indent=2);f.write('\n')
completion={'completedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':True,'proofInventorySha256':sha(DEST/'proof-inventory.json'),'credentialReviewSha256':sha(DEST/'credential-marker-review.json'),'credentialClassificationSha256':sha(DEST/'credential-marker-classification.json'),'sourceScopeSha256':sha(DEST/'source-scope.json'),'fileCountBeforeClosureMetadata':len(files),'regularBytesBeforeClosureMetadata':inventory['totalRegularBytes'],'sourceCopiedFiles':len(copy_manifest),'sourceCopiedBytes':copied,'knownMarkerHitsRetained':3,'reviewedPublicLibraryFixtureHits':3,'unresolvedHits':0,'userCredentialFindingsInInspectedScope':0,'uniqueJarsInspected':77,'jarOccurrencesCovered':104,'allCopiedFileBytesModesDirectorySetsMatchFrozenSources':True,'originalSparseNativeTreesCopied':False,'noTestsOrCloudOperations':True,'freeBytesAfter':shutil.disk_usage(ROOT).free}
with (DEST/'completion.json').open('x') as f:json.dump(completion,f,indent=2);f.write('\n')
print(json.dumps(completion,indent=2))
