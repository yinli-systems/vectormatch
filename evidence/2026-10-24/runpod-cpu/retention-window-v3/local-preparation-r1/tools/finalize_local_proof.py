#!/usr/bin/env python3
"""Finish the new offline proof without modifying archived inputs or their reports."""
from pathlib import Path
import ast, datetime, hashlib, json, os, re, shutil, stat, zipfile

WORK=Path('/Users/kevin/Documents/ChatGPT/App 2')
OWN=WORK/'runtime/cloud/cpu-20261024/window-local-proof-archive-r1'
DEST=WORK/'evidence/2026-10-24/runpod-cpu/retention-window-v3/local-preparation-r1'
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):assert p.is_file() and not p.is_symlink();return p.read_bytes()
def js(p):return json.loads(read(p))
def write(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n')

scan=js(DEST/'CREDENTIAL_MARKER_REVIEW.json')
assert len(scan['hits'])==3
resolved=[];source_sha=None;literal_sha=None
pattern=re.compile(rb'(?i)(?:postgres(?:ql)?|mysql)://[^/\s:@]+:[^@\s]+@')
for hit in scan['hits']:
    archive,member=hit['path'].split('!/',1)
    assert hit['kind']=='credential-dsn' and member=='deploy/test_remote_service.py' and hit['count']==1
    with zipfile.ZipFile(DEST/archive) as z:b=z.read(member)
    tree=ast.parse(b.decode());function=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='test_configuration_fingerprint_excludes_credentials_and_jdbc_urls')
    lines=b.splitlines(keepends=True);lo=sum(map(len,lines[:function.lineno-1]));hi=sum(map(len,lines[:function.end_lineno]))
    match=pattern.search(b);assert match and lo<=match.start()<match.end()<=hi
    assert b'VM_PG_PASSWORD' in b[lo:hi] and b'OTHER_API_TOKEN' in b[lo:hi] and b'patch.object' in b[lo:hi]
    source_sha=source_sha or sha(b);literal_sha=literal_sha or sha(match.group());assert source_sha==sha(b) and literal_sha==sha(match.group())
    resolved.append({**hit,'sourceSha256':sha(b),'matchedLiteralSha256':sha(match.group()),'classification':'Synthetic credential-DSN literal inside the configuration-fingerprint credential-exclusion unit test; no runtime credential value.','testFunction':function.name})
write(DEST/'MANUAL_CREDENTIAL_REVIEW.json',{'passed':True,'rawScanSha256':sha(read(DEST/'CREDENTIAL_MARKER_REVIEW.json')),'rawScannerHitsPreserved':True,'resolvedHits':resolved,'unresolvedHits':0,'scope':'Known-marker review and source context classification only; not a general secret-detection guarantee. No original PG/key/env files were selected.'})

for name in ('REGISTRATION.json','COMPLETION.json'):
    target=DEST/'tools'/('archive-'+name.lower());shutil.copy2(OWN/name,target)
shutil.copy2(Path(__file__),DEST/'tools/finalize_local_proof.py')
write(OWN/'EXECUTION_OBSERVATION.json',{'observedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':['python3','-I','-S','runtime/cloud/cpu-20261024/window-local-proof-archive-r1/archive_local_proof.py'],'scriptSha256':sha(read(OWN/'archive_local_proof.py')),'completionSha256':sha(read(OWN/'COMPLETION.json')),'completionWrittenAfterAllAssertions':True,'separateOsExitStatusCaptured':False,'stdoutStderrCapture':'Initial tool call yielded while running; wrapper emitted only current output, not its session identifier. The independently readable completion and all assertion reports are retained. No rerun was performed.','scope':'Archive process observation, not Java/native/cloud execution.'})
shutil.copy2(OWN/'EXECUTION_OBSERVATION.json',DEST/'tools/archive-execution-observation.json')

v=js(DEST/'VALIDATION.json')
text='''# Read-window V3: closed local preparation evidence

This proof preserves the exact three closed focused Java build/test attempts, the completed actual-JAR metadata helper, and the frozen Python cloud preparation. It contains no native benchmark result, throughput or p99 measurement, cloud execution, original PostgreSQL data directory, SSH key, or environment file. The native attempt running during collection was excluded.

The `units/` directories contain the original registrations, source ZIPs, commands, classpath captures, logs, execution receipts and full generated artifact ZIPs. Independent parsing counted actual XML testcase elements and reconciled their suite totals:

| Attempt | Actual tests | Passed | Failed | Errors/skips | Gradle exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| units-r1 | 133 | 120 | 13 | 0 / 0 | 1 |
| units-r2 | 133 | 131 | 2 | 0 / 0 | 1 |
| units-r3 | 133 | 133 | 0 | 0 / 0 | 0 |

The first attempt retained eleven failures from a prospective codec probe whose event/export counters disagreed, plus two invalid error-reply guard fixtures. The second retained an incorrect test expectation that a prospective 350,000-arrival envelope must be admitted despite its 2.5GiB allocation rejection, and an exception-type assertion inconsistent with a failed owner. The third fixed those test expectations without changing production source from r2. Exact failed cases and source changes are in `VALIDATION.json`; these failed attempts were preserved in full. All six coordinator tests executed and passed in every attempt. The final run is focused validation (one core legacy golden test and 132 nonnative retention cluster tests), not a full-project or native run.

For every attempt, source ZIP membership and every file SHA matched its registration; every generated artifact ZIP member matched bytes, SHA and mode in its capture manifest. Both test classpath inventories were bound to those captured bytes. The classpath capture sorts member paths and does not attest runtime class-load order. r1 and r2 produced no captured installed distribution JARs after their test failures. In r3, all 171 main cluster classes and 41 main core classes exactly match their installed JAR entries. Configured test-class directories and generated distribution JARs remain distinct evidence.

`release-observation/` preserves the helper source, class, all four input JARs, pinned input metadata, javac/java commands and successful execution receipts. The extra `root-helper-source/` copy was byte-identical to the executed helper source. Independent Python recomputation of the helper's four actual loaded anchor sources yields `b148bbd416beca0c63ec10a2921a7709f1e82e8f3263604c930d5d901367117b`. The two Agrona/MediaDriver anchor observations both loaded from `aeron-all`; the separately included Agrona JAR is not claimed as the actual DirectBuffer source. Final core/cluster helper JARs match r3's installed JARs. JDK executable/release pins were rehashed and matched at archive time; the complete JDK and process class-load trace are not archived.

The helper computed admitted prospective bounds for the fixed 6,400-arrival, cap4/chunk6144/fetch16 windows 1 and 8. Their operational envelopes match after removing only `requestedReadWindow`; both reserve a maximum of eight read slots. Its 6,727-byte shape fixture, the plan's conservative 6,791-byte largest reply allowance, and the generic codec maximum 6,919 bytes are different bounds. None is an observed network reply. The helper starts no driver/cluster; these observations prove no stable capacity or latency SLA, and no completed 350,000- or 100M-arrival workload.

`cloud-preparation/` includes exactly all 16 frozen stageable files, both local historical adaptation sources, the frozen manifest, and every file from Python guard attempts 02–06. Attempts 02/03 failed (103 tests with five errors / 107 tests with one error); 04 passed 120, and 05/06 passed 122 tests. Attempt 01 has only the original manifest's historical tool-transcript summary of 17 tests, not a newly invented execution archive. No compiled `__pycache__` was copied. The preserved manifest explicitly remains a draft release requiring the separate actual native, Linux, protected-state and cloud gates; this archive does not promote it to ready.

`COPY_BINDINGS.json` binds all 87 copied input files (37,613,447 logical bytes) plus every copied directory and empty directory, preserving mode/uid/gid. Input states were rehashed after copying and remained unchanged. `NESTED_ARCHIVE_INVENTORIES.json` records full member SHA/bytes/modes, explicit directories and CRC reads for every ZIP/JAR recursively. ZIP member uid/gid are unavailable and are not fabricated. No sparse native tree was extracted.

The bounded marker scan read 18,691 outer/member inputs, totaling 162,279,177 bytes. Its three hits are the same synthetic DSN literal inside the credential-exclusion test, present in each source ZIP. The raw findings remain in `CREDENTIAL_MARKER_REVIEW.json`; `MANUAL_CREDENTIAL_REVIEW.json` resolves them by exact source/function/literal hash, without hiding or rewriting the original evidence. This is a known-marker review, not a universal proof of secret absence.

The collection and finishing scripts and their metadata are under `tools/`. The first collection tool wrapper did not retain the asynchronous process session identifier, so a separate OS exit-code receipt is unavailable; its completion file was written only after all validation assertions. No archive rerun, Java, Git, SSH, SQL, cloud, or source-build mutation was performed by this archive task. The final local inventory covers every other proof file and all directories; its own SHA is reported to the parent reviewer.
'''
with (DEST/'README.md').open('x') as f:f.write(text)

# New generated summaries/tools add no external values; scan their outer bytes too.
fresh=[]
for p in sorted(DEST.rglob('*')):
    if p.is_file() and p.relative_to(DEST).parts[0] not in ('units','release-observation','root-helper-source','cloud-preparation'):
        b=read(p)
        for kind,pat in [('private-key-header',rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED) PRIVATE KEY-----'),('github-token',rb'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b'),('aws-access-key-id',rb'\bAKIA[A-Z0-9]{16}\b'),('runpod-token',rb'\b(?:rpa|rp)_[A-Za-z0-9]{30,}\b'),('credential-dsn',pattern.pattern)]:
            assert not re.search(pat,b), 'new generated credential marker: '+str(p)
        fresh.append({'path':p.relative_to(DEST).as_posix(),'bytes':len(b),'sha256':sha(b)})
write(DEST/'GENERATED_FILES_MARKER_REVIEW.json',{'passed':True,'files':fresh,'scope':'Known markers in generated summaries/tools; nested copied inputs were separately fully scanned and three fixture findings resolved.'})

inventory={}
for p in [DEST]+sorted(DEST.rglob('*')):
    s=p.lstat();assert stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode)
    row={'type':'directory' if stat.S_ISDIR(s.st_mode) else 'file','mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
    if row['type']=='file':b=read(p);row.update(bytes=len(b),sha256=sha(b))
    inventory['.' if p==DEST else p.relative_to(DEST).as_posix()]=row
assert 'FINAL_LOCAL_INVENTORY.json' not in inventory
final={'schema':'local-full-sha-mode-owner-directory-closure-v1','selfExcluded':True,'paths':inventory,'files':sum(s['type']=='file' for s in inventory.values()),'directoriesIncludingRoot':sum(s['type']=='directory' for s in inventory.values()),'logicalBytes':sum(s.get('bytes',0) for s in inventory.values()),'freeBytesAtCompletion':shutil.disk_usage(WORK).free,'noNativeTreeIncluded':True}
write(DEST/'FINAL_LOCAL_INVENTORY.json',final)
out={'passed':True,'proof':str(DEST),'inventorySha256':sha(read(DEST/'FINAL_LOCAL_INVENTORY.json')),'otherFiles':final['files'],'directoriesIncludingRoot':final['directoriesIncludingRoot'],'otherLogicalBytes':final['logicalBytes'],'totalProofLogicalBytes':final['logicalBytes']+(DEST/'FINAL_LOCAL_INVENTORY.json').stat().st_size,'freeBytes':shutil.disk_usage(WORK).free,'validationSha256':sha(read(DEST/'VALIDATION.json')),'manualCredentialReviewSha256':sha(read(DEST/'MANUAL_CREDENTIAL_REVIEW.json')),'readmeSha256':sha(read(DEST/'README.md'))}
write(OWN/'FINAL_COMPLETION.json',out);print(json.dumps(out,sort_keys=True))
