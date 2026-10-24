from pathlib import Path
import re,json
p=Path('/opt/vectormatch-cpu/source/.tools/gradle-user-home/daemon/8.14.3/daemon-5669.out.log')
assert p.is_file() and not p.is_symlink()
with p.open('r',errors='replace')as f:head=f.read(262144)
values=sorted(set(int(x)for x in re.findall(r'idleTimeout=(\d+)',head)))
print(json.dumps(dict(readOnly=True,source=str(p),idleTimeoutMsValues=values,onlyBoundedNumericConfigurationExtracted=True,noFullLogOrCredentialsReturned=True,noStopRequested=True)))
