from pathlib import Path
import json,hashlib,subprocess,sys
P=Path(__file__).parent;W=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards');old=P.parent.parent/'replicated-stage-trace-20261027-r1/cloud'
candidate=json.loads((old/'CANDIDATE.json').read_text());candidate['sourceCommit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=W,text=True).strip();candidate['files']={}
for f in [*(P/'lib').glob('*.jar'),P/'soak-agent.jar',P/'stage-patch.jar',P/'libvmclock.so',*P.glob('audit-*.py'),P/'process_agent.py']:
 candidate['files'][str(f.relative_to(P))]={'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size}
(P/'CANDIDATE.json').write_text(json.dumps(candidate,indent=2)+'\n')
sys.path.insert(0,str(P));import controller as c
matrix={}
for name,s in c.PLAN['cases'].items():
 matrix[name]=[c.config(i,name,'G1',s['seconds'],True)for i in range(4)]
 for cfg in matrix[name]:
  assert len([x for x in cfg['properties']if x.startswith('-Dvectormatch.stage.preallocate=')])==1 and '-Dvectormatch.stage.trace=true'in cfg['properties']
(P/'LAUNCH_MATRIX.json').write_text(json.dumps(matrix,indent=2)+'\n');print({'commit':candidate['sourceCommit'],'cases':list(matrix),'configs':sum(map(len,matrix.values()))})
