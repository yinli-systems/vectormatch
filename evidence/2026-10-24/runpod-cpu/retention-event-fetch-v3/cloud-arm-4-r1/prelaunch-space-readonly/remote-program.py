import os,json,platform,shutil
assert platform.node()=='ed6c0673f5cb' and os.geteuid()==0
u=shutil.disk_usage('/opt/vectormatch-cpu')
print(json.dumps(dict(host=platform.node(),totalBytes=u.total,freeBytes=u.free,unchangedPerArmReserve=2116076873,aboveUnchangedLaunchReserve=u.free>=2116076873,readOnly=True,applicationStarted=False)))
