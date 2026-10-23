import pathlib,json,hashlib,shutil
import campaign as c
base=pathlib.Path(__file__).resolve().parent;root=pathlib.Path('evidence/2026-10-23/runpod-optimization').resolve();out=root/'network'
expected=[('isolated',f'o-isolated-15000-w128-r{r}') for r in (1,2)]+[('shared',f'o-shared-15000-w128-r{r}') for r in (1,2)]
prior=[]
for mode,ident in expected:
 d=root/mode/'runs'/ident
 result=json.loads((d/'result.json').read_text());leader=json.loads((d/'fixed-leader-check.json').read_text());verified=json.loads((d/'configuration-verification.json').read_text())
 assert result['passed'] and leader['passed'] and verified['passed']
 summary=json.loads((root/mode/'analysis/summary.json').read_text());row=next(t for t in summary['trials'] if t['id']==ident);assert row['measurementValid']
 prior.append({'id':ident,'classification':row['classification'],'resultSha256':hashlib.sha256((d/'result.json').read_bytes()).hexdigest(),'conditionalP99Millis':row['derived']['latency']['conditionalAccepted']['p99Millis'],'goodput':row['derived']['arrivalWindowGoodputPerSecond']})
assert any(json.loads(line)['action']=='primary-shared-driver-matrix-completed' for line in (root/'timeline.jsonl').read_text().splitlines())
assert not (out/'plan.json').exists(),'Already registered; resume exact next trial only'
node=json.loads((base/'node-release.json').read_text());load=json.loads((base.parent/'loadgen-release.json').read_text());probe=json.loads((base/'socket-probe.json').read_text());assert hashlib.sha256(pathlib.Path(probe['source']).read_bytes()).hexdigest()==probe['sha256']
source=json.loads((root/'shared/campaign.json').read_text())
for name,value in [('receive128k',131072),('receive1m',1048576)]:
 d=out/name;d.mkdir(exist_ok=True);config={**source,'registeredAtUtc':c.now(),'reason':'Only node requested UDP receive buffer changes; client remains one shared driver and128 independent Aeron/session/worker owners. Identical immutable new node artifact in both groups; sync2 unchanged.','scope':'Network receive-buffer one-factor campaign. Effective kernel rb/tb independently attested outside both arrival windows.','sourceCampaign':str(root/'shared/campaign.json'),'fixed':{**source['fixed'],'socketReceiveBufferArgumentBytes':value,'socketReceiveBufferBytes':value},'screeningRates':[15000]}
 c.save(d/'campaign.json',config);c.save(d/'deployment.json',node);shutil.copyfile(out/'node-deployment-manifest.json',d/'deployment-manifest.json')
plan=[]
for r in (1,2):
 for name,value,label in [('receive128k',131072,'128k'),('receive1m',1048576,'1m')]:plan.append({'id':f'n-r{label}-15000-w128-r{r}','cohort':name,'receiveBytes':value,'rate':15000,'arrivals':190000,'workers':128,'phase':'node-receive-buffer-control','repetition':r})
c.save(out/'plan.json',{'registeredAtUtc':c.now(),'primaryDriverMatrix':prior,'reason':'Client resource reduction did not establish15k stability; verified owned follower log sockets had drops, while node0 shared driver remained near one CPU. Test buffer effect before selecting threading factor.','node':node,'load':load,'effectiveBufferProbe':probe,'trials':plan,'budget':c.budget(3600),'scope':'A/B/A/B on same new node artifact with shared client driver. No stability/latency rule changed; original app remains paused; no new Pods or global sysctl.'});print('NETWORK_REGISTERED',len(plan),flush=True)
