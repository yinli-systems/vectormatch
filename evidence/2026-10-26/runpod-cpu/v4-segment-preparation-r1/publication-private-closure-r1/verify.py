from pathlib import Path
import json,subprocess,sys,tarfile,hashlib,datetime,os,time
B=Path(__file__).resolve().parent.parent;W=B/'interbank-v4-worktree';A=W/'evidence/2026-10-26/runpod-cpu/v4-segment-preparation-r1/comparison-r1';O=B/'v4-segment-comparison-private-proof-r1';assert not O.exists()
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import tree,sha,verify
git=lambda *a:subprocess.check_output(['git','-C',str(W),*a]);head=git('rev-parse','HEAD').decode().strip();assert git('ls-remote','origin','refs/heads/codex/v4-segment-preparation').decode().split()[0]==head
O.mkdir()
def api(path):
 for attempt in range(1,4):
  r=subprocess.run(['gh','api',path],capture_output=True,text=True,timeout=30,env={**os.environ,'GODEBUG':'http2client=0'})
  if r.returncode==0:return json.loads(r.stdout)
  (O/('metadata-error-'+str(attempt)+'-'+hashlib.sha256(path.encode()).hexdigest()[:12]+'.txt')).write_text(r.stderr)
  assert any(s in r.stderr for s in ['connect: connection refused','TLS handshake timeout','i/o timeout','connection reset','unexpected EOF'])and attempt<3,'metadata GET failed;no native retry'
  time.sleep(attempt)
repo='yinli-systems/vectormatch';assert api('repos/'+repo)['private']
closed=json.loads((A/'CLOSED.json').read_text());inv=json.loads((A/'INVENTORY.json').read_text());actual=tree(A);assert closed['passed']and closed['inventorySha256']==sha(A/'INVENTORY.json')and set(actual['files'])==set(inv['files'])|{'INVENTORY.json','CLOSED.json'}and actual['directories']==inv['directories']and all(actual['files'][n]==p for n,p in inv['files'].items())
prefix=A.relative_to(W).as_posix()
for n,pin in actual['files'].items():
 b=git('show',head+':'+prefix+'/'+n);assert len(b)==pin['bytes']and hashlib.sha256(b).hexdigest()==pin['sha256']
archive=A/'complete-comparison-reporting-and-private-proofs.tar.gz';assert archive.stat().st_size==closed['archiveBytes']and sha(archive)==closed['archiveSha256'];assert verify(archive,json.loads((A/'ORIGINAL_SCOPE_INVENTORIES.json').read_text()))==closed['everyOriginalMemberVerified']
r=json.loads((A/'RESULT.json').read_text());refs=json.loads((A/'PRIVATE_POINT_REFERENCES.json').read_text());assert r['allFourRawPrivatelyVerified']and r['allFourSafetyAndCorrectnessGatesPassed']and r['onlyRegisteredFactorChanged']
for arm,p in refs.items():
 assert p['passed']and p['completeAuthenticatedAssetDownloadVerified']and p['artifactFingerprint']==r['artifactFingerprint'];asset=api('repos/'+repo+'/releases/assets/'+str(p['assetId']));assert asset['state']=='uploaded'and asset['size']==p['assetBytes']and asset['digest']=='sha256:'+p['assetSha256']
with tarfile.open(archive)as t:before=json.load(t.extractfile('original/v4-segment-reporting-r1/index-before.json'))
index=json.loads((A/'published/index.json').read_text());assert len(index['runs'])==125 and len(index['capacityCohorts'])==46 and index['runs'][:120]==before['runs']and index['capacityCohorts'][:44]==before['capacityCohorts']and index['capacity']==before['capacity']
for path,n in [('evidence/index.json','index.json'),('README.md','README.md')]+[('docs/'+n,n)for n in ['V4_SEGMENT_PREPARATION_RESULTS.md','PRODUCTION_CORRECTNESS_RESULTS.md','PRODUCTION_ACCEPTANCE.md','V4_FORCE_MATERIALIZATION_RESULTS.md']]:assert git('show',head+':'+path)==(A/'published'/n).read_bytes()
proof=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),private=True,commit=head,allFourRawPrivatelyVerified=True,allFourSafetyAndCorrectnessGatesPassed=True,allEvidenceGitBlobsVerified=len(actual['files']),completeComparisonArchiveMembersVerified=closed['everyOriginalMemberVerified'],publishedIndexAndAllSixReportBodiesVerified=True,all120PriorRunsAnd44CohortsUnchanged=True,runs=125,cohorts=46,registeredBothPairsPassed=r['registeredBothPairsPassed'],defaultPromoted=False)
(O/'PRIVATE_PUSH.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n');print(json.dumps(proof))
