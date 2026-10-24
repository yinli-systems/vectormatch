"""Bounded JDK diagnostic attachment to three independently registered node identities only."""
import re

def attach_jcmd(base,root,release,label,target,operation):
    require(base.matching_identity(target)is not None,'Exact target identity gone; no attach')
    tool=release['jcmdExecutable'];require(digest(tool['path'])==tool['sha256'],'Pinned installed jcmd body changed')
    args=[tool['path'],'-J-Xmx64m',str(target['pid'])]+operation
    require(not(root/(label+'-intent.json')).exists(),'No diagnostic attach retry')
    base.save(root/(label+'-intent.json'),dict(arguments=args,targetIdentity=target,atUTC=base.now()))
    child,identity=None,None
    try:
        with(root/(label+'.stdout')).open('xb')as out,(root/(label+'.stderr')).open('xb')as err:
            child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC'},start_new_session=True)
        base.save(root/(label+'-launch.json'),dict(pid=child.pid,arguments=args))
        for unused in range(100):
            actual=base.process_identity(child.pid)
            if actual is not None and actual['arguments']==args:
                require(actual['commandSha256']==base.argv_digest(args),'jcmd exact full argv hash differs');identity=actual;break
            if child.poll()is not None:break
            time.sleep(.005)
        require(identity is not None,'No verified jcmd exec identity; preserve no retry')
        base.save(root/(label+'-identity.json'),identity)
        status=child.wait(timeout=15)
        require((root/(label+'.stdout')).stat().st_size<=65536 and(root/(label+'.stderr')).stat().st_size<=65536,'jcmd output cap')
        text=(root/(label+'.stdout')).read_text();error=(root/(label+'.stderr')).read_text()
        require(status==0 and not re.search(r'unknown argument|could not|exception|error|failed',text+'\n'+error,re.I),'Diagnostic command rejected')
        require(base.matching_identity(target)is not None,'Target changed/exited during diagnostic attach')
        require(digest(tool['path'])==tool['sha256'],'jcmd changed after command')
        return text
    finally:
        if child is not None and child.poll()is None:
            if identity is not None:base.stop_owned(identity,10)
            child.wait(timeout=15)
        if child is not None:
            gone=not(base.PROC/str(child.pid)).exists()
            base.save(root/(label+'-closed.json'),dict(strictPidAbsent=gone,forcedKill=False,pid=child.pid,exactIdentity=identity))
            require(gone,'Diagnostic helper PID closure unconfirmed')


def monitor_with_node_jfr(base,registry,release,initial):
    observation=ORIGINAL_MONITOR(base,registry,release,initial)
    roles={'window-32-node-'+str(n)for n in(0,1,2)}
    if roles.issubset({r['role']for r in registry.records.values()})and not NODE_ATTACH_STATE['started']:
        NODE_ATTACH_STATE['started']=True
        folder=JOB/'node-jfr-attaches';folder.mkdir(mode=0o700)
        records=[]
        for n in(0,1,2):
            target=next(r['identity']for r in registry.records.values()if r['role']=='window-32-node-'+str(n))
            repository=JOB/('node-'+str(n)+'-jfr-repository');repository.mkdir(mode=0o700)
            label='node-'+str(n)
            configured=attach_jcmd(base,folder,release,label+'-configure',target,['JFR.configure','repositorypath='+str(repository),'maxchunksize=1m'])
            require(str(repository)in configured,'Actual JFR repository differs')
            destination=JOB/'recordings'/('node-'+str(n)+'-pid-'+str(target['pid'])+'.jfr')
            started=attach_jcmd(base,folder,release,label+'-start',target,['JFR.start','name=vectormatch-node-'+str(n),'settings='+str(HERE/'force-only.jfc'),'filename='+str(destination),'dumponexit=true','maxsize=8m','disk=true'])
            require('Started recording'in started,'Node recording did not actually start')
            records.append(dict(node=n,targetIdentity=target,recording=str(destination),repository=str(repository)))
        base.save(JOB/'NODE_JFR_ATTACH_COMPLETE.json',dict(passed=True,records=records,noApplicationJarChanged=True,diagnosticOverheadExplicit=True,fullArrivalWindowCoverageNotAssumed=True))
        NODE_ATTACH_STATE['complete']=True
    return observation
