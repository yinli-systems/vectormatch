import pathlib,sys,json,hashlib,shlex
BASE=pathlib.Path(__file__).resolve().parent;REPO=BASE.parents[2];sys.path.insert(0,str(BASE));import remote
control='/workspace/vectormatch-cpu/bootstrap/cpu-jmh-observer-smoke-v2-r1';out=REPO/'evidence/2026-10-24/runpod-cpu/jmh-core-level-iterator/observer-smoke-v2';out.mkdir(exist_ok=False)
worker=BASE/'jmh-abab-worker-v2.py';assert hashlib.sha256(worker.read_bytes()).hexdigest()=='8323714d0fab440bb426908af1fcbb246a4ef38becf3077d1d6e6976e53517e7'
r=remote.run('python3 -B -',input='from pathlib import Path\nPath('+repr(control)+').mkdir(exist_ok=False)\n',timeout=30);assert r.returncode==0,r.stderr
for p in (worker,BASE/'jmh-observer-smoke.py'):
 r=remote.upload(p,control+'/'+p.name);assert r.returncode==0,r.stderr
r=remote.run('python3 -B '+shlex.quote(control+'/jmh-observer-smoke.py'),timeout=100)
(out/'transport.json').write_text(json.dumps({'exitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n');print(r.stdout);assert r.returncode==0,r.stderr
