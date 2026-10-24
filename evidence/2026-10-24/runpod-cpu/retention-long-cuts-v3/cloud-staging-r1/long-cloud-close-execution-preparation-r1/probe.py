import argparse,hashlib,json,datetime,shlex,importlib.util,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();B=Path('runtime/cloud/cpu-20261024').resolve();source=B/'cpu-long-cuts-close-preparation-r1/inspect_closed_long_arm.py';h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert h(source)=='3ca5b87b245edbc24b7ad57a90796b870a4d37fd6cb7b74032e41119513e340a'
launch=json.loads((B/'long-cloud-arm-1-launch-r1/launch.stdout.json').read_text());assert launch['pid']==65351 and launch['startTicks']==4119786 and launch['observedCommandSha256']=='1f000a846dd62de70105362fd5dd397a236a75905a78580d7edc4cb78d4b49ee'
args=['python3','-B','-','--arm','1','--release-sha256','b552c8dbc10db4c3164d023d93226c81f8ea644f39b95f685de1d49135bfb93a','--controller-sha256','1d4103af9dde51d190dad2eec80117622563a2736ac41121131db56db5a23447','--controller-pid','65351','--controller-start-ticks','4119786','--controller-argv-sha256',launch['observedCommandSha256']]
assert not a.output.exists();a.output.mkdir(mode=0o700)
(a.output/'REGISTRATION.json').write_text(json.dumps({'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'probeSourceSha256':h(source),'argv':args,'scope':'Read-only exact registered long controller lifecycle inspection; no signals/rawparsing/nativehash/benchmark'},indent=2)+'\n')
helper=B/'remote.py';assert h(helper)=='0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73';spec=importlib.util.spec_from_file_location('pinned_remote',helper);remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
t=time.monotonic();r=remote.run(shlex.join(args),input=source.read_text(),timeout=45)
(a.output/'stdout.json').write_text(r.stdout);(a.output/'stderr.log').write_text(r.stderr)
(a.output/'COMPLETION.json').write_text(json.dumps({'exitCode':r.returncode,'sourceUnchanged':h(source)=='3ca5b87b245edbc24b7ad57a90796b870a4d37fd6cb7b74032e41119513e340a','elapsedSeconds':time.monotonic()-t},indent=2)+'\n');print(r.stdout);assert r.returncode==0
