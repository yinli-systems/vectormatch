from pathlib import Path
import shutil,hashlib,json,datetime,subprocess,stat
w=Path.cwd();src=w/'build/window-validation/native-r1';dest=w/'evidence/2026-10-24/runpod-cpu/retention-window-v3/local-validation-r1';assert not dest.exists();dest.mkdir(parents=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert json.loads((src/'execution.json').read_text())['exitCode']==0
archive=json.loads((src/'native-archive/manifest.json').read_text());assert archive['allFileBytesModesAndDirectoriesReadBack'] is True
for p in src.rglob('*'):assert not p.is_symlink()
shutil.copytree(src,dest/'native-r1',copy_function=shutil.copy2)
root=Path('/Users/kevin/Documents/ChatGPT/App 2');peer=root/'runtime/cloud/cpu-20261024/window-native-independent-r1/PASS.json';shutil.copy2(peer,dest/'root-independent-native-PASS.json');shutil.copy2(root/'runtime/cloud/cpu-20261024/audit-window-native-r1.py',dest/'root-audit-window-native-r1.py');shutil.copy2(w/'build/window-validation/archive-branch-proof.py',dest/'archive-branch-proof.py')
artifact=json.loads((src/'artifact-state/manifest.json').read_text());assert all(sha(w/n)==h for n,h in artifact['sourceSha256'].items())
source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip();changed=subprocess.check_output(['git','diff-tree','--no-commit-id','--name-only','-r',source_commit],text=True).splitlines()
receipt={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceCommit':source_commit,'baseCommit':subprocess.check_output(['git','rev-parse','HEAD^'],text=True).strip(),'changedSourceSha256':{n:sha(w/n) for n in changed},'nativeArtifactManifestSha256':sha(src/'artifact-state/manifest.json'),'allNativeCapturedSourcesStillExact':True,'postExecutionDocumentationOnly':'docs/RETENTION_READ_WINDOW_V3.md was added after successful tests/native; no Java changes after passing execution','nativeCodeFingerprint':'b148bbd416beca0c63ec10a2921a7709f1e82e8f3263604c930d5d901367117b','profileFingerprint':'732201775469861083f9dd0798a465dec1d0ed6bff39ed281dbef58c28b9fc68','nativeGzipSha256':archive['gzipSha256'],'nativeAll159FilesAnd26DirectoriesFullReadback':True,'unitProofOwnedSeparately':'evidence/2026-10-24/runpod-cpu/retention-window-v3/local-preparation-r1','unitAttempts':{},'rootIndependentReceiptSha256':sha(peer),'scope':'Synthetic local functional proof, one same-artifact read-window1/8 pair; no capacity, stable-rate, cloud, independent host or100M claim. No original sparse tree copied/deleted.'}
for name in ['units-r1','units-r2','units-r3']:
 p=w/'build/window-validation'/name
 receipt['unitAttempts'][name]={'registrationSha256':sha(p/'registration.json'),'executionSha256':sha(p/'execution.json'),'exitCode':json.loads((p/'execution.json').read_text())['exitCode'],'actualArtifactZipSha256':sha(p/'actual-classes-jars-results.zip')}
with (dest/'source-freeze.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
files={};dirs={}
for p in sorted(dest.rglob('*')):
 s=p.lstat();n=p.relative_to(dest).as_posix()
 if p.is_dir():dirs[n]={'mode':stat.S_IMODE(s.st_mode)}
 else:files[n]={'bytes':s.st_size,'mode':stat.S_IMODE(s.st_mode),'sha256':sha(p)}
# Every source copy's bytes and mode must match, including compressed native archive.
for n,entry in files.items():
 if n.startswith('native-r1/'):
  p=src/n[len('native-r1/'):];assert sha(p)==entry['sha256'] and stat.S_IMODE(p.stat().st_mode)==entry['mode']
inventory={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':files,'directories':dirs,'fileCount':len(files),'totalCopiedBytes':sum(v['bytes'] for v in files.values()),'copyBytesModesVerified':True,'originalSparseTreesRetained':True}
with (dest/'proof-inventory.json').open('x') as f:json.dump(inventory,f,indent=2);f.write('\n')
print(json.dumps({'destination':str(dest),'fileCount':len(files),'copiedBytes':inventory['totalCopiedBytes'],'inventorySha256':sha(dest/'proof-inventory.json'),'sourceFreezeSha256':sha(dest/'source-freeze.json'),'nativeGzipSha256':archive['gzipSha256']}))
