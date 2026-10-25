from pathlib import Path
import json,hashlib,subprocess,stat,datetime,os
R=Path.cwd();B=R/"runtime/cloud/cpu-20261024"
def sha(p):
 h=hashlib.sha256()
 with p.open("rb")as f:
  for block in iter(lambda:f.read(1024**2),b""):h.update(block)
 return h.hexdigest()
def git(*a):return subprocess.check_output(["git",*a])
rows=[]
for arm in (1,2):
 A=R/f"evidence/2026-10-24/runpod-cpu/retention-dispatch-fairness-v3/cloud-arm-{arm}-r1"
 proof=json.loads((B/f"dispatch-fairness-arm-{arm}-private-proof-r1/PRIVATE_PUSH.json").read_text())
 inv=json.loads((A/"INVENTORY.json").read_text());large=json.loads((A/"ORIGINAL_LARGE_FILES.json").read_text())["files"]
 assert proof["passed"]and proof["private"]and proof["allOriginalNativeAndRawEvidencePushed"]and proof["archiveInventorySha256"]==sha(A/"INVENTORY.json")
 remote=git("ls-remote","origin","refs/heads/codex/dispatch-fairness-v3").decode().split()[0]
 subprocess.run(["git","merge-base","--is-ancestor",proof["commit"],remote],check=True)
 sources=json.loads((A/"SOURCE_MIRRORS.json").read_text())["sources"]
 names=[n for n in large if n=="collection/full-original-closed-round.tar.gz"or (n.startswith("root-review/")and not n.endswith("arrivals.csv"))]
 assert names
 for n in names:
  scope,relative=n.split("/",1);target=B/sources[scope]/relative;record=large[n];s=target.stat()
  assert not target.is_symlink()and s.st_size==record["bytes"]and sha(target)==record["sha256"]and stat.S_IMODE(s.st_mode)==record["mode"]and s.st_uid==record["uid"]and s.st_gid==record["gid"]
  paths=["INVENTORY.json","ORIGINAL_LARGE_FILES.json","SOURCE_MIRRORS.json"]+[part["path"]for part in record["parts"]]
  whole=hashlib.sha256();offset=0
  for part in record["parts"]:
   p=A/part["path"];pin=inv["files"][part["path"]];assert part["offset"]==offset and p.stat().st_size==part["bytes"]==pin["bytes"]and sha(p)==part["sha256"]==pin["sha256"]
   with p.open("rb")as f:
    for block in iter(lambda:f.read(1024**2),b""):whole.update(block)
   offset+=part["bytes"]
  assert offset==record["bytes"]and whole.hexdigest()==record["sha256"]
  for part in paths:
   p=A/part;rel=p.relative_to(R).as_posix();entry=git("ls-tree",proof["commit"],"--",rel).decode().split()
   assert len(entry)>=4 and entry[2]==git("hash-object","--",rel).decode().strip()
  rows.append(dict(target=str(target),bytes=record["bytes"],sha256=record["sha256"],restoreArchive=str(A),restoreOriginalPath=n,privateCommit=proof["commit"],remoteAncestorVerified=remote))
assert len(rows)==12
# Every source and lossless committed reconstruction was checked before any unlink.
receipt=dict(passed=True,verifiedAtUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope="Verified redundant runtime copies only; complete private archives and remote native originals unchanged",files=rows)
print(json.dumps(receipt),flush=True)
for row in rows:
 p=Path(row["target"]);assert p.stat().st_size==row["bytes"]and sha(p)==row["sha256"];p.unlink()
O=B/"verified-local-duplicate-retirement-r2";O.mkdir()
receipt["completedAtUTC"]=datetime.datetime.now(datetime.timezone.utc).isoformat();receipt["retiredLogicalBytes"]=sum(r["bytes"]for r in rows)
(O/"RETIREMENT.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
print(json.dumps(dict(passed=True,retiredFiles=len(rows),retiredLogicalBytes=receipt["retiredLogicalBytes"])),flush=True)
