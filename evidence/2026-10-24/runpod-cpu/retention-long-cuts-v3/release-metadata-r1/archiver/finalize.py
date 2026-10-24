from pathlib import Path
import datetime,hashlib,json,shutil,stat
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3]
DEST=ROOT/'evidence/2026-10-24/runpod-cpu/retention-long-cuts-v3/release-metadata-r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
assert json.loads((OUT/'COMPLETION.json').read_text())['exitCode']==1
assert json.loads((OUT/'COMPLETION_R2.json').read_text())['exitCode']==0
assert json.loads((DEST/'PAYLOAD_READY.json').read_text())['passed']
target=DEST/'archiver';target.mkdir(exist_ok=False)
names=['archive.py','REGISTRATION.json','stdout.txt','stderr.txt','COMPLETION.json','archive-r2.py','REGISTRATION_R2.json','stdout-r2.txt','stderr-r2.txt','COMPLETION_R2.json','finalize.py','REGISTRATION_FINALIZE.json']
for name in names:
 shutil.copy2(OUT/name,target/name);assert sha(OUT/name)==sha(target/name)
readme='''# Closed long-cut Linux release metadata evidence

This archive contains one completed metadata-only Linux JVM run using the already compiled helper and four exact JARs. The helper computed configuration/codec/Plan data and opened no driver, cluster, business RPC or benchmark. Its Java process65224/start4003060 was observed with exact argvSHA7f9002c7f8d6b54accf32bfc684fdd1ed6c38c38c6657e49c08c2b0a2c20e2ed and canonical JDK executable, then exited. The root identity review independently rejected an observation-gap interpretation. JDK executable9cad3f… and releasef83f6d… match before/after. All six staged source/class/JAR inputs remained unchanged.

Linux observation78bb2a6a46acfadde6888184caf507da934c2d22b1a532116c7d94a488795c27 and receiptf136046368c57d2998b50854e2b46e5dba3ebfbc639b66ef7cd87476d5824b5f are preserved byte-for-byte. The archive independently joins receipt observationSHA to the actual bytes and ownedParentPid to the observed identity. It reconstructs fingerprint6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8 from the four actual anchor JAR byte streams, checks all five reported class-source bindings, and verifies every regular member of the six-input gzip TAR without extraction. MatchingEngine comes from core; DirectBuffer comes from aeron-all, rather than the separate Agrona JAR.

The long Plan is prospective:33792 arrivals/500per second/67.584seconds,12maximum cycles,7243logical maintenance RPCs,185514924B raw trace and757122377B allocated growth. It is not a new workload or capacity result. Release readiness remainsfalse; source/controller/raw-proof/root freeze work proceeds separately.

Historical closed guard attempts retain17 and19 passing pure tests, complete registration/source ZIPs/stdout/stderr. Their ZIPs contain immutable historical controller/draft input snapshots for those executions; those are not a final controller release. No mutable active controller/template/proof draft was copied into the metadata payload. Full source-registered ZIP membership/SHA closure was checked.

The first local archiver attempt failed because its strict allowlist omitted root execution stdout.log/stderr.log (ignored by the initial file search). Its exact source, registration and failure logs are retained in archiver/. The second version explicitly included both logs and rehashed the already copied metadata before continuing, without overwriting or deleting it. Both source/copy file SHA/size/mode/uid/gid and all directory/empty-directory closure were checked. This archival work executed no additional Java, SSH, Git, native workload or original application/PG read. The actual earlier metadata execution remains explicitly evidenced in metadata/ and root-execution/.

Known high-confidence credential markers were scanned across all copied bytes, source/helper/stdout, every JAR entry, the nested input TAR and closed guard ZIP contents. Zero unresolved findings is a bounded marker-review result, not a universal secret-absence guarantee. No keys, environments, PG or original/local long-native trees were collected.

MANIFEST.json covers every file and directory except itself and CLOSED.json. All runtime originals remain retained and unchanged. Root owns review, commit and push.
'''
(DEST/'README.md').write_text(readme)
files={};dirs={}
for p in [DEST,*sorted(DEST.rglob('*'))]:
 st=p.lstat();rel='.' if p==DEST else p.relative_to(DEST).as_posix();assert not p.is_symlink()
 row=dict(mode=stat.S_IMODE(st.st_mode),uid=st.st_uid,gid=st.st_gid)
 if stat.S_ISDIR(st.st_mode):dirs[rel]=row
 else:
  assert stat.S_ISREG(st.st_mode);files[rel]=dict(**row,bytes=st.st_size,sha256=sha(p))
manifest=dict(files=files,directories=dirs,excludes=['MANIFEST.json','CLOSED.json'],fileCount=len(files),directoryCount=len(dirs),logicalBytes=sum(r['bytes'] for r in files.values()),scope='All closed payload/source/guard/root-execution/archive-attempt bytes and local modes/owners; no active controller draft')
save(DEST/'MANIFEST.json',manifest)
closed=dict(passed=True,manifestSha256=sha(DEST/'MANIFEST.json'),fileCountBeforeManifestAndClosed=len(files),directoryCount=len(dirs),logicalBytesBeforeManifestAndClosed=manifest['logicalBytes'],allCopiedInputsFullShaModeOwnerDirectoryClosureVerified=True,nestedSixInputTarFullyVerified=True,actualLinuxObservationSha256=sha(DEST/'metadata/actual-linux-distribution-observation.json'),actualLinuxReceiptSha256=sha(DEST/'metadata/remote-receipt.json'),actualRootIdentityReviewSha256=sha(DEST/'root-execution/ROOT_IDENTITY_REVIEW.json'),guardTestsHistorical=[17,19],firstArchiverFailureRetained=True,releaseReady=False,benchmarkStarted=False,cpuFunctionalOrPerformanceProven=False,originalsRetained=True,sourceCopyClosureSha256=sha(DEST/'source-copy-closure.json'),markerReviewSha256=sha(DEST/'known-marker-review.json'),nestedIdentityReviewSha256=sha(DEST/'nested-and-identity-review.json'),completedAtUTC=datetime.datetime.now(datetime.timezone.utc).isoformat())
save(DEST/'CLOSED.json',closed)
assert {p.relative_to(DEST).as_posix() for p in DEST.rglob('*') if p.is_file()}==set(files)|{'MANIFEST.json','CLOSED.json'}
for rel,row in files.items():
 p=DEST/rel;s=p.stat();assert (s.st_size,sha(p),stat.S_IMODE(s.st_mode),s.st_uid,s.st_gid)==(row['bytes'],row['sha256'],row['mode'],row['uid'],row['gid'])
print(json.dumps(dict(destination=str(DEST),closedSha256=sha(DEST/'CLOSED.json'),manifestSha256=sha(DEST/'MANIFEST.json'),fileCount=closed['fileCountBeforeManifestAndClosed']+2,directoryCount=len(dirs),bytes=manifest['logicalBytes']+(DEST/'MANIFEST.json').stat().st_size+(DEST/'CLOSED.json').stat().st_size,freeBytes=shutil.disk_usage(ROOT).free)))
