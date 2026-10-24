from pathlib import Path
import subprocess,os,json,datetime,xml.etree.ElementTree as ET,shutil
work=Path.cwd();out=work/'build/chunk-validation/legacy-r2'
names=sorted(p.stem for p in (work/'cluster/src/test/java/io/vectormatch/cluster').glob('Retention*V3Test.java') if 'ThreeJvm' not in p.name and 'Pilot' not in p.name)
cmd=['/Users/kevin/Documents/ChatGPT/App 2/.tools/gradle/bin/gradle',':cluster:test']
for name in names:cmd+=['--tests','io.vectormatch.cluster.'+name]
cmd+=['--no-daemon'];env=os.environ.copy();env['JAVA_HOME']='/Users/kevin/Documents/ChatGPT/App 2/.tools/jdk';env['GRADLE_USER_HOME']='/Users/kevin/Documents/ChatGPT/App 2/.tools/gradle-user-home'
with (out/'registration.json').open('x') as f:json.dump({'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':cmd,'excludedNativeFilenameMarkers':['ThreeJvm','Pilot'],'includedTestClasses':names},f,indent=2)
with (out/'gradle.log').open('xb') as stdout:status=subprocess.run(cmd,env=env,stdout=stdout,stderr=subprocess.STDOUT).returncode
counts={k:0 for k in ['tests','failures','errors','skipped']};(out/'xml').mkdir()
for p in (work/'cluster/build/test-results/test').glob('TEST-*.xml'):
 shutil.copy2(p,out/'xml'/p.name);r=ET.parse(p).getroot()
 for k in counts:counts[k]+=int(r.attrib[k])
with (out/'receipt.json').open('x') as f:json.dump({'completedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exitCode':status,**counts},f,indent=2);f.write('\n')
print(json.dumps({'exitCode':status,**counts}));raise SystemExit(status)
