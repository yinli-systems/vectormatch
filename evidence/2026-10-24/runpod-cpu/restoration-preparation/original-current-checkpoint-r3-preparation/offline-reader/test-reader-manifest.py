#!/usr/bin/env python3
"""Pure local descriptor/path/lifecycle freshness guards; never launches Java or accesses cloud."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile

PREP=Path(__file__).absolute().parent
spec=importlib.util.spec_from_file_location('reader',PREP/'read-current-checkpoints.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
passed=[]
def check(label, action, rejected=False):
    try: action()
    except (ValueError, OSError):
        if not rejected: raise
    else:
        if rejected: raise AssertionError('accepted '+label)
    passed.append(label)

def main():
    with tempfile.TemporaryDirectory(prefix='vm-checkpoint-manifest-guards-') as td:
        base=Path(td).resolve()
        stop={'allOwnedStopped':True,'errors':[],'forcedKill':False,'stops':[{'role':'node-'+str(n),'stopped':True} for n in range(3)]}
        (base/'owned-stop.json').write_text(json.dumps(stop))
        def desc(path): return {'path':str(path.relative_to(base)),'bytes':path.stat().st_size,'sha256':r.sha(path)}
        nodes=[]
        for n in range(3):
            d=base/('node'+str(n));d.mkdir();(d/'recording.log').write_bytes(bytes(128));(d/'recording-prefix.bin').write_bytes(bytes(64))
            nodes.append({'node':n,'preflightMaxSnapshotEntryIndex':21,'recordingLog':desc(d/'recording.log'),
                          'selected':dict(zip(r.SELECTED_KEYS,[103,31,4096,8192,1000,22,104,23])),
                          'recording':{'filename':'103-0.rec','bytes':134217728,'sha256':'a'*64,'prefix':desc(d/'recording-prefix.bin'),'zeroTailBeyondPrefixVerified':True}})
        good={'schemaVersion':1,'scope':'STOPPED_CURRENT_ORIGINAL_CHECKPOINT','allOwnedStopped':True,'sourceRevision':r.REVISION,
              'expected':r.EXPECTED,'stopReceipt':desc(base/'owned-stop.json'),'nodes':nodes}
        manifest=base/'manifest.json'
        def validate(value): manifest.write_text(json.dumps(value));return r.validate_manifest(manifest)
        check('valid manifest-bound descriptors without any process launch',lambda:validate(good))
        def mutate(label,path,value):
            bad=copy.deepcopy(good);target=bad
            for key in path[:-1]:target=target[key]
            target[path[-1]]=value
            check(label,lambda:validate(bad),True)
        mutate('wrong R2 frontier',['expected','commandSeq'],4608)
        mutate('boolean numeric frontier',['expected','pendingEvents'],False)
        mutate('wrong original source',['sourceRevision'],'0'*40)
        mutate('unproved stopped state',['allOwnedStopped'],False)
        mutate('nonunique node index',['nodes',1,'node'],0)
        mutate('old checkpoint entry',['nodes',0,'preflightMaxSnapshotEntryIndex'],22)
        mutate('boolean selected recording',['nodes',0,'selected','recordingId'],True)
        mutate('recording filename differs',['nodes',0,'recording','filename'],'7-0.rec')
        mutate('zero-tail assertion missing',['nodes',0,'recording','zeroTailBeyondPrefixVerified'],False)
        mutate('node cohort term differs',['nodes',1,'selected','leadershipTermId'],32)
        mutate('node cohort timestamp differs',['nodes',1,'selected','timestamp'],1001)
        mutate('absolute input path',['nodes',0,'recordingLog','path'],str(base/'node0/recording.log'))
        mutate('parent traversal',['nodes',0,'recordingLog','path'],'node0/../node0/recording.log')
        mutate('same file reused',['nodes',0,'recording','prefix'],good['nodes'][0]['recordingLog'])
        mutate('recording hash invalid',['nodes',0,'recording','sha256'],'x'*64)
        mutate('prefix hash mismatch',['nodes',0,'recording','prefix','sha256'],'a'*64)
        mutate('prefix too large descriptor',['nodes',0,'recording','prefix','bytes'],r.MAX_PREFIX+1)
        mutate('unrecognized top field',['unexpected'],True)
        linked=base/'linked.bin';linked.symlink_to(base/'node0/recording-prefix.bin')
        bad=copy.deepcopy(good);bad['nodes'][0]['recording']['prefix']=desc(linked)
        check('symlink prefix rejected',lambda:validate(bad),True)
        badstop=copy.deepcopy(stop);badstop['forcedKill']=True;(base/'owned-stop.json').write_text(json.dumps(badstop))
        bad=copy.deepcopy(good);bad['stopReceipt']=desc(base/'owned-stop.json')
        check('forced kill stop rejected',lambda:validate(bad),True)
        manifest.write_text('{"scope":1,"scope":2}')
        check('duplicate JSON key rejected',lambda:r.validate_manifest(manifest),True)
    result={'passed':True,'count':len(passed),'guards':passed,'javaStarted':False,'aeronStarted':False,'cloudAccessed':False}
    (PREP/'manifest-guards.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
if __name__=='__main__':main()
