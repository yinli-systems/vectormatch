from pathlib import Path
import json,subprocess,sys,tarfile,hashlib,datetime
B=Path(__file__).resolve().parent.parent;W=B/'interbank-v4-worktree';A=W/'evidence/2026-10-26/runpod-cpu/v4-batch-coalescing-r1/comparison-r1';O=B/'v4-batch-coalescing-comparison-private-proof-r1';assert not O.exists()
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import tree,verify,sha
git=lambda *a:subprocess.check_output(['git','-C',str(W),*a]);head=git('rev-parse','HEAD').decode().strip();assert git('ls-remote','origin','refs/heads/codex/v4-batch-coalescing').decode().split()[0]==head
api=lambda p:json.loads(subprocess.check_output(['gh','api',p]));repo='yinli-systems/vectormatch';assert api('repos/'+repo)['private']
closed=json.loads((A/'CLOSED.json').read_text());inv=json.loads((A/'INVENTORY.json').read_text());actual=tree(A);assert closed['passed']and closed['inventorySha256']==sha(A/'INVENTORY.json')and set(actual['files'])==set(inv['files'])|{'INVENTORY.json','CLOSED.json'}and actual['directories']==inv['directories']and all(actual['files'][n]==p for n,p in inv['files'].items())
prefix=A.relative_to(W).as_posix()
for n,pin in actual['files'].items():
 body=git('show',head+':'+prefix+'/'+n);assert len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256']
archive=A/'complete-comparison-reporting-and-private-proofs.tar.gz';assert archive.stat().st_size==closed['archiveBytes']and sha(archive)==closed['archiveSha256'];assert verify(archive,json.loads((A/'ORIGINAL_SCOPE_INVENTORIES.json').read_text()))==closed['everyOriginalMemberVerified']
r=json.loads((A/'RESULT.json').read_text());refs=json.loads((A/'PRIVATE_POINT_REFERENCES.json').read_text());assert r['allFourRawPrivatelyVerified']and r['allFourSafetyAndCorrectnessGatesPassed']and r['onlyRegisteredFactorChanged']
for arm,p in refs.items():
 assert p['passed']and p['completeAuthenticatedAssetDownloadVerified']and p['artifactFingerprint']==r['artifactFingerprint'];asset=api('repos/'+repo+'/releases/assets/'+str(p['assetId']));assert asset['state']=='uploaded'and asset['size']==p['assetBytes']and asset['digest']=='sha256:'+p['assetSha256']
 before=json.loads((B/'v4-batch-coalescing-reporting-r1/index-before.json').read_text());index=json.loads((A/'published/index.json').read_text());assert len(index['runs'])==118 and len(index['capacityCohorts'])==44 and index['runs'][:113]==before['runs']and index['capacityCohorts'][:42]==before['capacityCohorts']and index['capacity']==before['capacity']
assert git('show',head+':evidence/index.json')==(A/'published/index.json').read_bytes()
assert git('show',head+':docs/BATCH_COALESCING_RESULTS_V4.md')==(A/'published/BATCH_COALESCING_RESULTS_V4.md').read_bytes()
O.mkdir();proof=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),private=True,commit=head,allFourRawPrivatelyVerified=True,allFourSafetyAndCorrectnessGatesPassed=True,allEvidenceGitBlobsVerified=len(actual['files']),completeComparisonArchiveMembersVerified=closed['everyOriginalMemberVerified'],publishedIndexAndReportBodiesVerified=True,all113PriorRunsAnd42CohortsUnchanged=True,runs=118,cohorts=44,registeredBothPairsPassed=r['registeredBothPairsPassed'],defaultPromoted=False)
(O/'PRIVATE_PUSH.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n');print(json.dumps(proof))
