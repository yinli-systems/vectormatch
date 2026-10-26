import pathlib,subprocess,os,json,time,hashlib,sys,shutil
ROOT=pathlib.Path('/opt/vectormatch-cpu/experiments/anchored-continuity-20261027-r1')
JAVA='/opt/vectormatch-cpu/experiments/soak-20261026-r1/tools/jdk-21.0.13+9/bin/java'
BASE=[JAVA,'-Xms512m','-Xmx512m','-XX:ActiveProcessorCount=4','-XX:ParallelGCThreads=2','-XX:ConcGCThreads=1','-cp',str(ROOT/'dist/lib/*'),'io.vectormatch.cluster.AnchoredContinuityRunV4']
def birth(pid):return pathlib.Path('/proc/'+str(pid)+'/stat').read_text().split(') ',1)[1].split()[19]
def invoke(name,args,timeout=1000):
    cmd=BASE[:1]+['-Xlog:gc*:file='+str(ROOT/(name+'.gc.log'))+':time,uptime,level,tags']+BASE[1:]+args
    before=time.time()
    with (ROOT/(name+'.stdout')).open('xb') as out,(ROOT/(name+'.stderr')).open('xb') as err:
        proc=subprocess.Popen(cmd,stdout=out,stderr=err,start_new_session=True)
        launch={'pid':proc.pid,'startTicks':birth(proc.pid),'command':cmd,'epochStarted':before}
        (ROOT/(name+'.launch.json')).write_text(json.dumps(launch,indent=2)+'\n')
        try:code=proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # This subprocess and process group were created above; do not target any other workload.
            if proc.poll() is None:os.killpg(proc.pid,15)
            try:code=proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                if proc.poll() is None:os.killpg(proc.pid,9)
                code=proc.wait()
            (ROOT/(name+'.timeout.json')).write_text(json.dumps({'timeoutSeconds':timeout,'exitCode':code})+'\n')
        (ROOT/(name+'.exit.json')).write_text(json.dumps({'exitCode':code,'epochEnded':time.time(),'wallSeconds':time.time()-before})+'\n')
        if code!=0:raise RuntimeError(name+' exit '+str(code))
    print(json.dumps({'complete':name,'wallSeconds':time.time()-before}),flush=True)
if __name__=='__main__':
    name,mode,previous,target=sys.argv[1:]
    assert pathlib.Path('/etc/hostname').read_text().strip()=='33ace3d92505'
    assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
    if mode=='continue':
        invoke(name,['continue',str(ROOT/name),str(ROOT/previous),target,'900'])
        invoke('audit-'+name,['audit',str(ROOT/name)])
    else:raise ValueError('explicit continuation required')
