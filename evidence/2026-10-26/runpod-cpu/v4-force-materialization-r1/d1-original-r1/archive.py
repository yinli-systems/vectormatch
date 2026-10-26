from pathlib import Path
import json,sys,shutil,hashlib,subprocess,datetime,importlib.util
P=Path(__file__).resolve().parent;B=P.parent;W=B/'interbank-v4-worktree';phase=sys.argv[1];assert phase in ['qualification','c1','d1','c2','d2']
O=B/('v4-force-materialization-'+phase+'-r1');r=json.loads((O/'VERIFIED.json').read_text());assert r['passed']
A=W/('evidence/2026-10-26/runpod-cpu/v4-force-materialization-r1/'+phase+'-original-r1');assert not A.exists();A.mkdir()
for p in O.iterdir():
 assert p.is_file()and not p.is_symlink();shutil.copy2(p,A/p.name)
(A/'README.md').write_text('# Standalone force materialization: '+phase+'\n\nThe TAR retains every original synthetic file,all timing samples,full readback results,and owned process controls. Inventories pin every body,mode,owner and empty directory. Both CPU and local full-member reviews passed. The prospective source/config/class/protocol is in ../prospective-r1. This is a bounded closed-loop filesystem probe,not orders,network latency,capacity or production certification. All original active application/archive state remains unopened.\n')
shutil.copy2(P/'archive.py',A/'archive.py')
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import tree,sha,verify
m=json.loads((A/'remote-manifest.json').read_text());assert verify(A/'complete-original-files.tar.gz',m['sourceScopes'])==m['everyOriginalMemberVerified'];inv=tree(A)
(A/'INVENTORY.json').write_text(json.dumps(inv,indent=2,sort_keys=True)+'\n');(A/'CLOSED.json').write_text(json.dumps(dict(passed=True,inventorySha256=sha(A/'INVENTORY.json'),originalScopesVerified=m['everyOriginalMemberVerified'],noTradingPerformanceClaim=True),indent=2,sort_keys=True)+'\n')
git=lambda *a:subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','-C',str(W),*a]);branch=git('branch','--show-current').decode().strip();assert branch=='codex/v4-owned-jfr-profile'
git('add','--sparse',A.relative_to(W).as_posix());git('commit','-m','Archive all original standalone force '+phase+' files and every timing sample');head=git('rev-parse','HEAD').decode().strip()
spec=importlib.util.spec_from_file_location('blob_guard',W/'scripts/check-new-git-blobs.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard);assert guard.check(W,'HEAD~1','HEAD')['passed']
git('push','origin',branch);assert git('ls-remote','origin','refs/heads/'+branch).decode().split()[0]==head
assert json.loads(subprocess.check_output(['gh','api','repos/yinli-systems/vectormatch']))['private']
actual=tree(A)
for n,pin in actual['files'].items():
 body=git('show',head+':'+A.relative_to(W).as_posix()+'/'+n);assert len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256']
proof=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),private=True,phase=phase,commit=head,allGitBodiesVerified=len(actual['files']),completeOriginalScopesVerified=m['everyOriginalMemberVerified'],noNativeTradingPerformanceClaim=True);(O/'PRIVATE_PUSH.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n');print(json.dumps(proof))
