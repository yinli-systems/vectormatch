import pathlib,hashlib,os
p=pathlib.Path('/opt/vectormatch-cpu/preparation/pg-readonly-source-r2/supervise-pg-readonly-r2.py')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='897c562dde3790f23a18686bbd46c98d520370462475f8761de05fd3cca013c5'
os.execv('/usr/bin/python3',['/usr/bin/python3','-B',str(p)])
