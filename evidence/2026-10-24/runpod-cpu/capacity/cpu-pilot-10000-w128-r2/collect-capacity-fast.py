"""Collect one completed, already-archived CPU pilot with one binary SSH stream; never run workload."""
import pathlib,subprocess,sys,json,hashlib,shutil,shlex,datetime,importlib.util,argparse
BASE=pathlib.Path(__file__).resolve().parent;REPO=BASE.parents[2]
spec=importlib.util.spec_from_file_location('frozen_cpu_pilot_v2',BASE/'capacity_v2.py');C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
p=argparse.ArgumentParser();p.add_argument('--plan',type=pathlib.Path,required=True);a=p.parse_args();plan=C.validate_plan(C.read(a.plan));remote=C.remote_module();paths=C.paths(plan['jobId'])
lookup=remote.run('python3 -B -',input='from pathlib import Path\nprint(Path('+repr(str(paths['control']/'completion.json'))+').read_text())\n',timeout=30)
assert lookup.returncode==0,'Completion not available: query same job; no workload retry'
completion=json.loads(lookup.stdout);assert completion['archiveComplete'] and completion['allOwnedProcessesStopped'] and completion['planSha256']==plan['planSha256']
info=completion['archive'];assert info['path']==str(paths['archive']) and info['verifiedAllEntries']
local=REPO/'evidence/2026-10-24/runpod-cpu/capacity'/plan['jobId'];assert not local.exists();assert shutil.disk_usage(local.parent).free>info['bytes']+4*1024**3
local.mkdir();archive=local/(plan['jobId']+'.tar.gz');started=C.now()
with archive.open('xb') as out:
 r=subprocess.run(remote.sshargs()+['cat '+shlex.quote(info['path'])],stdout=out,stderr=subprocess.PIPE,timeout=300)
assert r.returncode==0,r.stderr.decode();assert archive.stat().st_size==info['bytes'] and C.sha(archive)==info['sha256']
C.save_new(local/'completion.json',completion)
C.save_new(local/'binary-transport.json',{'passed':True,'startedAtUtc':started,'completedAtUtc':C.now(),'archiveBytes':info['bytes'],'archiveSha256':info['sha256'],'sourceSha256':C.sha(__file__),'scope':'One read-only binary SSH stream of the exact completed synthetic-job archive; no new workload, reissue or process signal.'})
C.safe_extract(archive,local/'raw')
identity=plan['analysisIdentity']
for name,expected in identity['files'].items():assert C.sha(pathlib.Path(identity['root'])/name)==expected
for name in ('sourceArchive','validationReceipt'):assert C.sha(identity[name]['path'])==identity[name]['sha256']
assert C.sha(identity['python']['resolvedExecutable'])==identity['python']['binarySha256']
arguments=[identity['python']['executable'],'-I','-B',str(pathlib.Path(identity['root'])/identity['entryPoint']),'--runs-dir',str(local/'raw/evidence/runs'),'--output-dir',str(local/'analysis'),'--campaign',str(local/'raw/evidence/campaign.json')]
r=C.run_command(arguments,timeout=120);C.save_new(local/'postprocess.json',{**r,'analysisIdentitySha256':C.ANALYSIS_ID,'analysisIdentity':identity,'scope':C.SCOPE});assert r['exitCode']==0,r
s=C.read(local/'analysis/summary.json');assert len(s['trials'])==1
print(json.dumps({'jobId':plan['jobId'],'strictPilotPassed':completion['strictPilotPassed'],'trial':{k:s['trials'][0].get(k) for k in ('measurementValid','observedStableWindow','classification','arrivalWindowGoodputPerSecond','allOfferedAcceptedP99Millis')},'archiveBytes':info['bytes']}))
