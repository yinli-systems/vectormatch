from pathlib import Path
import json,shutil,subprocess,hashlib,sys
P=Path(__file__).resolve().parent;R=Path('/Users/kevin/Documents/ChatGPT/App 2');W=R/'runtime/worktrees/production-soak-shards';C=P/'cloud';C.mkdir()
old=R/'runtime/benchmarks/public-comparison-20261027-r1/cloud'
shutil.copytree(W/'bench/build/install/common-comparison',C/'dist')
(C/'qualification').mkdir();shutil.copytree(W/'bench/build/classes/java/comparisonTest',C/'qualification/classes')
for f in (old/'qualification').glob('*.jar'):shutil.copy2(f,C/'qualification'/f.name)
s=(old/'LinuxQualification.java').read_text().replace('DiscoverySelectors.selectClass("io.vectormatch.bench.comparison.CommonFlowTest")','DiscoverySelectors.selectClass("io.vectormatch.bench.comparison.CommonFlowTest"),DiscoverySelectors.selectClass("io.vectormatch.bench.comparison.ProcessIsolationTest")').replace('!=6','!=9')
(C/'LinuxQualification.java').write_text(s)
cp=str(C/'qualification/classes')+':'+str(C/'qualification/*')+':'+str(C/'dist/lib/*')
subprocess.run([str(R/'.tools/jdk/bin/javac'),'-cp',cp,'-d',str(C/'qualification/classes'),str(C/'LinuxQualification.java')],check=True)
plan={'protocol':'docs/PROCESS_ISOLATION_PROTOCOL.md','sourceCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=W,text=True).strip(),'points':{'qualification-r1':{'qualification':True}}}
for name,placement,collector in [('functional-colocated-g1','COLOCATED','G1'),('functional-isolated-g1','ISOLATED','G1'),('functional-isolated-zgc','ISOLATED','GEN_ZGC')]:plan['points'][name]={'placement':placement,'collector':collector,'rate':1000,'seconds':1}
for phase in ['placement','collector']:
 for rate in [100000,250000]:
  for arm in ['a1','b1','a2','b2']:
   b=arm.startswith('b');plan['points'][f'{phase}-{rate}-{arm}']={'placement':('ISOLATED'if b else'COLOCATED')if phase=='placement'else'ISOLATED','collector':'GEN_ZGC'if phase=='collector'and b else'G1','rate':rate,'seconds':5}
(C/'PLAN.json').write_text(json.dumps(plan,indent=2)+'\n')
for n in ['audit-common-comparison.py','audit-process-isolation.py']:shutil.copy2(W/'scripts'/n,C/n)
(C/'tests').mkdir();shutil.copy2(W/'scripts/tests/test_common_comparison.py',C/'tests/test_common_comparison.py')
shutil.copy2(W/'docs/PROCESS_ISOLATION_PROTOCOL.md',C/'PROTOCOL.md')
for folder in ['bench/src/comparison/java','bench/src/comparisonTest/java']:
 shutil.copytree(W/folder,C/'source'/folder)
shutil.copy2(W/'bench/build.gradle.kts',C/'source/bench/build.gradle.kts')
s=(old/'archive_closed.py').read_text().replace("common-comparison-20261027-r1","process-isolation-20261027-r1").replace("closed-common-comparison-evidence-1","closed-process-isolation-evidence-1")
s=s.replace("assert name in {'qualification-r1','native-vector-q1','native-exchange-q1'} or name in {f'{r}-{a}'for r in [10000,50000,100000,250000]for a in ['a1','b1','a2','b2']}","assert name in json.loads((P/'PLAN.json').read_text())['points']")
(C/'archive_closed.py').write_text(s)
head=(old/'remote_worker.py').read_text().split('\ndef main():')[0].replace("common-comparison-20261027-r1","process-isolation-20261027-r1")
(C/'worker_head.txt').write_text(head)
files={str(f.relative_to(C)):{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}for top in ['dist','qualification']for f in sorted((C/top).rglob('*'))if f.is_file()}
(C/'CANDIDATE.json').write_text(json.dumps({'sourceCommit':plan['sourceCommit'],'files':files},indent=2)+'\n')
sys.path.insert(0,str(R/'runtime/cloud/cpu-20261024/current-read-window32-collection-preparation-r2'));import remote_current as remote
code="""from pathlib import Path
import json,os,shutil
for f in Path('/proc').glob('[0-9]*/comm'):
 try:assert f.read_text().strip()!='java','Java task active'
 except(FileNotFoundError,ProcessLookupError):pass
chosen=[0,2,7,10,12,19,24,26];assert set(chosen)<=os.sched_getaffinity(0)
assert Path('/etc/hostname').read_text().strip()=='33ace3d92505'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
print(json.dumps({'host':Path('/etc/hostname').read_text().strip(),'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'cpuMax':Path('/sys/fs/cgroup/cpu.max').read_text(),'allowed':sorted(os.sched_getaffinity(0)),'chosen':chosen,'freeBytes':shutil.disk_usage('/opt/vectormatch-cpu').free,'cpuInfo':Path('/proc/cpuinfo').read_text()}))
"""
r=remote.run('python3 -',input=code,timeout=45);assert r.returncode==0,r.stderr
(C/'CPU_ADMISSION.json').write_text(json.dumps(json.loads(r.stdout),indent=2)+'\n');print({'candidateFiles':len(files),'bytes':sum(v['bytes']for v in files.values()),'points':len(plan['points']),'sourceCommit':plan['sourceCommit']})
