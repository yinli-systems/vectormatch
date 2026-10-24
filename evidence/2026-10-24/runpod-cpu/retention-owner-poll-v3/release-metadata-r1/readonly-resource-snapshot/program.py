import pathlib,shutil,socket,json,subprocess,datetime
assert socket.gethostname()=="ed6c0673f5cb"
p=pathlib.Path("/opt/vectormatch-cpu/preparation")
rows=[]
for d in sorted(p.iterdir()):
 if d.is_dir() and not d.is_symlink():
  r=subprocess.run(["du","-sk",str(d)],capture_output=True,text=True,timeout=15)
  assert r.returncode==0
  rows.append({"path":str(d),"allocatedKiB":int(r.stdout.split()[0])})
processes=[]
for q in pathlib.Path("/proc").iterdir():
 if q.name.isdigit():
  try:
   comm=(q/"comm").read_text().strip()
   if comm in ["java","postgres"]: processes.append({"pid":int(q.name),"comm":comm})
  except FileNotFoundError: pass
print(json.dumps({"atUTC":datetime.datetime.now(datetime.timezone.utc).isoformat(),"host":socket.gethostname(),"disk":dict(zip(["total","used","free"],shutil.disk_usage(p))),"shm":dict(zip(["total","used","free"],shutil.disk_usage("/dev/shm"))),"preparationAllocated":rows,"javaPostgresNamesOnly":processes,"readOnly":True}))
