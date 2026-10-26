from pathlib import Path
import json,hashlib,socket
assert socket.gethostname()=='33ace3d92505'
roots=[Path('/opt/vectormatch-cpu/tools/jdk-21.0.13+9'),Path('/opt/vectormatch-cpu/ci/production-correctness-r20/toolcache/Java_Temurin-Hotspot_jdk/21.0.13-9.0.LTS/x64')]
def tree(root):
 out={}
 for p in sorted(root.rglob('*')):
  if not p.is_file():continue
  p.resolve().relative_to(root.resolve())
  out[str(p.relative_to(root))]=dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 return out
values=[tree(r)for r in roots];assert values[0]==values[1]and len(values[0])==454
print(json.dumps(dict(passed=True,roots=list(map(str,roots)),files=[len(v)for v in values],allFileBodies=values[0],allActualCiAndBenchmarkImageFileBytesEqual=True,noJavaStarted=True)))
