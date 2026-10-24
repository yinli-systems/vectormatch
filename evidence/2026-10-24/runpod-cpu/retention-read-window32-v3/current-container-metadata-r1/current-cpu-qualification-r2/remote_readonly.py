from pathlib import Path
import os,socket,platform,json,hashlib,shutil,subprocess,time
assert socket.gethostname()=="33ace3d92505"
root=Path("/opt/vectormatch-cpu")
java=root/"tools/jdk-21.0.13+9/bin/java";release=java.parent.parent/"release"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
processes=[]
for p in Path("/proc").iterdir():
 if not p.name.isdigit():continue
 try:
  comm=(p/"comm").read_text().strip()
  if comm not in["java","postgres"]:continue
  st=(p/"stat").read_text();fields=st[st.rfind(")")+2:].split();raw=(p/"cmdline").read_bytes()
  processes.append(dict(pid=int(p.name),comm=comm,startTicks=int(fields[19]),cpuTicks=int(fields[11])+int(fields[12]),argv=raw.rstrip(b"\0").decode().split("\0"),commandSha256=hashlib.sha256(raw).hexdigest(),executable=os.readlink(str(p/"exe"))))
 except(FileNotFoundError,ProcessLookupError,PermissionError):continue
cpu=Path("/proc/cpuinfo").read_text();cpu_model=next((x.split(":",1)[1].strip()for x in cpu.splitlines()if x.startswith("model name")),None)
result=dict(observedUTC=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),hostname=socket.gethostname(),bootId=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),kernel=platform.release(),machine=platform.machine(),logicalCpuCount=os.cpu_count(),affinity=sorted(os.sched_getaffinity(0)),cpuModel=cpu_model,memoryInfo=Path("/proc/meminfo").read_text(),overlayDiskUsage=shutil.disk_usage(root)._asdict(),mountInfo=Path("/proc/self/mountinfo").read_text(),javaSha256=sha(java),jdkReleaseSha256=sha(release),jdkRelease=release.read_text(),oldPreparationPresent=(root/"preparation").exists(),sourcePresent=(root/"source").is_dir(),processes=processes,networkInterfaces=[p.name for p in Path("/sys/class/net").iterdir()],readOnly=True,noProcessesStopped=True,noFileMutation=True)
print(json.dumps(result,sort_keys=True))
