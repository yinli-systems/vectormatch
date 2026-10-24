#!/usr/bin/env python3
"""Close stopped r1 probe: exact ownership, control, full raw clone and file diff."""
from pathlib import Path
import hashlib,importlib.util,json,os,stat,tarfile
S=Path('/opt/vectormatch-cpu/preparation/pg-readonly-source-r2')
assert hashlib.sha256((S/'pg_recovery.py').read_bytes()).hexdigest()=='e8223d9bdd5a33319002d4567856c072e7f68801b554089bad2e4a6be7d59315'
spec=importlib.util.spec_from_file_location('m',S/'pg_recovery.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
R=Path('/opt/vectormatch-cpu/preparation/pg-readonly-close-r2')
assert not R.exists();m.no_symlink(R);R.mkdir(mode=0o700)
m.host_check();m.idle_check();m.port_check()
stop=json.loads((m.JOB/'automatic-stop.json').read_text());assert stop['stopped']
assert m.process_identity(stop['pid']) is None and not (m.PGDATA/'postmaster.pid').exists()
assert json.loads((m.JOB/'outer-result.json').read_text())['controllerExitCode']==0
assert json.loads((m.JOB/'sql-result.json').read_text())['ownedInspectorAbsent']
original=m.load_baseline();files,dirs=m.scan_tree(m.PGDATA)
def row(p):
    st=p.stat();return dict(bytes=st.st_size,sha256=m.sha(p),mode=stat.S_IMODE(st.st_mode),uid=st.st_uid,gid=st.st_gid,mtimeNs=st.st_mtime_ns)
actual={n:row(p) for n,p in sorted(files.items())}
directories=[]
for n in sorted(dirs):
    st=(m.PGDATA/n).stat();directories.append(dict(path=n,mode=stat.S_IMODE(st.st_mode),uid=st.st_uid,gid=st.st_gid,mtimeNs=st.st_mtime_ns))
assert all((e['uid'],e['gid'])==(963,963) for e in list(actual.values())+directories)
newbaseline=dict(original,pgFiles=actual,pgDirectories=directories,pgFilesCount=len(actual),
    derivedFrom='StoppedPG-onlyr2probe:expectedinternalphysicalwrites;originalimmutablebackupsretained')
m.save_new(R/'post-r2-baseline.json',newbaseline)
diff={'added':sorted(set(actual)-set(original['pgFiles'])),'removed':sorted(set(original['pgFiles'])-set(actual)),
      'changed':[{ 'path':n,'original':original['pgFiles'][n],'postR2':actual[n]} for n in sorted(set(actual)&set(original['pgFiles']))
                 if any(actual[n][k]!=original['pgFiles'][n][k] for k in ['bytes','sha256','mode'])]}
m.save_new(R/'post-r1-to-post-r2-diff.json',diff)
control=m.control_readback();m.save_new(R/'post-r2-control.json',control)
inputs={'postgres18':m.PGDATA,'job':m.JOB,'frozen-source':S}
inventory={};directoryInventory={}
for label,base in inputs.items():
    m.no_symlink(base)
    for p in [base]+sorted(base.rglob('*')):
        assert not p.is_symlink()
        st=p.stat();name=label+('/'+str(p.relative_to(base)) if p!=base else '')
        if p.is_dir():directoryInventory[name]=dict(mode=stat.S_IMODE(st.st_mode),uid=st.st_uid,gid=st.st_gid)
        else:
            assert stat.S_ISREG(st.st_mode) and st.st_nlink==1
            inventory[name]=row(p)
a=R/'raw-stopped-probe.tar.gz'
with tarfile.open(str(a),'x:gz',compresslevel=3) as tf:
    for label,base in inputs.items():tf.add(str(base),arcname=label,recursive=True)
assert a.stat().st_size<24*1024*1024
manifest={'passed':True,'files':inventory,'directories':directoryInventory,
    'archive':{'path':str(a),'bytes':a.stat().st_size,'sha256':m.sha(a)},
    'postR2BaselineSha256':m.sha(R/'post-r2-baseline.json'),'control':control,'diffCounts':{k:len(v) for k,v in diff.items()},
    'sqlInspectionPassed':json.loads((m.JOB/'sql-inspection-r2/inspection.json').read_text())['passed'],'serverStopped':True,'originalBackupsRetained':True,
    'scope':'Actualr2PG-onlyprobe;SQLresultseparatefield;rawstoppedderivedclonepreserved;notAeroncanonical/application/performanceproof'}
m.save_new(R/'closure.json',manifest)
print(json.dumps({'closure':manifest,'postR2Baseline':newbaseline,'diff':diff}))
