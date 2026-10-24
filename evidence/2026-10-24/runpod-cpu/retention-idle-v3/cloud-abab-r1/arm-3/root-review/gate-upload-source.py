target='/opt/vectormatch-cpu/preparation/cpu-idle-cloud-abab-r1/release/arm-3-collection-gate.json'
text='{\n  "allRawInputsAndFailuresRetained": true,\n  "arm": 3,\n  "atUTC": "2026-10-24T08:31:20.167028+00:00",\n  "closedArchiveSha256": "ebdc5b7117a7a6c406c264735c5c5620d1cdb3902068bd73e50649deb5a09705",\n  "closedNativeInventorySha256": "100db8ef753c8c16ef0c69244eae54a362e4f2f8f26ec13afc0ae7d392ef9e4a",\n  "collectionComplete": true,\n  "controllerSha256": "07016602e61a9d415fdf968ada64c1ad6d40172926fd64ef44ab7c9dd124f98c",\n  "frozenReleaseSha256": "c2df0427bea0cdd8575ee3130adf4ff4aa43c65fca0a5458ed0c7c8c1eea4676",\n  "independentLocalCollectionReceiptSha256": "be65ce8f4cb4966954557e1f031229d7acb499d8592433e1091640784ba4869f",\n  "localFullMemberShaBytesModesOwnersEmptyDirsVerified": true,\n  "maximumParkNs": 1000000,\n  "rootIndependentReviewSha256": "b840322c62f6d0238f171df807f328781c056a8b35f9386326f0b2a7cdcde378",\n  "rootIndependentReviewSourceSha256": "069ba00caf54ccbd2c599bc46d267dca1e66a8179a4c575a8ad8d68b59d87c39",\n  "rootReviewedExactOwnedNativeRemoval": false,\n  "rootVerified": true,\n  "schemaVersion": 2,\n  "scope": "ROOT_VERIFIED_CLOSED_CPU_IDLE_ARM_COLLECTION",\n  "warningsRetained": 0\n}\n'
expected='e0645774d701e859df39338c9c3088089f172ce14e3e9c8bf3ad906e06a56a3e'
import pathlib,hashlib,os,platform,json
assert platform.system()=='Linux' and platform.node()=='ed6c0673f5cb' and os.geteuid()==0
p=pathlib.Path(target)
for q in p.parents:assert q.is_dir() and not q.is_symlink()
b=text.encode();assert len(b)<65536 and hashlib.sha256(b).hexdigest()==expected
with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
print(json.dumps({'passed':True,'target':target,'sha256':expected,'bytes':len(b)}))
