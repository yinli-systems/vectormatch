import campaign as c,json
for workers,rate in ((32,2400),(64,2400),(32,3000),(64,3000)):
 ident=f'concurrency-{rate:04d}-w{workers}'
 d=c.trial(ident,rate,min(rate*12,30000),workers,'concurrency',1)
 assert d is not None and d['passed'],'Correctness failed'
 assert json.loads((c.OUT/'runs'/ident/'fixed-leader-check.json').read_text())['passed'],'Fixed leader evidence failed'
