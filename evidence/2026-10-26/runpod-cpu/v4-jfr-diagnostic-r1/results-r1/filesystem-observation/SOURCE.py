from pathlib import Path
import json,os,shutil
p=Path('/opt/vectormatch-cpu');matches=[]
for line in Path('/proc/self/mountinfo').read_text().splitlines():
 left,right=line.split(' - ',1);a=left.split();b=right.split();mount=a[4].replace('\\040',' ')
 try:p.relative_to(mount)
 except ValueError:continue
 matches.append(dict(mountPoint=mount,fileSystemType=b[0],deviceMajorMinor=a[2]))
print(json.dumps(dict(target=str(p),longestMatchingMount=max(matches,key=lambda r:len(r['mountPoint'])),targetDevice=os.stat(p).st_dev,freeBytes=shutil.disk_usage(p).free,mountSourceAndOptionsNotCollected=True)))
