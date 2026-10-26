from pathlib import Path
import tarfile,json,hashlib,subprocess,shutil,sys
P=Path(__file__).resolve().parent;R=P.parents[2];W=R/'runtime/worktrees/production-soak-shards'
cases=['physical-soak-r2']+(json.loads((P/'worker-wait-cases.json').read_text())if(P/'worker-wait-cases.json').exists()else[])
for case in cases:
 root=P/'analysis'/case;root.mkdir(parents=True,exist_ok=True);inputs=[]
 for folder in sorted((P/'archives').glob(case+'-vmatch-*')):
  proof=json.loads((folder/'PRIVATE_ASSET_VERIFIED.json').read_text());assert proof['allOriginalMembersVerified']and proof['authenticatedFullDownloadVerified']
  archive=folder/proof['name'];assert archive.exists()
  manifest=json.loads((folder/'MEMBER_MANIFEST.json').read_text())['files'];selected=[]
  with tarfile.open(archive,'r|gz')as t:
   for member in t:
    bits=Path(member.name).parts
    wanted=(len(bits)==2 and bits[0]=='evidence') or (len(bits)>=2 and bits[0]=='telemetry' and bits[1]in ['node%d-g0'%i for i in range(4)]) or (len(bits)==2 and bits[0]in ['node%d-g0'%i for i in range(4)] and bits[1]in ['LAUNCH.json','EXIT.json','metrics.jsonl','gc.log','stdout.log','stderr.log'])
    if not wanted:continue
    assert member.isfile() and not Path(member.name).is_absolute()and'..'not in bits
    target=root/member.name;target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists(),'duplicate member'
    h=hashlib.sha256();size=0
    with target.open('xb')as out:
     source=t.extractfile(member)
     for chunk in iter(lambda:source.read(1024**2),b''):out.write(chunk);h.update(chunk);size+=len(chunk)
    assert {'bytes':size,'sha256':h.hexdigest()}==manifest[member.name];selected.append(member.name)
  inputs.append({'privateAsset':proof,'selectedMembers':selected,'scope':'verified subset materialization for audit; complete originals remain in private asset'})
 (root/'RAW_INPUTS.json').write_text(json.dumps(inputs,indent=2));(root/'deployment').mkdir(exist_ok=True)
 shutil.copy2(P/'inventory.stdout',root/'deployment/inventory.json');shutil.copy2(P/'FAULT_DOMAINS.json',root/'deployment/fault-domains.json')
 members={}
 for f in root.rglob('*'):
  if f.is_file()and f.name!='MEMBER_MANIFEST.json':members[str(f.relative_to(root))]={'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
 (root/'MEMBER_MANIFEST.json').write_text(json.dumps({'files':members,'subsetMaterialization':True},indent=2))
 with (P/(case+'-audit.stdout')).open('x')as out,(P/(case+'-audit.stderr')).open('x')as err:
  q=subprocess.run(['python3',str(W/'scripts/audit-sustained-soak.py'),str(root),'--jfr',str(R/'.tools/jdk/bin/jfr'),'--output',str(P/(case+'-AUDIT.json'))],stdout=out,stderr=err,timeout=600)
 print(json.dumps({'case':case,'auditExit':q.returncode}),flush=True)
 if q.returncode:(P/(case+'-AUDIT_FAILURE.json')).write_text(json.dumps({'exitCode':q.returncode,'rawPreserved':True}))
