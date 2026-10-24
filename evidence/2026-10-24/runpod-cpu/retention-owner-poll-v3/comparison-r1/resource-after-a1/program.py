import pathlib,os,json,shutil,datetime,platform,subprocess,stat
assert platform.node()=="ed6c0673f5cb"
root=pathlib.Path("/opt/vectormatch-cpu")
rows=[]
for p in sorted(root.iterdir()):
 if p.is_symlink():continue
 r=subprocess.run(["du","-sk",str(p)],capture_output=True,text=True,timeout=25)
 assert r.returncode==0
 rows.append({"path":str(p),"allocatedKiB":int(r.stdout.split()[0])})
print(json.dumps({"atUtc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"disk":shutil.disk_usage(root)._asdict(),"topLevelAllocated":rows,"readOnly":True}))
