import pathlib,json,socket,shutil,datetime,hashlib
assert socket.gethostname()=="ed6c0673f5cb"
pid=67629
assert not pathlib.Path("/proc",str(pid)).exists(),"Metadata PID is not strictly absent"
root=pathlib.Path("/opt/vectormatch-cpu/preparation/cpu-event-fetch-release-metadata-r1")
assert not pathlib.Path("/opt/vectormatch-cpu/preparation/cpu-event-fetch-cloud-abab-r1").exists()
print(json.dumps({"atUTC":datetime.datetime.now(datetime.timezone.utc).isoformat(),"metadataPid":pid,"strictPidAbsent":True,"newBenchmarkPreparationAbsent":True,"disk":shutil.disk_usage(root)._asdict(),"readOnly":True}))
