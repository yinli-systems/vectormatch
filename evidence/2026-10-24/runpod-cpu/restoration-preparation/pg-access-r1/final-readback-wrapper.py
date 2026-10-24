import importlib.util,pathlib,json,subprocess,hashlib
s=pathlib.Path('/opt/vectormatch-cpu/preparation/pg-access-source-r1')
assert hashlib.sha256((s/'pg_recovery.py').read_bytes()).hexdigest()=='c2eb2ba8b96f30ebe09db5010cc4d7b23ab9cf7c7f0d78b289033bf31ab99c77'
spec=importlib.util.spec_from_file_location('m',s/'pg_recovery.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=m.preflight(require_access=True,expected_owner=(963,963));m.job_privacy()
files={}
for base,pat in [(m.JOB,'*.json'),(s,'job-acl-r2-*.json')]:
 for f in sorted(base.glob(pat)):
  assert f.is_file() and not f.is_symlink() and f.stat().st_size<1000000
  files[str(f)]=f.read_text()
print(json.dumps({'passed':True,'readback':p,'receipts':files,'scope':'Actual27Linuxguards+dedicatedaccount+exactfiveACLs+PGDATA-onlyownership; originalPGbytes/modescleancontrolstillidentical; noPGstart/SQL'}))
