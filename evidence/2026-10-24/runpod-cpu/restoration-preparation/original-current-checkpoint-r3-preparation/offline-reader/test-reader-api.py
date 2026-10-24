#!/usr/bin/env python3
"""Pure integration guards for caller-owned API; no Java/child/cloud process starts."""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import copy

PREP=Path(__file__).absolute().parent
spec=importlib.util.spec_from_file_location('reader',PREP/'read-current-checkpoints.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
passed=[]
def rejects(label, action):
    try:action()
    except (ValueError,OSError):passed.append(label);return
    raise AssertionError('accepted '+label)
def main():
    ast.parse((PREP/'read-current-checkpoints.py').read_text(),feature_version=(3,8))
    passed.append('Python 3.8 syntax accepted')
    def forbidden(*args,**kwargs):raise AssertionError('API launched a child process')
    r.subprocess.run=forbidden
    r.frozen_artifacts()
    with tempfile.TemporaryDirectory(prefix='vm-checkpoint-api-guards-') as td:
        base=Path(td).resolve()
        def desc(path):return {'path':str(path.relative_to(base)),'bytes':path.stat().st_size,'sha256':r.sha(path)}
        stop={'allOwnedStopped':True,'errors':[],'forcedKill':False,'stops':[{'role':'node-'+str(n),'stopped':True} for n in range(3)]}
        (base/'owned-stop.json').write_text(json.dumps(stop))
        nodes=[]
        for n in range(3):
            d=base/('node'+str(n));d.mkdir();(d/'recording.log').write_bytes(bytes(128));(d/'recording-prefix.bin').write_bytes(bytes(64))
            nodes.append({'node':n,'preflightMaxSnapshotEntryIndex':21,'recordingLog':desc(d/'recording.log'),
                          'selected':dict(zip(r.SELECTED_KEYS,[103,31,4096,8192,1000,22,104,23])),
                          'recording':{'filename':'103-0.rec','bytes':134217728,'sha256':'a'*64,'prefix':desc(d/'recording-prefix.bin'),'zeroTailBeyondPrefixVerified':True}})
        manifest={'schemaVersion':1,'scope':'STOPPED_CURRENT_ORIGINAL_CHECKPOINT','allOwnedStopped':True,'sourceRevision':r.REVISION,
                  'expected':r.EXPECTED,'stopReceipt':desc(base/'owned-stop.json'),'nodes':nodes}
        path=base/'manifest.json';path.write_text(json.dumps(manifest))
        # This executable is never invoked; the API only records caller-supplied argv.
        java=base/'java';java.write_text('not executed\n');java.chmod(0o700)
        rejects('relative Java path rejected',lambda:r.prepare_inputs(path,base/'bad','java'))
        plan=r.prepare_inputs(path,base/'decoded',java)
        assert len(plan['nodes'])==3 and plan['launchesPerformed'] is False
        assert all(n['argv'][0]==str(java) and '*' not in n['argv'][5] and len(n['argv'])==18 for n in plan['nodes'])
        passed.append('exact three direct caller-owned argv produced without launch')
        assert all((base/'decoded'/('node%d/disposable-recording-log/recording.log'%n)).read_bytes()==bytes(128) for n in range(3))
        passed.append('disposable recording logs are exact separate copies')
        rejects('existing output refused',lambda:r.prepare_inputs(path,base/'decoded',java))
        rejects('failed owned exit rejected before any decoded files read',lambda:r.finish_outputs(plan,[{'node':0,'exitCode':1},{'node':1,'exitCode':0},{'node':2,'exitCode':0}]))
        rejects('unordered owned exits rejected',lambda:r.finish_outputs(plan,[{'node':1,'exitCode':0},{'node':0,'exitCode':0},{'node':2,'exitCode':0}]))
        rejects('successful exits alone do not prove decode',lambda:r.finish_outputs(plan,[{'node':n,'exitCode':0} for n in range(3)]))
        tamper=copy.deepcopy(plan);tamper['nodes'][0]['argv'][0]='/forged/java'
        rejects('modified plan rejected',lambda:r.finish_outputs(tamper,[{'node':n,'exitCode':0} for n in range(3)]))
        (base/'node0/recording.log').write_bytes(bytes(64)+b'x'*64)
        rejects('input change after preparation rejected',lambda:r.finish_outputs(plan,[{'node':n,'exitCode':0} for n in range(3)]))
    result={'passed':True,'count':len(passed),'guards':passed,'childStarted':False,'cloudAccessed':False,'actualCheckpointDecoded':False}
    (PREP/'api-guards.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
