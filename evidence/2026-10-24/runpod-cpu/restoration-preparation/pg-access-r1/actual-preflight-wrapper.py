import pathlib,hashlib,json,subprocess,sys
p=pathlib.Path('/opt/vectormatch-cpu/preparation/pg-access-source-r1')
expected={'pg_recovery.py': 'c2eb2ba8b96f30ebe09db5010cc4d7b23ab9cf7c7f0d78b289033bf31ab99c77', 'expected-baseline.json': '7a517d88b2759c1379f61b2f210176d96d67d4375848561fe948a09c90b5bff5', 'manifest.json': '2b7dda36a4fd431aa2509e07e174ed989f0c7cf61f8be353ea93d702b087d9d1'}
assert all(not x.is_symlink() for x in [p]+list(p.parents))
for name,h in expected.items():
 assert hashlib.sha256((p/name).read_bytes()).hexdigest()==h
r=subprocess.run(['/usr/bin/python3','-B',str(p/'pg_recovery.py')],capture_output=True,text=True,timeout=160)
sys.stdout.write(r.stdout);sys.stderr.write(r.stderr);sys.exit(r.returncode)
