import campaign as c,json
for rate in (100,200,400,800,1600,2400):
 d=c.trial(f'screen-{rate:04d}-w16',rate,rate*12,16,'screen',1)
 assert d is not None and d['passed'],'Correctness failed, stopping campaign'
 check=json.loads((c.OUT/'runs'/f'screen-{rate:04d}-w16'/'fixed-leader-check.json').read_text())
 assert check['passed'],'Fixed leadership unverified, stopping campaign'
