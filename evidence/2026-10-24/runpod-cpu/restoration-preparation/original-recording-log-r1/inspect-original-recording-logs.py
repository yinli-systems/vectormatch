#!/usr/bin/env python3
"""Original archived recording.log metadata, no cluster/archive session or recovery."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tarfile

BASE=Path(__file__).resolve().parent;REPO=BASE.parents[2]
OUT=REPO/'evidence/2026-10-24/runpod-cpu/restoration-preparation/original-recording-log-r1'
BUILD=BASE/'original-recording-log-preparation'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
OUT.mkdir(exist_ok=False);BUILD.mkdir(exist_ok=False)
source=BASE/'ReadOriginalRecordingLog.java';shutil.copy2(source,OUT/source.name);shutil.copy2(Path(__file__),OUT/Path(__file__).name)
lib=BASE/'app-restore-build/bundle/dist/cluster/lib';jars=[lib/'aeron-all-1.53.3.jar',lib/'agrona-2.6.1.jar']
assert sha(jars[0])=='4c6c8a5014a2b67424051170392a005daa9a998ac963302d2819d0f3db749ef2'
classpath=':'.join(str(p) for p in jars);jdk=REPO/'.tools/jdk/bin'
cmd=[str(jdk/'javac'),'--release','21','-cp',classpath,'-d',str(BUILD),str(source)]
c=subprocess.run(cmd,capture_output=True,text=True,timeout=20);assert c.returncode==0,c.stderr
results=[]
for node in range(3):
    inventory_path=REPO/'evidence/2026-10-23/runpod-optimization/gpu-to-cpu'/('node'+str(node)+'-pre-stop-state.json')
    receipt=json.loads(inventory_path.read_text());name='runtime/cloud-20261023-01/node-'+str(node)+'/cluster/recording.log';expected=receipt['files'][name]
    assert expected['bytes']<=65536 and receipt['allOwnedStopped'] and receipt['originalRolesStopped']
    archive=REPO/'runtime/cloud/optimization-20261024/gpu-to-cpu/backups'/('node'+str(node)+'-original-state.tar.gz')
    target=OUT/('node'+str(node));target.mkdir();found=0
    with tarfile.open(archive,'r|gz') as t:
        for m in t:
            if m.name!=name:continue
            assert m.isreg() and m.size==expected['bytes'];data=t.extractfile(m).read();assert hashlib.sha256(data).hexdigest()==expected['sha256']
            (target/'recording.log').write_bytes(data);found+=1;break
    assert found==1
    cmd=[str(jdk/'java'),'--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','-cp',str(BUILD)+':'+classpath,'ReadOriginalRecordingLog',str(target)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
    (target/'stdout.json').write_text(r.stdout);(target/'stderr.log').write_text(r.stderr);assert r.returncode==0,r.stderr
    entries=json.loads(r.stdout);assert sha(target/'recording.log')==expected['sha256']
    results.append({'node':node,'originalArchiveSha256':sha(archive),'originalStoppedInventorySha256':sha(inventory_path),
                    'recordingLogSha256BeforeAfter':expected['sha256'],'entries':entries,'argv':cmd,'exitCode':r.returncode})
summary={'passed':True,'scope':'Actual pinned Aeron1.53.3 reads disposable local recording.log copies;library opensRW,onlyreader methods used,before/afterbytes identical. NoArchive/session/node/start orRecoveryPlan. This is metadata baseline,not recovery/businesscanonical proof.',
         'dependencySha256':{p.name:sha(p) for p in jars},'sourceSha256':sha(source),'helperClassSha256':sha(BUILD/'ReadOriginalRecordingLog.class'),'results':results}
(OUT/'metadata.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'passed':True,'nodes':[{'node':r['node'],'entries':len(r['entries']),'snapshots':[e for e in r['entries'] if e['isValid'] and e['type']==1]} for r in results]}))
