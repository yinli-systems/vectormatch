import pathlib,json,hashlib,base64,stat,socket
assert socket.gethostname()=="ed6c0673f5cb"
root=pathlib.Path("/opt/vectormatch-cpu/preparation/owner-native-retirement-r1")
for p in [root]+list(root.parents):assert not p.is_symlink()
names=["REGISTRATION.json","BACKUP_AND_RESTORE_COMPLETE.json"]+["RESTORE_PROOF_"+str(n)+".json" for n in range(1,5)]
assert set(p.name for p in root.iterdir())==set(names)
rows={}
for name in names:
 p=root/name;s=p.lstat();assert stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size<1024**2
 raw=p.read_bytes();rows[name]={"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"mode":stat.S_IMODE(s.st_mode),"uid":s.st_uid,"gid":s.st_gid,"rawBase64":base64.b64encode(raw).decode()}
print(json.dumps({"passed":True,"readOnly":True,"files":rows}))
