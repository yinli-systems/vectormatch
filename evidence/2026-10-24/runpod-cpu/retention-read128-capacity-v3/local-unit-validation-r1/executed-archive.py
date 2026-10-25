from pathlib import Path
import json,hashlib,stat,shutil,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=R/'evidence/2026-10-24/runpod-cpu/retention-read128-capacity-v3/local-unit-validation-r1';O.parent.mkdir(parents=True,exist_ok=True);assert not O.exists()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def tree(p):
 files={};dirs={}
 for q in[p,*sorted(p.rglob('*'))]:
  assert not q.is_symlink();s=q.stat();n=q.relative_to(p).as_posix();r=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
  if q.is_dir():dirs[n]=r
  else:files[n]=dict(r,bytes=s.st_size,sha256=sha(q))
 return dict(files=files,directories=dirs)
names=['read128-capacity-unit-r1'];assert json.loads((B/names[0]/'VALIDATION.json').read_text())['passed'];before={n:tree(B/n)for n in names};O.mkdir()
for n in names:shutil.copytree(B/n,O/n);assert tree(B/n)==tree(O/n)==before[n]
(O/'SOURCE_MIRRORS.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py');(O/'README.md').write_text('# Fixed128-credit capacity preset candidate:64 local tests\n\n64 distinct tests across14 JUnit reports pass, zero failures/errors/skips; installDist completed. Six explicit20-second presets500/1000/2000/4000/8000/16000 retain read128/page32/batch4/chunk6144 and equal5s pre-load warm-up. Every exact codec-derived plan passes existing raw/allocation/journal/writer caps. Old fixed20000@1000 read32/128 comparison mode remains unchanged. Native source is separately qualified before any capacity result.\n\nFull source/build inputs were captured after Gradle completed and verified unchanged before closure; no preregistration claim for that source capture. Actual test process executable/options/classpath were recorded by Gradle before test execution. All existing registered classpath bodies are copied; NO-SOURCE absent resource directories remain explicitly absent. Installed application JAR class bodies match actual test-compiled main classes. Full JUnit XML/HTML, local JDK executable/release, installedJARs and all14 maintenance fixture roots (including9original128-boundary failure proofs) are retained. Synthetic unit fixtures are not native wire performance evidence. New native installed-JAR metadata, original configuration/leader/process/native/raw checks remain required. No throughput,100M or hard-realtime claim.\n');i=tree(O);(O/'INVENTORY.json').write_text(json.dumps(i,indent=2,sort_keys=True)+'\n');(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=sha(O/'INVENTORY.json'),payloadFiles=len(i['files']),allSourceCopiesCompleteAndEqual=True,allAvailableFailedAndSuccessfulUnitScopesRetained=True,noNativeBenchmarkClaim=True),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,payloadFiles=len(i['files']),inventorySha256=sha(O/'INVENTORY.json'))))
