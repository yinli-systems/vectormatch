#!/usr/bin/env python3
"""Prospective Linux synthetic-force diagnostic. Default/register are local; no implicit launch/retry."""
from pathlib import Path, PurePosixPath
import argparse
import base64
import csv
import ctypes
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
import platform
import re
import shlex
import signal
import struct
import subprocess
import sys
import tarfile
import time
import traceback

BASE=Path(__file__).resolve().parent
CPU_BASE=BASE.parent
REPO=BASE.parents[3] if len(BASE.parents)>3 else None
HOST='ed6c0673f5cb'; POD='4il7v4518ccogj'
ROOT=Path('/opt/vectormatch-cpu'); CONTROL=Path('/workspace/vectormatch-cpu-control')
JAVA=ROOT/'tools/jdk/bin/java'; PROC=Path('/proc')
PREPARATION_SHA='5d437f48e1379a83ac009d1e657124682fca4f32cc1572f7c31f77338f2f5a0d'
SOURCE_SHA='3331268b1852d53c9f20b767f632c84280518239a4d3a508253919abeac10e74'
CLIENT_CONTROLLER_SHA='e5fa98bf5ee4978b259120afb1b1da3cdcef87b3225b64814e405914f590fc29'
PREDECESSOR_ID='cpu-client-driver-park-22000-w128-abab-ebede-r1'
PREDECESSOR_POINTS=tuple('cpu-capacity-clientpark-'+stage+'-22000-w128-r1' for stage in ('a1','b1','a2','b2'))
BLOCKS=(4096,16384,24576,49152)
PREALLOC_BLOCKS=16; WARMUP=10; MEASUREMENTS=200
ADMISSION_MS=30000; PROCESS_SECONDS=35; MATRIX_SECONDS=280
MIN_FREE=3*1024**3; MAX_CSV=1024**2; MAX_META=65536; MAX_LOG=262144
HEADER='schema_version,phase,writer_id,iteration,wall_utc,monotonic_start_ns,offset_bytes,requested_bytes,written_bytes,write_calls,force_calls,write_elapsed_ns,force_elapsed_ns,total_elapsed_ns,thread_cpu_ns,deadline_exceeded,status,error'.split(',')


def require(ok,message):
    if not ok:raise ValueError(message)
def utc():return dt.datetime.now(dt.timezone.utc).isoformat()
def sha(path):
    p=Path(path);require(p.is_file() and not p.is_symlink(),'Regular owned file required: '+str(p))
    h=hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def value_sha(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def read(path,maximum=None):
    p=Path(path)
    if maximum is not None:require(p.stat().st_size<=maximum,'JSON size bound')
    return json.loads(p.read_text())
def save(path,value):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as out:json.dump(value,out,indent=2,allow_nan=False);out.write('\n')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def identifier(value):
    require(isinstance(value,str) and re.fullmatch(r'force-probe-[a-z0-9][a-z0-9-]{0,38}',value),'Unique bounded force-probe-... identifier required')
    return value

def tasks(ident):
    identifier(ident)
    return [{'id':ident+'-w'+str(w)+'-b'+str(b),'writers':w,'blockBytes':b,
             'fileBytesPerWriter':PREALLOC_BLOCKS*b,'warmup':WARMUP,'measurements':MEASUREMENTS,
             'plannedDataWriteBytes':w*(PREALLOC_BLOCKS+WARMUP+MEASUREMENTS)*b,
             'plannedForceCalls':w*(1+WARMUP+MEASUREMENTS),
             'maximumOutputBytes':w*(PREALLOC_BLOCKS*b+MAX_CSV)+2*MAX_META}
            for w in (1,3) for b in BLOCKS]

def prerequisite(required=False):
    require(REPO is not None,'Local repository required for predecessor archive verification')
    path=CPU_BASE/'capacity_client_driver_abab.py'
    require(sha(path)==CLIENT_CONTROLLER_SHA,'Frozen client ABAB source changed')
    c=module('frozen_client_abab_force_prerequisite',path)
    plan_path=REPO/'evidence/2026-10-24/runpod-cpu/registrations'/(c.MATRIX_ID+'.json')
    matrix=REPO/'evidence/2026-10-24/runpod-cpu/matrices'/c.MATRIX_ID
    missing=[str(p) for p in [plan_path]+[matrix/'points'/(t['id']+'.json') for t in c.matrix_tasks()] if not p.is_file()]
    if missing:
        require(not required,'All four clientABAB attempts must close before registration: '+json.dumps(missing))
        return {'ready':False,'missing':missing}
    plan=c.validate_matrix(c.read(plan_path));points=c.completed_prefix(matrix,plan,4);rows=[]
    for child,point in zip(plan['trialPlans'],points):
        local=Path(point['analysisDirectory']);trial=local/'raw/evidence/runs'/child['jobId']
        receipt_path=matrix/'point-executions'/child['jobId']/'receipt.json';receipt=read(receipt_path)
        require(receipt.get('passed') is True and receipt.get('point')==point,'Client per-point closure changed')
        verifier_path=local/'raw/pinned-tools/verify-client-driver-config.py'
        require(sha(verifier_path)==child['mixedVerifier']['sha256'],'Mixed-source verifier changed')
        verifier=module('force_prereq_mixed_'+child['task']['stage'],verifier_path)
        legacy_path=local/'raw/pinned-tools/scripts/verify-capacity-config.py'
        require(sha(legacy_path)==verifier.NODE_VERIFIER_SHA256,'Original node helper changed')
        checked=verifier.verify(child,trial,module('force_prereq_node_'+child['task']['stage'],legacy_path))
        require(checked==read(trial/'configuration-verification.json') and not checked['configurationOnly'],'Actual client closure differs')
        stopped=read(local/'raw/all-owned-processes-stopped.json')
        require(stopped.get('passed') is True and stopped.get('records') and all(r.get('stopped') is True for r in stopped['records']),'Prior owned process cleanup incomplete')
        rows.append({'jobId':child['jobId'],'completionSha256':value_sha(point['completion']),
                     'archiveSha256':point['completion']['archive']['sha256'],'archivePath':point['completion']['archive']['path'],
                     'analysisSha256':point['analysisSummarySha256'],'pointSha256':sha(matrix/'points'/(child['jobId']+'.json')),
                     'receiptSha256':sha(receipt_path),'configurationSha256':sha(trial/'configuration-verification.json'),
                     'ownedStopSha256':sha(local/'raw/all-owned-processes-stopped.json')})
    return {'ready':True,'controllerSha256':CLIENT_CONTROLLER_SHA,'matrixId':c.MATRIX_ID,
            'planSha256':sha(plan_path),'points':rows,'scope':'All4 canonical/valid/zeroUNKNOWN clientABAB attempts, raw/native archives and actual mixed-source/owned-stop closure. Valid overload is retained; not performance promotion.'}

def artifact():
    manifest_path=BASE/'manifest.json';require(sha(manifest_path)==PREPARATION_SHA,'Frozen preparation manifest changed')
    manifest=read(manifest_path);require(manifest['sources']['ForcePathProbe.java']['sha256']==SOURCE_SHA and sha(BASE/'ForcePathProbe.java')==SOURCE_SHA,'Frozen Java source changed')
    classes=manifest['runtimeClasses']
    require(classes and 'ForcePathProbe.class' in classes and all(re.fullmatch(r'ForcePathProbe(?:\$[A-Za-z0-9]+)?\.class',n) for n in classes),'Exact runtime class namespace required; test clock guard excluded')
    payloads={'ForcePathProbe.java':(BASE/'ForcePathProbe.java').read_bytes(),'preparation-manifest.json':manifest_path.read_bytes()}
    for name,row in classes.items():
        p=BASE/'build'/name;require(sha(p)==row['sha256'] and p.stat().st_size==row['bytes'],'Compiled runtime class changed')
        data=p.read_bytes();require(data[:4]==b'\xca\xfe\xba\xbe' and struct.unpack('>H',data[6:8])[0]==65,'Java21 class format required')
        payloads['classes/'+name]=data
    stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as out:
        for name,data in sorted(payloads.items()):
            info=tarfile.TarInfo(name);info.mode=0o644;info.size=len(data);info.mtime=0;out.addfile(info,io.BytesIO(data))
    data=stream.getvalue()
    return {'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
            'files':{n:{'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for n,v in payloads.items()}},data

def plan_identity(plan):return value_sha({k:v for k,v in plan.items() if k!='planSha256'})
def draft(ident='force-probe-cpu-20261024-r1',prior=None):
    meta,_=artifact();manifest_source=(BASE/'manifest.json').read_text();ident=identifier(ident)
    p={'schemaVersion':1,'role':'synthetic-filechannel-force-diagnostic-single-jvm-threads','id':ident,'registeredAtUtc':utc(),
       'hostname':HOST,'podId':POD,'controllerSha256':sha(__file__),'javaSourceSha256':SOURCE_SHA,
       'preparationManifestSource':manifest_source,'preparationManifestSha256':PREPARATION_SHA,'artifact':meta,
       'prerequisite':prerequisite() if prior is None else prior,'order':tasks(ident),
       'globalPlannedDataWriteBytes':sum(t['plannedDataWriteBytes'] for t in tasks(ident)),
       'globalPlannedForceCalls':sum(t['plannedForceCalls'] for t in tasks(ident)),
       'admissionMsPerPoint':ADMISSION_MS,'supervisorSecondsPerPoint':PROCESS_SECONDS,'globalSeconds':MATRIX_SECONDS,
       'minimumFreeBytes':MIN_FREE,'maximumCsvBytesPerWriter':MAX_CSV,'maximumJsonBytesPerFile':MAX_META,
       'maximumChildLogBytesPerPoint':MAX_LOG,'maximumGlobalOutputBytes':sum(t['maximumOutputBytes']+MAX_LOG for t in tasks(ident)),
       'java':str(JAVA),'artifactRoot':str(ROOT/'force-probe-artifacts'/ident),'dataParent':str(ROOT/'force-path-probes'),
       'control':str(CONTROL/ident),'localArtifact':str(BASE/('artifact-'+meta['sha256'][:16]+'.tar')),
       'scope':'Exploratory synthetic FileChannel write+force(true), not trading/Aeron or pure fsync/CPU exclusivity. Threads1/3 in one JVM; fixed order can confound host/JIT drift. Preallocation/warmup/measurement retained separately; no Linux result exists until actual run.',
       'recovery':'One immutable attempt; no auto retry/resubmit/resume/prune. Query same controller after transport ambiguity. Any partial/failure/unproven owned stop permanently blocks later points.'}
    p['planSha256']=plan_identity(p);return validate_plan(p)

def validate_plan(p):
    require(p.get('schemaVersion')==1 and p.get('role')=='synthetic-filechannel-force-diagnostic-single-jvm-threads','Wrong diagnostic schema')
    ident=identifier(p.get('id'));require(p.get('hostname')==HOST and p.get('podId')==POD and p.get('java')==str(JAVA),'Wrong existing CPU target')
    require(p.get('controllerSha256')==sha(__file__) and p.get('javaSourceSha256')==SOURCE_SHA,'Controller/source changed')
    require(p.get('preparationManifestSha256')==PREPARATION_SHA and hashlib.sha256(p.get('preparationManifestSource','').encode()).hexdigest()==PREPARATION_SHA,'Preparation manifest identity differs')
    m=json.loads(p['preparationManifestSource']);expected={'ForcePathProbe.java':m['sources']['ForcePathProbe.java'],'preparation-manifest.json':{'bytes':len(p['preparationManifestSource'].encode()),'sha256':PREPARATION_SHA}}
    expected.update({'classes/'+n:r for n,r in m['runtimeClasses'].items()})
    require(p.get('artifact',{}).get('files')==expected and type(p['artifact'].get('bytes')) is int and 0<p['artifact']['bytes']<1024**2 and re.fullmatch('[a-f0-9]{64}',p['artifact'].get('sha256','')),'Exact source/manifest/class artifact inventory required')
    require(p.get('order')==tasks(ident) and p.get('globalPlannedDataWriteBytes')==85164032 and p.get('globalPlannedForceCalls')==3376,'Exact bounded eight-point matrix/counts required')
    for key,value in {'admissionMsPerPoint':ADMISSION_MS,'supervisorSecondsPerPoint':PROCESS_SECONDS,'globalSeconds':MATRIX_SECONDS,
        'minimumFreeBytes':MIN_FREE,'maximumCsvBytesPerWriter':MAX_CSV,'maximumJsonBytesPerFile':MAX_META,'maximumChildLogBytesPerPoint':MAX_LOG,
        'maximumGlobalOutputBytes':sum(t['maximumOutputBytes']+MAX_LOG for t in tasks(ident)),
        'artifactRoot':str(ROOT/'force-probe-artifacts'/ident),'dataParent':str(ROOT/'force-path-probes'),'control':str(CONTROL/ident)}.items():
        require(p.get(key)==value,'Diagnostic bound/path differs: '+key)
    require(p.get('planSha256')==plan_identity(p),'Registered plan SHA differs')
    prior=p.get('prerequisite',{});require(type(prior.get('ready')) is bool,'Explicit predecessor readiness required')
    if prior['ready']:
        require(prior.get('controllerSha256')==CLIENT_CONTROLLER_SHA and prior.get('matrixId')==PREDECESSOR_ID
                and [r.get('jobId') for r in prior.get('points',[])]==list(PREDECESSOR_POINTS),'Full ordered4 predecessor closure required')
        for row in prior['points']:
            for key in ('completionSha256','archiveSha256','analysisSha256','pointSha256','receiptSha256','configurationSha256','ownedStopSha256'):
                require(re.fullmatch('[a-f0-9]{64}',row.get(key,'')),'Incomplete predecessor receipt SHA')
            require(row.get('archivePath')=='/workspace/vectormatch-cpu-archives/'+row.get('jobId','')+'.tar.gz','Wrong predecessor archive path')
    return p

def enable_pidfd():
    native=callable(getattr(os,'pidfd_open',None)) and callable(getattr(signal,'pidfd_send_signal',None))
    if not native:
        require(platform.system()=='Linux' and platform.machine()=='x86_64','Python3.8 pidfd mapping supports Linux x86_64 only')
        libc=ctypes.CDLL(None,use_errno=True);libc.syscall.restype=ctypes.c_long
        def syscall(n,*args):
            value=libc.syscall(ctypes.c_long(n),*args)
            if value<0:raise OSError(ctypes.get_errno(),os.strerror(ctypes.get_errno()))
            return int(value)
        if not callable(getattr(os,'pidfd_open',None)):
            def pidfd_open(pid,flags=0):
                require(type(pid) is int and pid>1 and flags==0,'Invalid pidfd_open')
                fd=syscall(434,ctypes.c_int(pid),ctypes.c_uint(0));os.set_inheritable(fd,False);return fd
            os.pidfd_open=pidfd_open
        if not callable(getattr(signal,'pidfd_send_signal',None)):
            def pidfd_send_signal(fd,sig,siginfo=None,flags=0):
                require(type(fd) is int and fd>=0 and siginfo is None and flags==0,'Unsupported pidfd signal')
                syscall(424,ctypes.c_int(fd),ctypes.c_int(int(sig)),ctypes.c_void_p(),ctypes.c_uint(0))
            signal.pidfd_send_signal=pidfd_send_signal
    fd=os.pidfd_open(os.getpid())
    try:signal.pidfd_send_signal(fd,0)
    finally:os.close(fd)
    return {'mode':'native' if native else 'linux-x86_64-syscall-python38','selfSignalZeroVerified':True,
            'scope':'Copied explicit syscall numbers434/424 from frozenCPUv2 controller89a5517; no numericPID kill or process-group signal'}

def command_sha(args):return hashlib.sha256(b''.join(os.fsencode(a)+b'\0' for a in args)).hexdigest()
def identity(pid):
    require(type(pid) is int and pid>1,'Invalid owned PID')
    try:
        stat=(PROC/str(pid)/'stat').read_text().rsplit(')',1)[1].split();raw=(PROC/str(pid)/'cmdline').read_bytes()
    except FileNotFoundError:return None
    require(len(raw)<=65536,'Owned argv bound')
    return {'pid':pid,'startTicks':int(stat[19]),'state':stat[0],'arguments':[os.fsdecode(x) for x in raw.split(b'\0') if x],
            'commandSha256':hashlib.sha256(raw).hexdigest()}
def state(record):
    actual=identity(record['pid'])
    if actual is None or actual['startTicks']!=record['startTicks'] or actual['state']=='Z':return 'stopped'
    require(all(actual[k]==record[k] for k in ('arguments','commandSha256')),'Owned PID argv changed; cleanup unproven')
    return 'running'
def await_identity(child,args):
    end=time.monotonic()+2
    while True:
        actual=identity(child.pid)
        if actual and actual['state']!='Z' and actual['arguments']==args and actual['commandSha256']==command_sha(args):
            second=identity(child.pid);require(second is not None and second['state']!='Z' and
                all(second[k]==actual[k] for k in ('pid','startTicks','arguments','commandSha256')),'Owned launch identity changed between observations')
            return {**actual,'verifiedAtUtc':utc(),'twoMatchingObservations':True}
        require(child.poll() is None and time.monotonic()<end,'Could not establish exact launched JVM identity; no next point')
        time.sleep(.01)
def stop_owned(record):
    if state(record)=='stopped':return {'stopped':True,'pid':record['pid'],'startTicks':record['startTicks'],'signals':[]}
    fd=os.pidfd_open(record['pid']);sent=[]
    try:
        for sig in (signal.SIGTERM,signal.SIGKILL):
            if state(record)=='stopped':break
            # Re-read exact birth+argv after pidfd open and immediately before each signal.
            require(state(record)=='running','Owned signal target changed')
            try:signal.pidfd_send_signal(fd,sig);sent.append(int(sig))
            except ProcessLookupError:pass
            end=time.monotonic()+2
            while state(record)=='running' and time.monotonic()<end:time.sleep(.05)
        require(state(record)=='stopped','Owned JVM stop remains unproven; later points forbidden')
        return {'stopped':True,'pid':record['pid'],'startTicks':record['startTicks'],'signals':sent}
    finally:os.close(fd)

def mount_type(path):
    target=str(path);best=('',None)
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        a,b=line.split(' - ',1);mount=a.split()[4].replace('\\040',' ')
        if (target==mount or target.startswith(mount.rstrip('/')+'/')) and len(mount)>len(best[0]):best=(mount,b.split()[0])
    return best[1]
def no_symlinks(path):require(not any(p.is_symlink() for p in [path]+list(path.parents)),'Symlink destination ancestor')
def idle_check():
    require(platform.system()=='Linux' and platform.node()==HOST,'Wrong existing Linux CPU host')
    found=[]
    for p in PROC.iterdir():
        if not p.name.isdigit():continue
        try:raw=(p/'cmdline').read_bytes()
        except FileNotFoundError:continue
        require(len(raw)<=131072,'Process argv bound')
        args=raw.split(b'\0')
        if args and args[0].split(b'/')[-1]==b'java' and any(a.startswith((b'io.vectormatch.',b'org.openjdk.jmh.',b'ForcePathProbe')) for a in args):
            found.append(int(p.name))
    require(not found,'Project/JMH/probe JVM active; no diagnostic launch: '+str(found))
    require(mount_type(ROOT)=='overlay','Probe must use the declared overlay, not tmpfs/FUSE')
    require(os.statvfs(ROOT).f_bavail*os.statvfs(ROOT).f_frsize>=MIN_FREE,'Free-space admission floor')
    return {'passed':True,'checkedAtUtc':utc(),'hostname':platform.node(),'projectJvmPids':found,'filesystem':'overlay',
            'scope':'Fresh JVM identity inventory only; does not prove filesystem/CPU exclusivity or absence of other users/preparation work'}

def java_arguments(p,t):
    return [str(JAVA),'-Xms32m','-Xmx64m','-cp',p['artifactRoot']+'/classes','ForcePathProbe',
        '--output-dir',p['dataParent']+'/'+t['id'],'--block-bytes',str(t['blockBytes']),'--writers',str(t['writers']),
        '--file-bytes-per-writer',str(t['fileBytesPerWriter']),'--warmup-iterations',str(WARMUP),'--measurement-iterations',str(MEASUREMENTS),
        '--max-total-write-bytes',str(t['plannedDataWriteBytes']),'--max-duration-ms',str(ADMISSION_MS),'--min-free-bytes',str(MIN_FREE),'--scope-label','diagnostic']

def check_artifact(p,path):
    require(set(str(f.relative_to(path)) for f in path.rglob('*') if f.is_file())==set(p['artifact']['files']),'Actual artifact inventory differs')
    for name,row in p['artifact']['files'].items():
        target=path/name;require(sha(target)==row['sha256'] and target.stat().st_size==row['bytes'],'Actual class/source bytes differ')
    return {'passed':True,'files':p['artifact']['files'],'checkedAtUtc':utc()}
def stage_artifact(p,archive):
    target=Path(p['artifactRoot']);no_symlinks(target);require(not target.exists(),'Artifact attempt already exists; no overwrite/retry')
    require(sha(archive)==p['artifact']['sha256'] and archive.stat().st_size==p['artifact']['bytes'],'Uploaded artifact changed')
    with tarfile.open(archive,'r:') as stream:
        members=stream.getmembers();expected=p['artifact']['files']
        require(len(members)==len(expected) and {m.name for m in members}==set(expected),'Artifact tar inventory differs')
        require(all(m.isreg() and not m.issparse() and m.mode==0o644 and m.size==expected[m.name]['bytes']
                    and str(PurePosixPath(m.name))==m.name and not PurePosixPath(m.name).is_absolute() and '..' not in PurePosixPath(m.name).parts for m in members),'Unsafe artifact tar')
        target.parent.mkdir(exist_ok=True);target.mkdir()
        for member in members:
            out=target/member.name;out.parent.mkdir(parents=True,exist_ok=True)
            with out.open('xb') as dest,stream.extractfile(member) as src:dest.write(src.read())
            os.chmod(out,0o444)
    return check_artifact(p,target)


def validate_output(p,t,path):
    expected={'configuration.json','success.json'}|{'writer-'+str(i)+'.csv' for i in range(t['writers'])}|{'synthetic-force-writer-'+str(i)+'.data' for i in range(t['writers'])}
    require(path.is_dir() and not path.is_symlink() and {f.name for f in path.iterdir()}==expected,'Complete exact Java output set required; failure/extra output retained but invalid')
    require(all(f.is_file() and not f.is_symlink() for f in path.iterdir()),'Only regular flat diagnostic outputs allowed')
    require(sum(f.stat().st_size for f in path.iterdir())<=t['maximumOutputBytes'],'Point output cap')
    config=read(path/'configuration.json',MAX_META);success=read(path/'success.json',MAX_META)
    for key,value in {'schemaVersion':1,'label':'diagnostic','writers':t['writers'],'blockBytes':t['blockBytes'],'fileBytesPerWriter':t['fileBytesPerWriter'],
        'warmupIterationsPerWriter':WARMUP,'measurementIterationsPerWriter':MEASUREMENTS,'maxTotalWriteBytes':t['plannedDataWriteBytes'],
        'plannedTotalWriteBytes':t['plannedDataWriteBytes'],'plannedForceCalls':t['plannedForceCalls'],'maxDurationMs':ADMISSION_MS,'minFreeBytes':MIN_FREE,'forceMetadata':True}.items():
        require(config.get(key)==value and type(config.get(key))==type(value),'Actual probe option differs: '+key)
    require(config.get('os',{}).get('name')=='Linux' and config.get('filesystem',{}).get('type')=='overlay','Actual Linux overlay evidence required')
    require('one JVM' in config.get('writerModel',''),'Single-JVM thread scope missing')
    require(success.get('passed') is True and success.get('allWorkerThreadsTerminated') is True,'Successful JVM worker shutdown missing')
    total_bytes=total_forces=0;writer_rows=[]
    for writer in range(t['writers']):
        source=path/('writer-'+str(writer)+'.csv');require(source.stat().st_size<=MAX_CSV,'CSV byte cap')
        with source.open(newline='') as stream:
            reader=csv.DictReader(stream);require(reader.fieldnames==HEADER,'Exact raw schema required');rows=list(reader)
        phases=[('preallocation',-1,0,t['fileBytesPerWriter'])]+[('warmup',i,i%PREALLOC_BLOCKS*t['blockBytes'],t['blockBytes']) for i in range(WARMUP)]+[('measurement',i,i%PREALLOC_BLOCKS*t['blockBytes'],t['blockBytes']) for i in range(MEASUREMENTS)]
        require(len(rows)==len(phases),'All raw preallocation/warmup/measurement rows required')
        previous_end=None;written=forces=0
        for row,(phase,index,offset,size) in zip(rows,phases):
            require(None not in row and None not in row.values(),'Malformed CSV width')
            for key,value in {'schema_version':1,'writer_id':writer,'iteration':index,'offset_bytes':offset,'requested_bytes':size,'written_bytes':size,'force_calls':1}.items():
                require(row[key]==str(value),'Raw row byte/count/offset mismatch: '+key)
            require(row['phase']==phase and row['status']=='complete' and row['deadline_exceeded']=='false' and row['error']=='','Failed/reordered raw phase')
            require(int(row['write_calls'])>=1,'Write call count absent')
            write_ns,force_ns,total_ns,start=[int(row[n]) for n in ('write_elapsed_ns','force_elapsed_ns','total_elapsed_ns','monotonic_start_ns')]
            require(min(write_ns,force_ns,total_ns)>=0 and total_ns==write_ns+force_ns and (previous_end is None or start>=previous_end),'Raw clock/timing conservation differs')
            previous_end=start+total_ns
            stamp=dt.datetime.fromisoformat(row['wall_utc'].replace('Z','+00:00'));require(stamp.tzinfo is not None,'UTC timestamp missing')
            if row['thread_cpu_ns']!='':require(int(row['thread_cpu_ns'])>=0,'Invalid thread CPU counter')
            written+=size;forces+=1
        data=path/('synthetic-force-writer-'+str(writer)+'.data');require(data.stat().st_size==t['fileBytesPerWriter'],'Fixed data extent differs')
        writer_rows.append({'writerId':writer,'rows':len(rows),'measurementRows':MEASUREMENTS,'writtenBytes':written,'forceCalls':forces,'csvSha256':sha(source),'dataSha256':sha(data)})
        total_bytes+=written;total_forces+=forces
    require(total_bytes==success.get('totalWrittenBytes')==t['plannedDataWriteBytes'] and total_forces==success.get('forceTrueCalls')==t['plannedForceCalls'],'Whole-run byte/force counts differ')
    require(len(success.get('writers',[]))==t['writers'] and len(success.get('dataFiles',[]))==t['writers'],'Writer/data result set differs')
    for i,row in enumerate(writer_rows):
        require(success['writers'][i]=={'writerId':i,'writtenBytes':row['writtenBytes'],'forceCalls':row['forceCalls'],'preallocationRows':1,'warmupRows':WARMUP,'measurementRows':MEASUREMENTS},'Writer result differs')
        require(success['dataFiles'][i]=={'name':'synthetic-force-writer-'+str(i)+'.data','bytes':t['fileBytesPerWriter'],'sha256':row['dataSha256']},'Post-readback hash differs')
    return {'passed':True,'point':t,'writers':writer_rows,'totalDataWrittenBytes':total_bytes,'forceTrueCalls':total_forces,
            'inputSha256':{f.name:sha(f) for f in path.iterdir()},'scope':'Exploratory synthetic force distribution; all phases retained separately. Not trading latency, pure fsync time or exclusive disk/CPU attribution.'}


def remote_module():return module('force_probe_existing_cpu_remote',CPU_BASE/'remote.py')
def remote_predecessors(p):
    require(p['prerequisite'].get('ready') is True,'Predecessor closure required')
    for row in p['prerequisite']['points']:
        completion=read(CONTROL/row['jobId']/'completion.json')
        require(value_sha(completion)==row['completionSha256'] and completion.get('matrixTrialPassed') is True
                and completion.get('allOwnedProcessesStopped') is True and completion.get('archiveComplete') is True,'Remote client predecessor completion changed')
        # All four full archives are rehashed LOCALLY by prerequisite() before launch.
        # Remote scope is immutable completion/owned-stop receipts plus a fresh idle check;
        # no redundant multi-GB FUSE archive scan is included in this diagnostic window.

def point_run(p,t,global_deadline):
    control=Path(p['control'])/'points'/t['id'];output=Path(p['dataParent'])/t['id']
    require(not control.exists() and not output.exists() and not output.is_symlink(),'Point already attempted; no resubmit')
    require(time.monotonic()+PROCESS_SECONDS<=global_deadline,'Global budget cannot admit another complete point')
    control.mkdir(parents=True,exist_ok=False)
    save(control/'attempted.json',{'point':t,'planSha256':p['planSha256'],'dataTargetAbsentBeforeLaunch':True,'startedAtUtc':utc()})
    receipt={'passed':False,'point':t,'startedAtUtc':utc(),'cleanup':None};child=None;record=None
    try:
        save(control/'idle-before.json',idle_check())
        save(control/'artifact-before.json',check_artifact(p,Path(p['artifactRoot'])))
        require(not any(os.environ.get(key) for key in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS')),'Hidden JVM launch options refused; no environment values recorded')
        args=java_arguments(p,t);start=time.monotonic()
        with (control/'jvm.log').open('xb') as log:
            child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            record=await_identity(child,args);save(control/'process.json',record)
            while child.poll() is None:
                require(time.monotonic()<min(start+PROCESS_SECONDS,global_deadline),'Supervisor deadline; cancel only this exact owned JVM')
                require((control/'jvm.log').stat().st_size<=MAX_LOG,'JVM log cap')
                if output.exists():
                    require(not output.is_symlink(),'Unexpected output symlink')
                    entries=list(output.iterdir());require(all(f.is_file() and not f.is_symlink() for f in entries),'Unexpected output entry')
                    require(sum(f.stat().st_size for f in entries)<=t['maximumOutputBytes'],'Live output byte cap')
                    for file in entries:
                        if file.suffix=='.csv':require(file.stat().st_size<=MAX_CSV,'Live CSV cap')
                        elif file.suffix=='.json':require(file.stat().st_size<=MAX_META,'Live JSON cap')
                        elif file.suffix=='.data':require(file.stat().st_size<=t['fileBytesPerWriter'],'Live data extent cap')
                        else:raise ValueError('Unexpected output suffix')
                time.sleep(.05)
            receipt['exitCode']=child.returncode
        require((control/'jvm.log').stat().st_size<=MAX_LOG,'Final JVM log cap')
        require(child.returncode==0,'Probe exited nonzero; partial files retained')
        receipt['cleanup']=stop_owned(record)
        receipt['outputValidation']=validate_output(p,t,output)
        save(control/'artifact-after.json',check_artifact(p,Path(p['artifactRoot'])))
        require(time.monotonic()<=global_deadline,'Global diagnostic deadline')
        receipt['passed']=True
    except BaseException as failure:
        receipt.update(errorType=type(failure).__name__,error=str(failure),traceback=traceback.format_exc())
    finally:
        if child is not None:
            try:
                if record is None:
                    # Never signal an unverified launch. Recover only an exact two-read argv/birth identity.
                    record=await_identity(child,java_arguments(p,t));save(control/'recovered-process.json',record)
                receipt['cleanup']=stop_owned(record)
                child.wait(timeout=1)
            except BaseException as failure:
                receipt['passed']=False;receipt['cleanup']={'stopped':False,'errorType':type(failure).__name__,'error':str(failure)}
        else:receipt['cleanup']={'stopped':True,'launched':False,'scope':'Popen was never called successfully'}
        receipt['completedAtUtc']=utc();save(control/'receipt.json',receipt)
    return receipt

def archive_results(p,points):
    control=Path(p['control']);files={}
    # The live launcher log and completion marker are excluded. All Java logs/CSV/data are closed first.
    for path in sorted(control.rglob('*')):
        require(not path.is_symlink(),'Unexpected owned control symlink; archive closure unproven')
        if path.is_file() and not path.is_symlink() and path.name not in ('controller.log','completion.json','output.tar.gz','output.tar.gz.partial','output-manifest.json'):
            files['control/'+str(path.relative_to(control))]=path
    for point in points:
        ident=point['point']['id'];data=Path(p['dataParent'])/ident
        if (control/'points'/ident/'attempted.json').is_file() and data.exists():
            for path in sorted(data.iterdir()):
                require(path.is_file() and not path.is_symlink(),'Unexpected partial data output; archive closure unproven')
                files['runs/'+ident+'/'+path.name]=path
    require(sum(path.stat().st_size for path in files.values())<=p['maximumGlobalOutputBytes']+2*1024**2,'Archive logical byte cap')
    manifest={name:{'bytes':path.stat().st_size,'sha256':sha(path)} for name,path in files.items()}
    save(control/'output-manifest.json',{'files':manifest,'scope':'Closed synthetic files and immutable controller inputs only; no original state/native/PGDATA. Live controller carrier log excluded.'})
    files['output-manifest.json']=control/'output-manifest.json'
    archive=control/'output.tar.gz';partial=control/'output.tar.gz.partial'
    with tarfile.open(partial,'x:gz',compresslevel=1) as stream:
        for name,path in sorted(files.items()):stream.add(path,arcname=name,recursive=False)
    with tarfile.open(partial,'r:gz') as stream:
        members=stream.getmembers();require({m.name for m in members}==set(files) and len(members)==len(files),'Archive file closure differs')
        for member in members:
            require(member.isreg() and not member.issparse(),'Unexpected archive member')
            data=stream.extractfile(member);h=hashlib.sha256()
            for chunk in iter(lambda:data.read(65536),b''):h.update(chunk)
            require(h.hexdigest()==sha(files[member.name]),'Archived bytes changed')
    partial.rename(archive)
    return {'path':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive),'manifestSha256':sha(control/'output-manifest.json'),'files':len(files)}

def install_cancellation_handlers():
    previous={};cancelled=[False]
    def cancel(signum,frame):
        if not cancelled[0]:
            cancelled[0]=True
            raise InterruptedError('Controller cancellation signal '+str(signum)+'; cleanup exact owned JVM before closing')
    for signum in (signal.SIGINT,signal.SIGTERM):
        previous[signum]=signal.signal(signum,cancel)
    return previous

def closed_attempts(p):
    """Disk-backed stop proof: missing receipt after any attempted launch is unproven."""
    closed=[];unproven=[];attempted=[]
    for t in p['order']:
        path=Path(p['control'])/'points'/t['id']
        if not path.exists():continue
        attempted.append(t['id'])
        try:
            r=read(path/'receipt.json')
            require(r.get('point')==t and r.get('cleanup',{}).get('stopped') is True,'Owned stop not proven')
            record_path=path/'process.json'
            if not record_path.exists():record_path=path/'recovered-process.json'
            if record_path.exists():require(state(read(record_path))=='stopped','Owned JVM remains alive')
            closed.append(r)
        except (OSError,ValueError,TypeError,KeyError) as error:
            unproven.append({'id':t['id'],'error':str(error)})
    return closed,attempted,unproven

def worker(plan_path):
    p=validate_plan(read(plan_path));control=Path(p['control'])
    require(Path(plan_path).resolve()==control/'plan.json','Worker must use its unique registered control plan')
    require(not (control/'worker-started.json').exists(),'Worker already attempted; no resume/retry')
    save(control/'worker-started.json',{'startedAtUtc':utc(),'planSha256':p['planSha256'],'controllerIdentity':identity(os.getpid())})
    result={'passed':False,'id':p['id'],'planSha256':p['planSha256'],'startedAtUtc':utc(),'points':[],'allMeasuredJvmsStopped':True,'archiveComplete':False}
    global_deadline=time.monotonic()+MATRIX_SECONDS;handlers=install_cancellation_handlers()
    try:
        pidfd=enable_pidfd();fresh=idle_check();remote_predecessors(p)
        save(control/'preflight.json',{'pidfd':pidfd,'idle':fresh,'remotePredecessorCompletionStopReceiptsVerified':True,'localFullArchivesRehashedBeforeLaunch':True,'checkedAtUtc':utc()})
        for t in p['order']:require(not (Path(p['dataParent'])/t['id']).exists(),'An immutable data identity already exists')
        save(control/'artifact-staging.json',stage_artifact(p,control/'artifact.tar'))
        data_parent=Path(p['dataParent']);no_symlinks(data_parent);data_parent.mkdir(exist_ok=True)
        for t in p['order']:
            point=point_run(p,t,global_deadline);result['points'].append(point)
            require(point.get('passed') is True and point.get('cleanup',{}).get('stopped') is True,'Failed/partial point: all later points remain unlaunched')
        result['passed']=True
    except BaseException as failure:result.update(errorType=type(failure).__name__,error=str(failure),traceback=traceback.format_exc())
    finally:
        closed,attempted,unproven=closed_attempts(p)
        result['allMeasuredJvmsStopped']=not unproven
        result['unprovenStopAttempts']=unproven
        result['unlaunchedIds']=[t['id'] for t in p['order'] if t['id'] not in attempted]
        if len(closed)!=len(result['points']) or unproven:result['passed']=False
        # Recover closed partial attempts for archive preservation even if a caller failed after receipt write.
        result['points']=closed if not unproven else result['points']
        result['completedAtUtc']=utc();save(control/'worker-receipt.json',result)
        if result['allMeasuredJvmsStopped']:
            try:result['archive']=archive_results(p,result['points']);result['archiveComplete']=True
            except BaseException as failure:result['passed']=False;result['archiveError']={'type':type(failure).__name__,'error':str(failure)}
        save(control/'completion.json',result)
        for signum,handler in handlers.items():signal.signal(signum,handler)
    return 0 if result['passed'] else 1

def execute(plan_path,idle_window_confirmed=False):
    p=validate_plan(read(plan_path));require(idle_window_confirmed,'Root must close dependency/native preparation and explicitly confirm the idle window')
    require(p['prerequisite'].get('ready') is True and prerequisite(required=True)==p['prerequisite'],'Local completed4client predecessor evidence changed')
    meta,payload=artifact();require(meta==p['artifact'],'Local prepared artifact changed')
    remote=remote_module();control=p['control']
    preflight="from pathlib import Path\nimport platform\nassert platform.node()==HOST\np=Path(CONTROL)\nassert not any(x.is_symlink() for x in [p]+list(p.parents))\np.mkdir(exist_ok=False)\nprint(p)\n"
    checked=remote.run('python3 -B -',input='HOST='+repr(HOST)+'\nCONTROL='+repr(control)+'\n'+preflight,timeout=30)
    require(checked.returncode==0,'Unique control create failed; query SAME identity; never retry launch: '+checked.stderr)
    bundle=Path(p['localArtifact'])
    if bundle.exists():require(sha(bundle)==meta['sha256'],'Existing immutable local artifact changed')
    else:
        with bundle.open('xb') as stream:stream.write(payload)
    for source,name in ((Path(__file__),'controller.py'),(Path(plan_path),'plan.json'),(bundle,'artifact.tar')):
        transferred=remote.upload(source,control+'/'+name);require(transferred.returncode==0,'Transfer ambiguous/failed; query same job; no reissue')
    launch="""from pathlib import Path
import subprocess,json,hashlib,os,time
p=Path(CONTROL);plan=json.loads((p/'plan.json').read_text())
assert hashlib.sha256((p/'controller.py').read_bytes()).hexdigest()==plan['controllerSha256']
with (p/'launch-attempt.json').open('x') as f:json.dump({'planSha256':plan['planSha256'],'idleWindowConfirmedByCaller':True},f)
args=['python3','-B',str(p/'controller.py'),'--worker','--plan',str(p/'plan.json')]
with (p/'controller.log').open('xb') as log:
 child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 end=time.monotonic()+2
 while True:
  stat=(Path('/proc')/str(child.pid)/'stat').read_text().rsplit(')',1)[1].split()
  raw=(Path('/proc')/str(child.pid)/'cmdline').read_bytes()
  expected=hashlib.sha256(b''.join(os.fsencode(a)+bytes([0]) for a in args)).hexdigest()
  if stat[0]!='Z' and hashlib.sha256(raw).hexdigest()==expected:break
  assert child.poll() is None and time.monotonic()<end
  time.sleep(.01)
 record={'pid':child.pid,'startTicks':int(stat[19]),'arguments':args,'commandSha256':expected,'planSha256':plan['planSha256']}
 with (p/'launch.json').open('x') as f:json.dump(record,f)
 print(json.dumps(record))
"""
    answer=remote.run('python3 -B -',input='CONTROL='+repr(control)+'\n'+launch,timeout=30)
    require(answer.returncode==0,'Launch response ambiguous; query SAME controller, never resubmit: '+answer.stderr)
    print(answer.stdout);return 0

def status(p):
    code="""from pathlib import Path
import json,hashlib
p=Path(CONTROL);out={'controlExists':p.is_dir()}
for name in ('launch.json','completion.json'):
 if (p/name).is_file():out[name]=json.loads((p/name).read_text())
record=out.get('launch.json');out['controllerIdentityAlive']=None
if record:
 try:
  s=(Path('/proc')/str(record['pid'])/'stat').read_text().rsplit(')',1)[1].split()
  raw=(Path('/proc')/str(record['pid'])/'cmdline').read_bytes()
  out['controllerIdentityAlive']=s[0]!='Z' and int(s[19])==record['startTicks'] and hashlib.sha256(raw).hexdigest()==record['commandSha256']
 except FileNotFoundError:out['controllerIdentityAlive']=False
print(json.dumps(out))
"""
    response=remote_module().run('python3 -B -',input='CONTROL='+repr(p['control'])+'\n'+code,timeout=30)
    require(response.returncode==0,'Status failed; no reissue');return json.loads(response.stdout)

def collect(p):
    seen=status(p);completion=seen.get('completion.json',{})
    require(seen.get('controllerIdentityAlive') is False and completion.get('planSha256')==p['planSha256']
            and completion.get('archiveComplete') is True and completion.get('allMeasuredJvmsStopped') is True,'Full stopped diagnostic archive required')
    info=completion['archive'];require(info['path']==p['control']+'/output.tar.gz' and 0<info['bytes']<=p['maximumGlobalOutputBytes']+2*1024**2,'Archive path/size differs')
    local=BASE/'collected'/p['id'];local.mkdir(parents=True,exist_ok=False);archive=local/'output.tar.gz'
    with archive.open('xb') as out:
        remote=remote_module();done=subprocess.run([*remote.sshargs(),'cat -- '+shlex.quote(info['path'])],stdout=out,stderr=subprocess.PIPE,timeout=90)
    require(done.returncode==0 and archive.stat().st_size==info['bytes'] and sha(archive)==info['sha256'],'Archive transfer incomplete; retain partial/no rerun')
    raw=local/'raw';raw.mkdir()
    with tarfile.open(archive,'r:gz') as stream:
        members=stream.getmembers();names=[m.name for m in members]
        require(len(names)==len(set(names)) and all(m.isreg() and not m.issparse() and not PurePosixPath(m.name).is_absolute() and '..' not in PurePosixPath(m.name).parts and str(PurePosixPath(m.name))==m.name for m in members),'Unsafe archive members')
        require(sum(m.size for m in members)<=p['maximumGlobalOutputBytes']+2*1024**2,'Extracted output cap')
        for member in members:
            target=raw/member.name;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as out,stream.extractfile(member) as src:
                for block in iter(lambda:src.read(65536),b''):out.write(block)
    manifest=read(raw/'output-manifest.json');require(sha(raw/'output-manifest.json')==info['manifestSha256'],'Output manifest changed')
    actual={str(f.relative_to(raw)) for f in raw.rglob('*') if f.is_file()}
    require(actual==set(manifest['files'])|{'output-manifest.json'},'Archive full-file closure differs')
    for name,row in manifest['files'].items():require(sha(raw/name)==row['sha256'] and (raw/name).stat().st_size==row['bytes'],'Output raw hash differs')
    require(read(raw/'control/plan.json')==p and sha(raw/'control/controller.py')==p['controllerSha256']
            and sha(raw/'control/artifact.tar')==p['artifact']['sha256'],'Collected plan/controller/class artifact binding differs')
    require(read(raw/'control/artifact-staging.json').get('files')==p['artifact']['files'],'Collected staged class inventory differs')
    save(local/'completion.json',completion)
    checked=[]
    if completion.get('passed') is True:
        require(len(completion.get('points',[]))==8,'All8points required before successful summary')
        for t,point in zip(p['order'],completion['points']):
            require(point==read(raw/'control/points'/t['id']/'receipt.json') and point.get('point')==t
                    and point.get('passed') is True and point.get('cleanup',{}).get('stopped') is True,'Collected point receipt differs')
            require((raw/'control/points'/t['id']/'jvm.log').stat().st_size<=MAX_LOG,'Collected JVM log cap')
            actual=validate_output(p,t,raw/'runs'/t['id']);require(actual==point.get('outputValidation'),'Collected raw validation differs')
            for name in ('artifact-before.json','artifact-after.json'):
                require(read(raw/'control/points'/t['id']/name).get('files')==p['artifact']['files'],'Collected before/after classes differ')
            checked.append(actual)
    save(local/'independent-validation.json',{'passed':completion.get('passed') is True,'points':checked,'scope':'Finite synthetic diagnostic only; unsuccessful attempts retained without pretending all8completed'})
    print(json.dumps({'collected':str(local),'passed':completion.get('passed'),'points':len(checked)}));return 0

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);actions=parser.add_mutually_exclusive_group()
    for name in ('register','execute','worker','status','collect'):actions.add_argument('--'+name,action='store_true')
    parser.add_argument('--id',default='force-probe-cpu-20261024-r1');parser.add_argument('--plan',type=Path)
    parser.add_argument('--idle-window-confirmed',action='store_true',help='Explicit caller confirmation that dependency/native preparation ended; fresh JVM check still required')
    args=parser.parse_args(argv)
    if args.worker or args.execute or args.status or args.collect:
        require(args.plan is not None,'Explicit original registered plan required');p=validate_plan(read(args.plan))
        if args.worker:return worker(args.plan)
        if args.execute:return execute(args.plan,args.idle_window_confirmed)
        if args.status:print(json.dumps(status(p)));return 0
        return collect(p)
    require(not args.idle_window_confirmed,'Idle attestation only for explicit execute')
    p=draft(args.id)
    if args.register:
        require(p['prerequisite'].get('ready') is True,'All4client closure required; prospective draft remains allowed')
        target=args.plan or BASE/'registrations'/(p['id']+'.json');save(target,p)
        print(json.dumps({'registered':str(target),'planSha256':p['planSha256'],'networkUsed':False}));return 0
    print(json.dumps(p,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
