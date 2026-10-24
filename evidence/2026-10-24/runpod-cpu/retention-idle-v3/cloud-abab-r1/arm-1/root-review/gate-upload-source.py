target='/opt/vectormatch-cpu/preparation/cpu-idle-cloud-abab-r1/release/arm-1-collection-gate.json'
text='{\n  "allRawInputsAndFailuresRetained": true,\n  "arm": 1,\n  "atUTC": "2026-10-24T08:24:47.792855+00:00",\n  "closedArchiveSha256": "3485a1bc42a1c96582bfeb41e2aec7a7a3bae7d56465128a00803db3f264a059",\n  "closedNativeInventorySha256": "e331023305d17bc42c08784bc698fa2aeeacb0adaf4ebc5dc4b76555f623046b",\n  "collectionComplete": true,\n  "controllerSha256": "07016602e61a9d415fdf968ada64c1ad6d40172926fd64ef44ab7c9dd124f98c",\n  "frozenReleaseSha256": "c2df0427bea0cdd8575ee3130adf4ff4aa43c65fca0a5458ed0c7c8c1eea4676",\n  "independentLocalCollectionReceiptSha256": "4247bf823f620db350b729a28ea7821a2c916034e163a21907aaa406ef0a69cc",\n  "localFullMemberShaBytesModesOwnersEmptyDirsVerified": true,\n  "maximumParkNs": 1000000,\n  "rootIndependentReviewSha256": "1e4f3333d3fd39494d668a326deae8376dc46e2527f531f3b90e41d399a45929",\n  "rootIndependentReviewSourceSha256": "069ba00caf54ccbd2c599bc46d267dca1e66a8179a4c575a8ad8d68b59d87c39",\n  "rootReviewedExactOwnedNativeRemoval": false,\n  "rootVerified": true,\n  "schemaVersion": 2,\n  "scope": "ROOT_VERIFIED_CLOSED_CPU_IDLE_ARM_COLLECTION",\n  "warningsRetained": 0\n}\n'
expected='f60593c37f3ae23e1368ba8b7d04882738979c654c6d965465f6bcd471019181'
import pathlib,hashlib,os,platform,json
assert platform.system()=='Linux' and platform.node()=='ed6c0673f5cb' and os.geteuid()==0
p=pathlib.Path(target)
for q in p.parents:assert q.is_dir() and not q.is_symlink()
b=text.encode();assert len(b)<65536 and hashlib.sha256(b).hexdigest()==expected
with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
print(json.dumps({'passed':True,'target':target,'sha256':expected,'bytes':len(b)}))
