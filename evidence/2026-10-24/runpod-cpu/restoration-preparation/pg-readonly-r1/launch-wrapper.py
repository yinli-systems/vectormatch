import pathlib,hashlib,os
p=pathlib.Path('/opt/vectormatch-cpu/preparation/pg-readonly-source-r1/supervise-pg-readonly-r1.py')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='9707e129f47ddc457361834f979c0755590a167520d269bda82b838b955dfd76'
os.execv('/usr/bin/python3',['/usr/bin/python3','-B',str(p)])
