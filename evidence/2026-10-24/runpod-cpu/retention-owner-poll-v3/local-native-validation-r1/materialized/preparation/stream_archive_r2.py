"""Finite streaming gzip/TAR primitives; no native data or processes opened at import."""
from pathlib import Path
import gzip,tarfile

class Cap:
 def __init__(self,file,maximum=256*1024**2):self.file=file;self.maximum=maximum;self.n=0
 def write(self,data):
  if self.n+len(data)>self.maximum:raise AssertionError('Compressed archive256MiB cap')
  count=self.file.write(data);self.n+=count;return count
 def flush(self):return self.file.flush()

def native_items(root):
 """Never classify a prior/current derived closure as original business data."""
 root=Path(root);items=[]
 for path in sorted(root.iterdir()):
  if path.name.startswith('closed-originals'):continue
  for member in [path]+sorted(path.rglob('*'))if path.is_dir()else[path]:
   items.append((member,Path('native')/member.relative_to(root)))
 return items

def pack_stream(archive,items,maximum=256*1024**2):
 # Python3.9 streaming tar does NOT accept compresslevel; gzip owns compression.
 with Path(archive).open('xb')as output:
  with gzip.GzipFile(fileobj=Cap(output,maximum),mode='wb',compresslevel=1)as compressed:
   with tarfile.open(fileobj=compressed,mode='w|')as tar:
    for source,name in items:tar.add(source,arcname=str(name),recursive=False)
