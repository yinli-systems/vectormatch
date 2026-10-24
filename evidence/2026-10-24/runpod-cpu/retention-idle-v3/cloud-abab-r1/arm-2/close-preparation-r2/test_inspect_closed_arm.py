"""Pure ownership/control-receipt mocks. No remote access/process actions."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import inspect_closed_arm as p

BASE=Path(__file__).resolve().parent.parent
RELEASE=(BASE/'idle-root-freeze-r1/release.json').read_bytes()
CONTROLLER=(BASE/'cpu-idle-cloud-preparation-r2/cpu_idle_abab.py').read_bytes()


class CloseGuards(unittest.TestCase):
    def setUp(self,arm=2):
        self.arm=arm;self.maximum=p.PARK_ORDER[arm-1]
        self.prior_gate={'schemaVersion':2,'scope':'ROOT_VERIFIED_CLOSED_CPU_IDLE_ARM_COLLECTION','collectionComplete':True,
            'arm':arm-1,'maximumParkNs':p.PARK_ORDER[arm-2],'frozenReleaseSha256':p.RELEASE_SHA,'controllerSha256':p.CONTROLLER_SHA,
            'localFullMemberShaBytesModesOwnersEmptyDirsVerified':True,'allRawInputsAndFailuresRetained':True,
            'independentLocalCollectionReceiptSha256':'e'*64,'closedArchiveSha256':'d'*64,'closedNativeInventorySha256':'c'*64}
        self.prior=p.hashlib.sha256(json.dumps(self.prior_gate).encode()).hexdigest()
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.prep=self.root/'prep';self.prep.mkdir()
        self.job=self.prep/('arm-'+str(arm));self.job.mkdir();self.native=self.job/'idle-arm'
        self.arc=self.job/'pilot-after-clean-stop.tar.gz';self.arc.write_bytes(b'x')
        self.release=json.loads(RELEASE);self.reg={'ports':42000,'readWindow':8,'appointedLeader':0,'sync':2,
            'profileSha256':self.release['profileFingerprint'],'codeSha256':self.release['codeFingerprint'],
            'retentionIdleSelection':{'maximumParkNs':self.maximum},'lineage':'capacity-pilot-schema'}
        args=['/usr/bin/python3','-B',str(self.prep/'cpu_idle_abab.py'),'--arm',str(arm),'--release-sha256',p.RELEASE_SHA,'--start-new','--prior-collection-sha256',self.prior]
        self.entries=[{'state':'INTENT_NO_PID_YET','expectedArguments':args,'arm':arm,'frozenReleaseSha256':p.RELEASE_SHA},
            {'state':'SPAWNED_IDENTITY_PENDING','pid':100,'arm':arm},
            {'pid':100,'startTicks':1000,'expectedArguments':args,'arm':arm,'frozenReleaseSha256':p.RELEASE_SHA,
             'observedCommandSha256':p.argv_sha(args),'observedExecArgvMatches':True,'stableStartTicks':True}]
        self.parent=self.identity(101,p.expected_parent(self.release,self.native,self.maximum))
        self.nodes=[self.identity(102+n,p.expected_node(self.release,self.native,self.reg,n,self.maximum))for n in range(3)]
        logs=[{'node':n,'warningPairCount':0,'afterSigtermWallTimeProven':False,'allLogLinesClassifiedAndRetained':True}for n in range(3)]
        self.completion={'arm':arm,'maximumParkNs':self.maximum,'frozenReleaseSha256':p.RELEASE_SHA,
            'allOwnedStopped':True,'passed':True,'errors':[],'result':{'passed':True,'arms':[{
                'maximumParkNs':self.maximum,'readWindow':8,'functional':{'passed':True,'actualSourceSummary':{
                    'confirmedAcceptedUniqueOrders':6400,'notSent':0,'unknownFinal':0,'schedulerTimingValid':True}},
                'nodeLogClassifications':logs,'retainedPostCheckpointEosWarningPairs':0}]}}
        self.stop={'allOwnedStopped':True,'errors':[],'forcedKill':False,'numericPidSignalFallback':False,
            'reports':[{'role':'window-8-node-%d'%n,'record':rec,'stopped':True}for n,rec in enumerate(self.nodes)]}
        self.protected={'passed':True,'manifestSha256':p.PROTECTED_SHA,'nativeTrees':[{'files':18},{'files':19},{'files':20}],'postgres':{'files':989}}
        self.before={'controllerSha256':p.CONTROLLER_SHA,'baseSha256':'8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87','protectedOriginal':self.protected,'priorArm':{'passed':True,'gateSha256':self.prior}}
        self.after={'protectedOriginal':copy.deepcopy(self.protected),'archive':{'sameHostReadback':{'passed':True},
            'requiresIndependentCollectorStreamReadback':True,'archive':{'path':str(self.arc),'bytes':1,'sha256':'f'*64}}}
        self.extra={}

    def tearDown(self):self.temp.cleanup()
    def identity(self,pid,args):return {'pid':pid,'startTicks':pid*10,'arguments':args,'commandSha256':p.argv_sha(args)}
    def js(self,path,*unused,**kw):
        self.extra.setdefault('jsonReads',[]).append(path.name)
        name=path.name
        if name=='BENCHMARK_BLOCKED.json':return None
        if name=='completion.json':return self.completion
        if name=='python-owned-stop.json':return self.stop
        if name=='identity-observation-000.json':return {'role':'pilot-parent','origin':'independent-direct-child-proc','kernelIdentity':self.parent}
        if name=='parent-launch-handle.json':return {'pid':101,'expectedArguments':self.parent['arguments'],'expectedCommandSha256':self.parent['commandSha256']}
        if name=='registration.json':return self.reg
        if name=='before.json':return self.before
        if name=='after-clean-stop.json':return self.after
        if name.startswith('node-'):
            rec=self.nodes[int(name.split('-')[1])]
            return {'pid':rec['pid'],'linuxStartTicks':rec['startTicks'],'linuxCommandSha256':rec['commandSha256'],
                    'command':rec['arguments'][0],'arguments':rec['arguments'][1:]}
        raise AssertionError(name)
    def bounded(self,path,*unused,**kw):
        if path.name=='arm-%d-execution-register.json'%self.arm:return b'\n'.join(json.dumps(v).encode()for v in self.entries)+b'\n'
        if path.name=='arm-%d-collection-gate.json'%(self.arm-1):return json.dumps(self.prior_gate).encode()
        if path.name=='release.json':return RELEASE
        if path.name=='cpu_idle_abab.py':return CONTROLLER
        raise AssertionError(path)
    def call(self,states=None,prior=None,identity=None):
        states=states or {}
        def status(rec):
            state=states.get(rec['pid'],'PID_ABSENT')
            return {'pid':rec['pid'],'originalIdentityRunning':state=='REGISTERED_IDENTITY_RUNNING','observation':state}
        with mock.patch.object(p,'PREP',self.prep),mock.patch.object(p,'bounded',side_effect=self.bounded),\
             mock.patch.object(p,'js',side_effect=self.js),mock.patch.object(p,'identity_state',side_effect=status),\
             mock.patch.object(p,'live_jvm_pg',return_value=([],5)),mock.patch.object(p.platform,'system',return_value='Linux'),\
             mock.patch.object(p.platform,'machine',return_value='x86_64'),mock.patch.object(p.platform,'node',return_value='ed6c0673f5cb'),\
             mock.patch.object(p.os,'geteuid',return_value=0):return p.inspect(self.arm,p.RELEASE_SHA,self.prior if prior is None else prior,
                    identity or {'pid':100,'startTicks':1000,'commandSha256':p.argv_sha(self.entries[0]['expectedArguments'])})

    def test_full_success_requires_controller_and_four_strict_pid_absences(self):
        r=self.call();self.assertTrue(r['closedGate']);self.assertTrue(r['allFourOwnedJvmsStrictlyPidAbsent'])
        self.assertEqual(len(r['ownership']),4);self.assertFalse(r['archiveFullHashReadHere'])
        self.assertEqual(r['protectedFinalValues'],self.protected)
    def test_controller_running_never_reads_job_or_native_receipts(self):
        r=self.call({100:'REGISTERED_IDENTITY_RUNNING'});self.assertFalse(r['closedGate']);self.assertNotIn('jsonReads',self.extra)
    def test_zombie_or_reused_controller_is_not_strict_absence(self):
        for state in ['REGISTERED_IDENTITY_ZOMBIE_NOT_RUNNING','PID_REUSED_DIFFERENT_START_TICKS']:
            with self.subTest(state=state):self.assertFalse(self.call({100:state})['closedGate'])
    def test_one_running_or_reused_owned_pid_blocks_collection(self):
        for state in ['REGISTERED_IDENTITY_RUNNING','PID_REUSED_DIFFERENT_START_TICKS']:
            with self.subTest(state=state):self.assertFalse(self.call({103:state})['closedGate'])
    def test_failed_receipt_is_preserved_as_failure_collection_not_pass(self):
        self.completion['passed']=False;self.completion['errors']=[{'phase':'proof-validation'}]
        r=self.call();self.assertEqual(r['state'],'CLOSED_FAILED_OUTCOME');self.assertFalse(r['closedGate'])
        self.assertTrue(r['safeForReadOnlyFailureCollection'])
    def test_changed_protected_receipt_or_kernel_argv_refused(self):
        self.after['protectedOriginal']['postgres']['files']=988
        with self.assertRaises(ValueError):self.call()
        self.after['protectedOriginal']=copy.deepcopy(self.protected);self.nodes[1]['arguments'][1]='-Dvectormatch.retention.idleMaxParkNs=999999'
        with self.assertRaises(ValueError):self.call()
    def test_pending_launch_or_wrong_verified_sha_never_resubmits(self):
        old=self.entries;self.entries=self.entries[:2];r=self.call();self.assertFalse(r['closedGate']);self.assertTrue(r['neverResubmit'])
        self.entries=old;self.entries[-1]['observedCommandSha256']='0'*64
        with self.assertRaises(ValueError):self.call()
    def test_probe_has_no_signal_subprocess_write_or_network_apis(self):
        tree=ast.parse(Path(p.__file__).read_text());imports={n.names[0].name for n in tree.body if isinstance(n,ast.Import)}
        self.assertFalse(imports & {'subprocess','signal','socket','shutil'})
        attrs={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call)and isinstance(n.func,ast.Attribute)}
        self.assertFalse(attrs & {'kill','killpg','unlink','rmtree','write_text','write_bytes','mkdir'})
    def test_registered_identity_cannot_replace_actual_root_launch_pid(self):
        self.entries[-1]['pid']=999;self.entries[1]['pid']=999
        with self.assertRaisesRegex(ValueError,'actual controller launch identity'):self.call()
    def test_each_manual_arm_binds_selected_park_and_immediate_predecessor(self):
        for arm in (2,3,4):
            self.tearDown();self.setUp(arm)
            with self.subTest(arm=arm):
                r=self.call();self.assertTrue(r['closedGate']);self.assertEqual(r['arm'],arm)
                self.assertEqual(r['maximumParkNs'],p.PARK_ORDER[arm-1])
                self.assertEqual(r['priorCollectionSha256'],self.prior)
                self.assertEqual(r['controllerOriginalIdentity']['arguments'][-2:],['--prior-collection-sha256',self.prior])
    def test_prior_sha_is_required_and_bound_to_launch_and_actual_gate_bytes(self):
        for value in ('','A'*64,'f'*64):
            with self.subTest(value=value),self.assertRaises(ValueError):self.call(prior=value)
        self.prior_gate['arm']=2
        with self.assertRaisesRegex(ValueError,'prior collection gate SHA'):self.call()
    def test_external_controller_pid_ticks_and_argv_sha_are_mandatory_exact(self):
        identity={'pid':100,'startTicks':1000,'commandSha256':p.argv_sha(self.entries[0]['expectedArguments'])}
        for change in ({'pid':999},{'startTicks':999},{'commandSha256':'0'*64},{'startTicks':True}):
            candidate=dict(identity,**change)
            with self.subTest(change=change),self.assertRaises(ValueError):self.call(identity=candidate)
        self.arm=1
        with self.assertRaisesRegex(ValueError,'Exact frozen round'):self.call()
    def test_gate_selected_park_and_before_receipt_cannot_drift(self):
        self.completion['maximumParkNs']=1000000
        with self.assertRaisesRegex(ValueError,'Completion scope'):self.call()
        self.completion['maximumParkNs']=self.maximum;self.before['priorArm']['gateSha256']='0'*64
        with self.assertRaisesRegex(ValueError,'preflight prior gate'):self.call()


if __name__=='__main__':unittest.main()
