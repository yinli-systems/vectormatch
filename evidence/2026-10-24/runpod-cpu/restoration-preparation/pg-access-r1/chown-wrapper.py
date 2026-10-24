import pathlib,hashlib,subprocess,sys
p=pathlib.Path('/opt/vectormatch-cpu/preparation/pg-access-source-r1')
assert hashlib.sha256((p/'pg_recovery.py').read_bytes()).hexdigest()=='c2eb2ba8b96f30ebe09db5010cc4d7b23ab9cf7c7f0d78b289033bf31ab99c77'
r=subprocess.run(['/usr/bin/python3','-B',str(p/'pg_recovery.py'),'chown','--execute'],capture_output=True,text=True,timeout=160)
sys.stdout.write(r.stdout);sys.stderr.write(r.stderr);sys.exit(r.returncode)
