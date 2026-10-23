import campaign as c,pathlib,json,subprocess,sys,urllib.request,hashlib
root=pathlib.Path('evidence/2026-10-23/runpod-optimization').resolve();base=pathlib.Path(__file__).resolve().parent
node=json.loads((c.remote.ROOT/'current-release.json').read_text());assert node['revision']=='b6f6c5cd165110e330d409e2ff51ee4574a3720b'
load=json.loads((base/'loadgen-release.json').read_text());receipt=json.loads((root/'loadgen-upload-receipt.json').read_text());assert receipt['verified'] and receipt['loadGeneratorRevision']==load['revision']
probe=json.loads((base/'attribution-release.json').read_text());c.PROFILE='extended-190k-128';c.COMMON.update({'VECTOR_OUTBOX_CAPACITY':'524288','VECTOR_MAX_HEAP':'2g','VECTOR_STATE_PROFILE':'capacity-190k-v1'});c.LOAD_RELEASE=load['root'];c.LOAD_IDENTITY={'loadGeneratorRevision':load['revision'],'loadGeneratorBundleSha256':load['bundleSha256'],'loadGeneratorRelease':load['root'],'attributionObserverIdentity':probe['identity']};c.ATTRIBUTION_ROOT=probe['root'];c.OUT=root
assert not (root/'original-paused.json').exists(),'Already paused; resume exact trial instead of replaying plan'
with urllib.request.urlopen('http://127.0.0.1:8011/api/state',timeout=20) as r:original=json.load(r)
assert original['health']['status']=='UP' and original['health']['flowEnabled'] is False;c.save(root/'original-before-pause.json',original)
c.record('prepare-budget',**c.budget(7200))
for role in ('gateway','projector'):c.record('pause-original',role=role,stdout=c.service(2,role,'stop',c.ORIG))
c.record('stop-original-nodes',stdout=c.parallel(lambda i:c.service(i,'node','stop',c.ORIG)))
p=c.remote.run(2,"runuser -u vectormatch-pg -- /opt/vectormatch/.tools/postgres/bin/pg_ctl -D /opt/vectormatch/runtime/postgres18 -m fast -w stop",timeout=40);c.record('stop-original-postgres',exitCode=p.returncode,stdout=p.stdout,stderr=p.stderr);assert p.returncode==0
c.save(root/'original-paused.json',{'timestamp':c.now(),'nativeFilesPreserved':True,'originalState':c.ORIG['VECTOR_STATE_DIR'],'originalJavaRelease':c.ORIGINAL,'reason':'Controlled fixed-node optimization campaign; no native database archive exported','budget':c.budget(0)})
c.save(root/'frozen-load-and-observer.json',{'timestamp':c.now(),'node':node,'load':load,'observer':probe,'planSha256':hashlib.sha256((root/'plan.json').read_bytes()).hexdigest()})
plan=json.loads((root/'plan.json').read_text())['trials']
for task in plan:
 c.OUT=root/task['mode'];c.LOAD_JVM_ARGUMENTS=['-Dvectormatch.capacity.client.driver='+task['mode']]
 d=c.trial(task['id'],task['rate'],task['arrivals'],task['workers'],task['phase'],task['repetition']);assert d and d['passed'],'Correctness failed; preserve run and inspect'
 subprocess.run([sys.executable,'-B','scripts/verify-capacity-config.py',str(c.OUT)],check=True)
 subprocess.run([sys.executable,'-B','scripts/analyze-capacity.py','--runs-dir',str(c.OUT/'runs'),'--output-dir',str(c.OUT/'analysis')],check=True)
 row=next(r for r in json.loads((c.OUT/'analysis/summary.json').read_text())['trials'] if r['id']==task['id']);assert row['measurementValid'],'Invalid measurement; inspect before continuing'
 print('CONTROLLED_TRIAL_RESULT',json.dumps({'id':task['id'],'classification':row['classification'],'goodput':row['derived']['arrivalWindowGoodputPerSecond'],'p99Millis':row['derived']['latency']['conditionalAccepted']['p99Millis'],'notSent':row['derived']['clientNotSent'],'unknown':row['derived']['unknownUnresolved']}),flush=True)
c.OUT=root;c.record('primary-shared-driver-matrix-completed',budget=c.budget(0));print('MATRIX_COMPLETE_INSPECT_BEFORE_NEXT_FACTOR',flush=True)
