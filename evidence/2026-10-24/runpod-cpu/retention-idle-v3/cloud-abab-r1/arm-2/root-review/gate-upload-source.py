target='/opt/vectormatch-cpu/preparation/cpu-idle-cloud-abab-r1/release/arm-2-collection-gate.json'
text='{\n  "allRawInputsAndFailuresRetained": true,\n  "arm": 2,\n  "atUTC": "2026-10-24T08:28:12.858748+00:00",\n  "closedArchiveSha256": "c74f0b236c087cf4d53d91c925e559dc7f9435de2a4ebe00a98621a92df06fa3",\n  "closedNativeInventorySha256": "c013aa88c2a00852fe5cd6c4053fd3b347c841bb73a544b2d995385d61eb2a20",\n  "collectionComplete": true,\n  "controllerSha256": "07016602e61a9d415fdf968ada64c1ad6d40172926fd64ef44ab7c9dd124f98c",\n  "frozenReleaseSha256": "c2df0427bea0cdd8575ee3130adf4ff4aa43c65fca0a5458ed0c7c8c1eea4676",\n  "independentLocalCollectionReceiptSha256": "742980406c0ecab275ace59f6ceef1579b9212b8218528cec0d8e4a39b145de1",\n  "localFullMemberShaBytesModesOwnersEmptyDirsVerified": true,\n  "maximumParkNs": 100000,\n  "rootIndependentReviewSha256": "07ac600d5f3fed54883b24f1f22b20fe23faef5dd0e99838c8c0f03d9f067f1c",\n  "rootIndependentReviewSourceSha256": "069ba00caf54ccbd2c599bc46d267dca1e66a8179a4c575a8ad8d68b59d87c39",\n  "rootReviewedExactOwnedNativeRemoval": false,\n  "rootVerified": true,\n  "schemaVersion": 2,\n  "scope": "ROOT_VERIFIED_CLOSED_CPU_IDLE_ARM_COLLECTION",\n  "warningsRetained": 0\n}\n'
expected='353b5d0cee3754db758f3902beda163cbff434d4c58ae0bb4999fa1da90ddeaf'
import pathlib,hashlib,os,platform,json
assert platform.system()=='Linux' and platform.node()=='ed6c0673f5cb' and os.geteuid()==0
p=pathlib.Path(target)
for q in p.parents:assert q.is_dir() and not q.is_symlink()
b=text.encode();assert len(b)<65536 and hashlib.sha256(b).hexdigest()==expected
with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
print(json.dumps({'passed':True,'target':target,'sha256':expected,'bytes':len(b)}))
