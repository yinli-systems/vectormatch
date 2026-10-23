import campaign as c,pathlib,json,shutil
out=pathlib.Path('evidence/2026-10-23/runpod-optimization');node=json.loads((c.remote.ROOT/'current-release.json').read_text());assert node['revision']=='b6f6c5cd165110e330d409e2ff51ee4574a3720b'
base=json.loads(pathlib.Path('evidence/2026-10-23/runpod-capacity-long/campaign.json').read_text());prepared='2247db9c15b0043a0b28172c5bfa2d9e4f20b5748f6a16424d881e296102655f'
for mode in ['isolated','shared']:
 d=out/mode;d.mkdir(exist_ok=True);assert not (d/'campaign.json').exists()
 config={**base,'registeredAtUtc':c.now(),'protocol':'docs/OPTIMIZATION_CAMPAIGN.md','scope':'New controlled one-factor client-driver campaign; fixed old b6f node. This mode is a distinct curve. Same new load artifact in both modes, read-only attribution observer in all measured trials.','reason':'Client driver count only; independent Aeron/client/worker/session identities and sync2 preserved','clientDriverMode':mode,'sourceCampaign':'evidence/2026-10-23/runpod-capacity-long/campaign.json','screeningRates':[15000,16000,19000],'preparedSnapshotSha256':prepared}
 c.save(d/'campaign.json',config);c.save(d/'deployment.json',node)
 for name in ['deployment-manifest.json','telemetry-deployment.json']:
  p=pathlib.Path('evidence/2026-10-23/runpod-capacity-long')/name
  if p.exists():shutil.copyfile(p,d/name)
plan=[{'id':'o-smoke-shared-8000-w128','mode':'shared','rate':8000,'arrivals':20000,'workers':128,'phase':'shared-driver-smoke','repetition':1}]
for rep in [1,2]:
 for mode in ['isolated','shared']:plan.append({'id':f'o-{mode}-15000-w128-r{rep}','mode':mode,'rate':15000,'arrivals':190000,'workers':128,'phase':'driver-count-control','repetition':rep})
c.save(out/'plan.json',{'registeredAt':c.now(),'scope':'Smoke then pre-registered A/B/A/B; compare complete same-new-load-revision cohorts. No capacity claim for short smoke. Immutable load identity and observer digest will be fixed before first trial. Adaptive extension only after completed results.','nodeRevision':node['revision'],'nodeBundleSha256':node['bundleSha256'],'preparedSnapshotSha256':prepared,'trials':plan,'budgets':c.budget(7200),'longTermTargets':{'cumulativeUniqueAcceptedCommands':100000000,'uniqueAcceptedCommandsPerSecond':100000000,'simultaneousConnections':100000000,'status':'All targets unverified requirements; instantaneous targets not feasible to validate on current budget/resources. Do not conflate them.'}})
print('REGISTERED',len(plan),'TRIALS',node['revision'])
