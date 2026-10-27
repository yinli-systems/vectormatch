from pathlib import Path
import json,hashlib,subprocess,os
P=Path(__file__).resolve().parent;GH='/Users/kevin/.local/bin/gh';REPO='yinli-systems/vectormatch';RELEASE=423510304
original=P.parent/'cloud-package.tar.gz';name='vectormatch-replicated-sustained-20261027-r3-frozen-runtime.tar.gz';a=P.parent/name
if not a.exists():os.link(original,a)
sha=hashlib.sha256(a.read_bytes()).hexdigest();assert sha==json.loads((P/'STAGED.json').read_text())['packageSha256']
api=lambda path:json.loads(subprocess.check_output([GH,'api',path],text=True))
assert api('repos/'+REPO)['private'];release=api('repos/'+REPO+'/releases/'+str(RELEASE));assert release['draft']
assets=[x for x in release['assets']if x['name']==name]
if not assets:
 subprocess.run([GH,'release','upload',release['tag_name'],str(a),'--repo',REPO],check=True,timeout=180);assets=[x for x in api('repos/'+REPO+'/releases/'+str(RELEASE))['assets']if x['name']==name]
assert len(assets)==1 and assets[0]['size']==a.stat().st_size
q=subprocess.Popen([GH,'api','-H','Accept: application/octet-stream','repos/'+REPO+'/releases/assets/'+str(assets[0]['id'])],stdout=subprocess.PIPE);h=hashlib.sha256();n=0
for b in iter(lambda:q.stdout.read(1024**2),b''):h.update(b);n+=len(b)
assert q.wait(timeout=30)==0 and h.hexdigest()==sha and n==a.stat().st_size
v={'assetId':assets[0]['id'],'name':name,'sha256':sha,'bytes':n,'privateDraftRelease':RELEASE,'authenticatedFullDownloadVerified':True,'samePackageVerifiedByRemoteBeforeFirstQualification':True}
(P/'RUNTIME_PRIVATE_VERIFIED.json').write_text(json.dumps(v,indent=2)+'\n');print(v)
