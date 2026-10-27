#!/usr/bin/env python3
"""Download a private evidence asset, verify EVERY member, extract selected stage inputs."""
from pathlib import Path
import argparse,json,hashlib,subprocess,tarfile,tempfile,shutil

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('thin_arm',type=Path);p.add_argument('output',type=Path);p.add_argument('--gh',default='gh');p.add_argument('--repo',default='yinli-systems/vectormatch');p.add_argument('--include-force',action='store_true',help='Also extract native force inputs and launch identities for offline re-audit');a=p.parse_args()
 proof=json.loads((a.thin_arm/'PRIVATE_ASSET_VERIFIED.json').read_text());manifest=json.loads((a.thin_arm/'ARCHIVE_MEMBER_MANIFEST.json').read_text())
 assert proof['authenticatedFullDownloadVerified'] and proof['allOriginalMembersVerified'] and not a.output.exists()
 assert shutil.disk_usage(a.output.parent).free>proof['bytes']+300*1024**2
 with tempfile.TemporaryDirectory(prefix='vm-evidence-',dir=a.output.parent)as tmp:
  archive=Path(tmp)/'original.tar.gz'
  with archive.open('xb')as f:subprocess.run([a.gh,'api','-H','Accept: application/octet-stream',f'repos/{a.repo}/releases/assets/{proof["assetId"]}'],stdout=f,check=True,timeout=1200)
  h=hashlib.sha256()
  with archive.open('rb')as f:
   for b in iter(lambda:f.read(1024**2),b''):h.update(b)
  assert archive.stat().st_size==proof['bytes'] and h.hexdigest()==proof['sha256']
  selected={};seen=set();manifest_seen=False
  with tarfile.open(archive,'r|gz')as t:
   for m in t:
    n=m.name;path=Path(n);assert m.isfile() and not path.is_absolute() and '..'not in path.parts
    if n=='ARCHIVE_MEMBER_MANIFEST.json':assert not manifest_seen and json.loads(t.extractfile(m).read())==manifest;manifest_seen=True;continue
    assert n in manifest['files'] and n not in seen;seen.add(n);v=manifest['files'][n];assert m.size==v['bytes']
    keep=n=='stage-attribution.csv' or (n.startswith('stages/')and(n.endswith('.csv')or n.endswith('complete.json')or n.endswith('clock.txt')))
    if a.include_force:keep=keep or n.startswith('force-wait/') or n in [f'node{i}-g0/LAUNCH.json'for i in range(3)]
    f=t.extractfile(m);h=hashlib.sha256();target=Path(tmp)/'selected'/n
    if keep:target.parent.mkdir(parents=True,exist_ok=True);out=target.open('xb')
    try:
     for b in iter(lambda:f.read(1024**2),b''):
      h.update(b)
      if keep:out.write(b)
    finally:
     if keep:out.close()
    assert h.hexdigest()==v['sha256'],n
    if keep:selected[n]=v
  assert manifest_seen and seen==set(manifest['files']) and 'stage-attribution.csv'in selected
  a.output.mkdir();
  for n in selected:
   dest=a.output/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(Path(tmp)/'selected'/n),dest)
  (a.output/'ARCHIVE_MEMBER_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
  receipt={'assetId':proof['assetId'],'archiveSha256':proof['sha256'],'allMembersVerified':len(seen),'selectedFiles':list(selected),'onlySelectedMembersExtracted':True}
  (a.output/'FETCH_VERIFIED.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
