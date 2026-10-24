import pathlib,json,hashlib,base64,stat,socket,shutil
assert socket.gethostname()=="ed6c0673f5cb"
root=pathlib.Path("/opt/vectormatch-cpu/preparation/owner-native-retirement-r1")
for p in [root]+list(root.parents):assert not p.is_symlink()
names=["REGISTRATION.json","BACKUP_AND_RESTORE_COMPLETE.json","RETIRE_INTENT.json","RETIRE_COMPLETE.json"]+["RESTORE_PROOF_"+str(n)+".json" for n in range(1,5)]
assert set(p.name for p in root.iterdir())==set(names)
rows={}
for name in names:
 p=root/name;s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<1024**2
 raw=p.read_bytes();rows[name]={"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"mode":stat.S_IMODE(s.st_mode),"uid":s.st_uid,"gid":s.st_gid,"rawBase64":base64.b64encode(raw).decode()}
c=json.loads((root/"REGISTRATION.json").read_text());retired=json.loads((root/"RETIRE_COMPLETE.json").read_text());assert retired["passed"]
assert retired["protectedBefore"]==retired["protectedAfter"]
for identity in c["allClosedProcessIdentities"]:assert not pathlib.Path("/proc",str(identity["pid"])).exists()
archives={}
for key,row in c["arms"].items():
 leaf=pathlib.Path(row["nativeLeaf"]);assert not leaf.exists() and not leaf.is_symlink()
 for archive in [leaf.parent/"pilot-after-clean-stop.tar.gz",pathlib.Path("/workspace/vectormatch-cpu-archives/owner-poll-native-retirement-20261024-r1")/("arm-"+key+".native.tar.gz")]:
  for p in [archive]+list(archive.parents):assert not p.is_symlink()
  s=archive.lstat();assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<256*1024**2
  h=hashlib.sha256()
  with archive.open("rb") as f:
   for data in iter(lambda:f.read(1024**2),b""):h.update(data)
  assert h.hexdigest()==row["nativeArchiveSha256"]
  archives[str(archive)]={"bytes":s.st_size,"sha256":h.hexdigest()}
print(json.dumps({"passed":True,"readOnly":True,"allFourRetiredLeavesStrictlyAbsent":True,"allTwentyPidsStrictlyAbsent":True,"eightCompressedArchiveBodiesStillExact":archives,"disk":shutil.disk_usage(root)._asdict(),"files":rows}))
