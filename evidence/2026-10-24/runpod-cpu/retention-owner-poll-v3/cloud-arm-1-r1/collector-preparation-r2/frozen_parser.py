"""Load byte-exact qualified parser in an isolated import namespace, retaining strict defaults."""
import importlib.util
import json
from pathlib import Path
import sys
from common import require,sha

FREEZE_SHA='1fdec3e1bd4253e6eb11f32bc8bae5fbab53cd5531ffb8dec75c0cfb31e8c7b3'
MODULES=('common','read_phase_audit','workload_contract','archive_closure','idle_inventory','setup_audit','audit_raw')


def load(root=None):
    root=Path(root)if root is not None else Path(__file__).parent/'long_parser'
    freeze=root/'SOURCE_FROZEN.json';require(sha(freeze)==FREEZE_SHA,'Qualified long parser freeze differs')
    pins=json.loads(freeze.read_text())['sourceFiles'];loaded={};previous={name:sys.modules.get(name)for name in MODULES}
    try:
        for name in MODULES:
            path=root/('source/'+name+'.py');pin=pins['source/'+name+'.py']
            require(path.stat().st_size==pin['bytes']and sha(path)==pin['sha256'],'Frozen long parser body changed: '+name)
            unique='_qualified_long_'+FREEZE_SHA[:12]+'_'+name
            spec=importlib.util.spec_from_file_location(unique,path);module=importlib.util.module_from_spec(spec)
            sys.modules[unique]=module;sys.modules[name]=module;spec.loader.exec_module(module);loaded[name]=module
    finally:
        for name,module in previous.items():
            if module is None:sys.modules.pop(name,None)
            else:sys.modules[name]=module
    return loaded
