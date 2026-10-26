from pathlib import Path
import datetime, hashlib, io, json, subprocess, tarfile, zipfile

R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';P=Path(__file__).resolve().parent;O=P/'lib'
assert not O.exists()
review=json.loads((B/'interbank-forced-correctness-r1/RESULT.json').read_text())
assert review['passed'] and review['junit']==dict(tests=446,failures=0,errors=0,skipped=0)
assert review['allTestTasksExecutedWithoutResultCache'] and review['sourceCommit']=='71eac60a88ca6d6079376d1b5bd369f646669f27'
C=B/'production-ci-attempt-20-collection-r1';verified=json.loads((C/'VERIFIED.json').read_text());assert verified['passed']
sha=lambda b:hashlib.sha256(b).hexdigest()
archive=C/'complete-code-compiled-tests-and-public-logs.tar.gz'
assert sha(archive.read_bytes())==verified['archiveSha256']
baseline=B/'async-v4-cut-gate-artifact-preparation-r1/lib'
O.mkdir();classes={};differences={}
with tarfile.open(archive)as t:
    members={m.name:m for m in t}
    for module in ('core','cluster'):
        name=module+'-0.1.0-SNAPSHOT.jar';member='original/compiled-and-tests/'+module+'/build/libs/'+name
        jar=t.extractfile(members[member]).read();(O/name).write_bytes(jar)
        with zipfile.ZipFile(io.BytesIO(jar))as z,zipfile.ZipFile(baseline/name)as old:
            bodies={n:z.read(n)for n in z.namelist()if n.endswith('.class')}
            expected_prefix='original/compiled-and-tests/'+module+'/build/classes/java/main/'
            compiled={n.removeprefix(expected_prefix):t.extractfile(m).read()for n,m in members.items()if n.startswith(expected_prefix)and n.endswith('.class')}
            assert bodies==compiled
            old_bodies={n:old.read(n)for n in old.namelist()if n.endswith('.class')}
            differences[module]=dict(changed=sorted(n for n in bodies.keys()&old_bodies.keys()if bodies[n]!=old_bodies[n]),
                                     added=sorted(bodies.keys()-old_bodies.keys()),removed=sorted(old_bodies.keys()-bodies.keys()))
            classes[module]={n:dict(bytes=len(b),sha256=sha(b))for n,b in sorted(bodies.items())}
    for name in ('aeron-all-1.53.3.jar','agrona-2.6.1.jar'):(O/name).write_bytes((baseline/name).read_bytes())
expectedSources={'cluster/src/main/java/io/vectormatch/cluster/'+name+'.java'for name in ['RetentionAsyncMaintenanceV4','RetentionCapacityAeronV4','RetentionCapacityExperimentV4','RetentionCapacityPlanV4','RetentionReadYieldPolicyV4']}
code=subprocess.check_output(['git','diff','--name-only','0c8303b250c61653eb1a0827ce54a67eab83e2a3',review['sourceCommit'],'--','core/src/main','cluster/src/main'],text=True).splitlines()
assert set(code)==expectedSources
for module,changes in differences.items():
 assert not changes['removed']
 allowed={source.split('/')[-1][:-5]for source in expectedSources if source.startswith(module+'/')}
 for name in changes['changed']+changes['added']:
  assert name.split('/')[-1].split('$')[0].split('.')[0]in allowed,name
assert 'io/vectormatch/core/MatchingEngine.class'not in differences['core']['changed']
files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes()))for p in sorted(O.iterdir())}
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceCommit=review['sourceCommit'],ciRun=review['runId'],
    ciOriginalArchiveSha256=verified['archiveSha256'],allCoreAndClusterJarClassesEqualActualCiCompiledClasses=True,
    compiledClasses=classes,files=files,classDifferences=differences,changedMainSources=code,noBenchmarkExecuted=True)
(P/'JAR_INPUTS.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(passed=True,sourceCommit=result['sourceCommit'],classes=sum(map(len,classes.values())),classDifferences=differences)))
