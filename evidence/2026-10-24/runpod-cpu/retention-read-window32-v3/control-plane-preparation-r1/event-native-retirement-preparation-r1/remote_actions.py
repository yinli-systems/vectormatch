def setup(c):
    validate_config(c);need(socket.gethostname()=='ed6c0673f5cb'and platform.system()=='Linux'and os.geteuid()==0,'Exact existing Linux CPU host/root required')
    for p in[OLD,CONTROL.parent,BACKUP.parent]:no_links(p);need(p.is_dir(),'Required existing parent')
    need(not Path('/opt/vectormatch-cpu/preparation/cpu-read-window32-cloud-abab-r1').exists(),'Next605 campaign already staged; preserve it')
    filesystem=mount_facts(CONTROL.parent);workspace=mount_facts(BACKUP.parent)
    need(filesystem['filesystemType']=='overlay'and os.stat(CONTROL.parent).st_dev==os.stat(OLD).st_dev,'Restore must use same Linux overlay, never FUSE')
    need('fuse'in workspace['filesystemType']and workspace['mountPoint']!='/','Workspace is archive-only separate FUSE mount')
    geometry=os.statvfs(CONTROL.parent);need(geometry.f_frsize==ALLOCATION_BLOCK and geometry.f_bsize==ALLOCATION_BLOCK,'Actual overlay allocation geometry differs')
    for name,h in c['oldSources'].items():need(sha(OLD/name)==h,'Frozen87a source identity: '+name)
    sys.path.insert(0,str(OLD));spec=importlib.util.spec_from_file_location('closed_event_controller_for_retirement',OLD/'cpu_event_fetch_abab.py');ctrl=importlib.util.module_from_spec(spec);spec.loader.exec_module(ctrl)
    base=ctrl.load_base();ctrl.strict_idle(base);require_twenty_absent(c)
    release=json.loads((OLD/'release/release.json').read_text());need(sha(OLD/'release/release.json')==c['releaseSha256'],'Frozen87a release changed')
    need(release['protectedOriginalState']['manifestSha256']==c['protectedOriginalManifestSha256'],'Exact original57/PG989 baseline')
    protected=ctrl.protected_state(base,release);inventories={}
    for key,row in c['arms'].items():
        job=OLD/('arm-'+key)
        for name,h in row['controls'].items():need(sha(job/name)==h,'Closed control changed: '+key+'/'+name)
        completion=json.loads((job/'completion.json').read_text());stop=json.loads((job/'python-owned-stop.json').read_text())
        need(completion['passed']and completion['allOwnedStopped']and completion['errors']==[]and completion['arm']==int(key),'Closed successful87a arm required')
        need(stop['allOwnedStopped']and not stop['forcedKill']and not stop['numericPidSignalFallback']and stop['errors']==[],'Normal exact owned stop required')
        after=json.loads((job/'after-clean-stop.json').read_text());inv=after['archive']['inventory'];archive=job/'pilot-after-clean-stop.tar.gz'
        need(canonical_sha(inv)==row['nativeInventorySha256']and len(inv['files'])==row['expectedFiles']and len(inv['directories'])==row['expectedDirectories']and inv['logicalBytes']==row['expectedLogicalBytes'],'Exact complete130/16 inventory differs')
        need(archive.stat().st_size==row['nativeArchiveBytes']and sha(archive)==row['nativeArchiveSha256']==after['archive']['archive']['sha256'],'Original nested archive identity')
        equal_inventory(base.scan(job/'idle-arm',True),inv);inventories[key]=inv
    return ctrl,base,protected,inventories,dict(overlay=filesystem,workspace=workspace,overlayAllocationBlockBytes=geometry.f_frsize)
def prove_protected_and_idle(c,ctrl,base,before):
    require_twenty_absent(c);ctrl.strict_idle(base);after=ctrl.protected_state(base,json.loads((OLD/'release/release.json').read_text()));need(before==after,'Protected original57/PG989 changed');return after
def bind_runner(c,action,source_sha):
    identity=runner_identity(source_sha);registration=dict(atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),action=action,sourceSha256=source_sha,configCanonicalSha256=canonical_sha(c),identity=identity,noBroadSignals=True,noAutomaticRetry=True)
    write(CONTROL/(action+'.RUNNER_REGISTRATION.json'),registration)
    print(json.dumps(dict(status='STARTED',runner=registration)),flush=True);return registration
def begin_runner(c,action,source_sha,fresh=False):
    validate_config(c);need(socket.gethostname()=='ed6c0673f5cb'and platform.system()=='Linux'and os.geteuid()==0,'Exact runner host/Linux/root required')
    no_links(CONTROL.parent);need(CONTROL.parent.is_dir(),'Existing control parent required')
    if fresh:
        need(not CONTROL.exists()and not CONTROL.is_symlink()and not BACKUP.exists(),'Fresh control/backup namespaces only');os.umask(0o077);CONTROL.mkdir(mode=0o700)
    else:no_links(CONTROL);need(CONTROL.is_dir(),'Existing separately reviewed control root required')
    return bind_runner(c,action,source_sha)
def archive_pair(c,key,ctrl,inv):
    original=OLD/('arm-'+key)/'pilot-after-clean-stop.tar.gz';backup=BACKUP/('arm-'+key+'.native.tar.gz');expected=c['arms'][key]
    for path in[original,backup]:
        no_links(path);need(path.is_file()and path.stat().st_nlink==1 and path.stat().st_size==expected['nativeArchiveBytes']and sha(path)==expected['nativeArchiveSha256'],'Original/second TAR identity differs');ctrl.verify_archive_members(path,inv)
    return backup
def backup_and_restore(c,source_sha):
    runner=begin_runner(c,'backup-and-restore',source_sha,fresh=True)
    ctrl,base,before,inventories,fs=setup(c);need(not BACKUP.exists(),'Fresh backup root only; preserve partials')
    need(shutil.disk_usage(CONTROL.parent).free>=FLOOR+METADATA_RESERVE,'Initial overlay metadata reserve/floor')
    need(shutil.disk_usage(BACKUP.parent).free>=sum(row['nativeArchiveBytes']for row in c['arms'].values())+METADATA_RESERVE,'Workspace complete second-copy reserve')
    BACKUP.mkdir(mode=0o700);write(CONTROL/'REGISTRATION.json',c);rows={}
    try:
        budgets={key:sparse_budget(OLD/('arm-'+key)/'pilot-after-clean-stop.tar.gz',inv)for key,inv in inventories.items()}
        for key,budget in budgets.items():write(CONTROL/('SPARSE_BUDGET_'+key+'.json'),budget)
        required=FLOOR+METADATA_RESERVE+sum(row['roundedDataWriteUpperBytes']for row in budgets.values())
        need(shutil.disk_usage(CONTROL).free>=required,'All four retained sparse proof data+metadata+floor budget does not fit; preserve')
        write(CONTROL/'ALL_RESTORE_BUDGET.json',dict(filesystem=fs,freeBytesBefore=shutil.disk_usage(CONTROL).free,allDataWriteUpperBytes=sum(row['roundedDataWriteUpperBytes']for row in budgets.values()),metadataReserveBytes=METADATA_RESERVE,floorBytes=FLOOR,requiredFreeBytes=required,logicalFallocateForbidden=True,allProofsRetainedUntilSeparateRootClear=True))
        for key,inv in inventories.items():
            remaining=sum(budgets[n]['roundedDataWriteUpperBytes']for n in inventories if n not in rows)
            need(shutil.disk_usage(CONTROL).free>=FLOOR+METADATA_RESERVE+remaining,'Remaining four-proof budget/floor changed')
            original=OLD/('arm-'+key)/'pilot-after-clean-stop.tar.gz';backup=BACKUP/('arm-'+key+'.native.tar.gz')
            with original.open('rb')as src,backup.open('xb')as dst:shutil.copyfileobj(src,dst,BLOCK);dst.flush();os.fsync(dst.fileno())
            archive_pair(c,key,ctrl,inv)
            proof=CONTROL/('restore-proof-'+key);free_before=shutil.disk_usage(CONTROL).free;restored=restore_sparse(backup,proof,inv,base,budgets[key]);free_after=shutil.disk_usage(CONTROL).free
            receipt=dict(passed=True,arm=int(key),nativeLeaf=str(OLD/('arm-'+key)/'idle-arm'),restoreProof=str(proof),originalInventorySha256=canonical_sha(inv),restoredInventory=restored,backup=str(backup),backupSha256=sha(backup),sparseBudgetSha256=sha(CONTROL/('SPARSE_BUDGET_'+key+'.json')),freeBytesBefore=free_before,freeBytesAfter=free_after,observedFloorBytes=FLOOR,noApplicationStarted=True,proofRetainedForIndependentClear=True,noPhysicalDurabilityOrColdApplicationRecoveryClaim=True)
            write(CONTROL/('RESTORE_PROOF_'+key+'.json'),receipt)
            rows[key]=dict(nativeLeaf=receipt['nativeLeaf'],restoreProof=str(proof),backup=str(backup),backupSha256=sha(backup),fullArchiveReadbackPassed=True,sparseRestoreProofPassed=True,files=len(inv['files']),directories=len(inv['directories']),logicalBytes=inv['logicalBytes'],restoreAllocatedBytes=restored['allocatedBytes'],restoreReceiptSha256=sha(CONTROL/('RESTORE_PROOF_'+key+'.json')))
        after=prove_protected_and_idle(c,ctrl,base,before)
        result=dict(passed=True,scope='87A_BACKUP_AND_OVERLAY_SPARSE_RESTORE_COMPLETE_NO_LEAF_OR_PROOF_REMOVED',sourceSha256=source_sha,configCanonicalSha256=canonical_sha(c),runner=runner,arms=rows,protectedBefore=before,protectedAfter=after,noOriginalLeafRemoved=True,allFourProofTreesRetained=True,freeBytes=shutil.disk_usage(CONTROL).free,independentFusedStorageCrashDurabilityProven=False,coldApplicationRestartProven=False,filesystem=fs)
        write(CONTROL/'BACKUP_AND_RESTORE_COMPLETE.json',result);return result
    except BaseException as error:
        write(CONTROL/'BACKUP_AND_RESTORE_FAILED.json',dict(passed=False,error=repr(error),traceback=traceback.format_exc(),allPartialsRetained=True,noAutomaticRetry=True,noOriginalLeafRemoved=True));raise
def backup_gate(c,gate_sha,source_sha):
    need(sha(CONTROL/'BACKUP_AND_RESTORE_COMPLETE.json')==gate_sha,'Root-selected actual backup/restore gate SHA')
    gate=json.loads((CONTROL/'BACKUP_AND_RESTORE_COMPLETE.json').read_text())
    need(gate['passed']and gate['scope']=='87A_BACKUP_AND_OVERLAY_SPARSE_RESTORE_COMPLETE_NO_LEAF_OR_PROOF_REMOVED'and gate['sourceSha256']==source_sha and gate['configCanonicalSha256']==canonical_sha(c)and gate['noOriginalLeafRemoved']and set(gate['arms'])==set(c['arms']),'Complete same-source87a backup/restore gate required')
    return gate
def clear_restore_reviewed(c,gate_sha,source_sha):
    runner=begin_runner(c,'clear-restore-reviewed',source_sha)
    ctrl,base,before,inventories,fs=setup(c);gate=backup_gate(c,gate_sha,source_sha);need(not(CONTROL/'CLEAR_RESTORE_INTENT.json').exists(),'No clear resubmission')
    receipts={}
    for key,inv in inventories.items():
        archive_pair(c,key,ctrl,inv);path=CONTROL/('RESTORE_PROOF_'+key+'.json');need(sha(path)==gate['arms'][key]['restoreReceiptSha256'],'Exact restore receipt differs');receipt=json.loads(path.read_text());proof=CONTROL/('restore-proof-'+key)
        need(receipt['passed']and receipt['restoreProof']==str(proof)and receipt['originalInventorySha256']==canonical_sha(inv),'Exact self-owned proof binding differs');equal_inventory(base.scan(proof,True),receipt['restoredInventory']);receipts[key]=receipt
    prove_protected_and_idle(c,ctrl,base,before)
    write(CONTROL/'CLEAR_RESTORE_INTENT.json',dict(backupRestoreGateSha256=gate_sha,sourceSha256=source_sha,configCanonicalSha256=canonical_sha(c),exactOwnProofs=[str(CONTROL/('restore-proof-'+key))for key in inventories],originalLeavesExcluded=True));cleared=[]
    try:
        for key,receipt in receipts.items():
            require_twenty_absent(c);ctrl.strict_idle(base);proof=CONTROL/('restore-proof-'+key);delete_exact(proof,receipt['restoredInventory'],base);cleared.append(str(proof))
        after=prove_protected_and_idle(c,ctrl,base,before)
        for key,inv in inventories.items():equal_inventory(base.scan(OLD/('arm-'+key)/'idle-arm',True),inv);archive_pair(c,key,ctrl,inv)
        result=dict(passed=True,scope='87A_EXACT_OWN_RESTORE_PROOFS_CLEARED_ORIGINAL_LEAVES_RETAINED',backupRestoreGateSha256=gate_sha,sourceSha256=source_sha,configCanonicalSha256=canonical_sha(c),runner=runner,clearedOwnRestoreProofs=cleared,noOriginalLeafRemoved=True,protectedBefore=before,protectedAfter=after,freeBytes=shutil.disk_usage(CONTROL).free)
        write(CONTROL/'CLEAR_RESTORE_COMPLETE.json',result);return result
    except BaseException as error:
        write(CONTROL/'CLEAR_RESTORE_FAILED.json',dict(passed=False,error=repr(error),traceback=traceback.format_exc(),clearedOwnProofs=cleared,noAutomaticRetry=True,noOriginalLeafRemoved=True));raise
def retire_reviewed(c,gate_sha,clear_sha,source_sha):
    runner=begin_runner(c,'retire-reviewed',source_sha)
    ctrl,base,before,inventories,fs=setup(c);backup_gate(c,gate_sha,source_sha)
    need(sha(CONTROL/'CLEAR_RESTORE_COMPLETE.json')==clear_sha,'Independent root-selected exact-clear gate SHA');clear=json.loads((CONTROL/'CLEAR_RESTORE_COMPLETE.json').read_text())
    need(clear['passed']and clear['scope']=='87A_EXACT_OWN_RESTORE_PROOFS_CLEARED_ORIGINAL_LEAVES_RETAINED'and clear['sourceSha256']==source_sha and clear['configCanonicalSha256']==canonical_sha(c)and clear['backupRestoreGateSha256']==gate_sha and clear['noOriginalLeafRemoved'],'Actual same-source clear gate differs')
    need(not(CONTROL/'RETIRE_INTENT.json').exists(),'No retirement resubmission')
    for key,inv in inventories.items():need(not(CONTROL/('restore-proof-'+key)).exists(),'Restore proof still present');archive_pair(c,key,ctrl,inv)
    prove_protected_and_idle(c,ctrl,base,before)
    write(CONTROL/'RETIRE_INTENT.json',dict(backupRestoreGateSha256=gate_sha,clearRestoreGateSha256=clear_sha,sourceSha256=source_sha,configCanonicalSha256=canonical_sha(c),exactNativeLeaves=[row['nativeLeaf']for row in c['arms'].values()],wrapperControlsAndOriginalArchivesRetained=True));free=shutil.disk_usage(CONTROL).free;removed=[]
    try:
        for key,inv in inventories.items():
            require_twenty_absent(c);ctrl.strict_idle(base);need(not Path('/opt/vectormatch-cpu/preparation/cpu-read-window32-cloud-abab-r1').exists(),'New605 preparation appeared; preserve it')
            leaf=OLD/('arm-'+key)/'idle-arm';delete_exact(leaf,inv,base);removed.append(str(leaf))
        after=prove_protected_and_idle(c,ctrl,base,before)
        for key,inv in inventories.items():
            need(not(OLD/('arm-'+key)/'idle-arm').exists(),'Retired leaf remains');archive_pair(c,key,ctrl,inv)
            for name,h in c['arms'][key]['controls'].items():need(sha(OLD/('arm-'+key)/name)==h,'Retirement changed wrapper control')
        result=dict(passed=True,scope='87A_ONLY_FOUR_CLOSED_ARCHIVED_DUPLICATE_NATIVE_LEAVES_RETIRED',removedNativeLeaves=removed,backupRestoreGateSha256=gate_sha,clearRestoreGateSha256=clear_sha,sourceSha256=source_sha,configCanonicalSha256=canonical_sha(c),runner=runner,freeBytesBefore=free,freeBytesAfter=shutil.disk_usage(CONTROL).free,protectedBefore=before,protectedAfter=after,allTwentyHistoricalPidsStrictlyAbsent=True,allEightOriginalAndSecondArchivesFullShaAndMembersReverified=True,noNewResources=True,otherWorkloadsTouched=False,no605LeafTouched=True)
        write(CONTROL/'RETIRE_COMPLETE.json',result);return result
    except BaseException as error:
        write(CONTROL/'RETIRE_FAILED.json',dict(passed=False,error=repr(error),traceback=traceback.format_exc(),removedNativeLeaves=removed,allBackupsRetained=True,noAutomaticRetry=True));raise
if __name__=='__main__':
    parser=argparse.ArgumentParser(allow_abbrev=False);parser.add_argument('action',choices=['backup-and-restore','clear-restore-reviewed','retire-reviewed']);parser.add_argument('--source-sha256',required=True);parser.add_argument('--backup-and-restore-gate-sha256');parser.add_argument('--restore-clear-gate-sha256');args=parser.parse_args()
    need((args.action!='backup-and-restore')==bool(args.backup_and_restore_gate_sha256),'Explicit backup gate required only for following actions');need((args.action=='retire-reviewed')==bool(args.restore_clear_gate_sha256),'Separate exact-clear gate required only for retirement')
    config=json.load(sys.stdin)
    try:
        if args.action=='backup-and-restore':result=backup_and_restore(config,args.source_sha256)
        elif args.action=='clear-restore-reviewed':result=clear_restore_reviewed(config,args.backup_and_restore_gate_sha256,args.source_sha256)
        else:result=retire_reviewed(config,args.backup_and_restore_gate_sha256,args.restore_clear_gate_sha256,args.source_sha256)
    except BaseException as error:
        registration=CONTROL/(args.action+'.RUNNER_REGISTRATION.json')
        if registration.is_file()and json.loads(registration.read_text())['identity']['pid']==os.getpid():
            write(CONTROL/(args.action+'.RUNNER_FAILED.json'),dict(passed=False,error=repr(error),traceback=traceback.format_exc(),allPartialsRetained=True,noAutomaticRetry=True,noSignalsSent=True))
        print(json.dumps(dict(status='FAILED',error=repr(error),remoteExitNotYetClaimed=True)),flush=True);raise
    write(CONTROL/(args.action+'.RUNNER_RETURNED.json'),dict(passed=True,identity=result['runner']['identity'],sourceSha256=args.source_sha256,actionReturnedNormally=True,processExitOrAbsenceNotClaimedBeforeItOccurs=True))
    print(json.dumps(dict(status='RETURNED',result=result)),flush=True)
