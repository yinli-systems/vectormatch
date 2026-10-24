"""Small local schema/bounds guards. No cloud, Aeron, PGDATA, long runs, or large allocation."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

BASE=Path(__file__).resolve().parent
REPO=BASE.parents[3]
JAVA=REPO/'.tools/jdk/bin/java'
JAVAC=REPO/'.tools/jdk/bin/javac'

class ForceProbeGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.build.cleanup)
        done=subprocess.run([str(JAVAC),'--release','21','-d',cls.build.name,
                str(BASE/'ForcePathProbe.java'),str(BASE/'ForcePathProbeClockGuard.java')],capture_output=True,text=True,timeout=20)
        if done.returncode:raise AssertionError(done.stdout+done.stderr)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.output=self.root/'force-probe-schema'
    def args(self,**changes):
        values={'output-dir':str(self.output),'block-bytes':'4096','writers':'1','file-bytes-per-writer':'8192',
                'warmup-iterations':'1','measurement-iterations':'2','max-total-write-bytes':'20480',
                'max-duration-ms':'5000','min-free-bytes':'0','scope-label':'schema-smoke'}
        values.update(changes)
        return [piece for key,value in values.items() for piece in ('--'+key,str(value))]
    def command(self,args,main='ForcePathProbe'):
        return subprocess.run([str(JAVA),'-Xms32m','-Xmx64m','-cp',self.build.name,main,*args],capture_output=True,text=True,timeout=10)
    def fail_before_create(self,args):
        done=self.command(args);self.assertNotEqual(done.returncode,0,done.stdout+done.stderr)
        self.assertFalse(self.output.exists(),done.stderr)
    def test_real_tiny_one_writer_all_phases_rows_force_true_counts_and_file_hash(self):
        done=self.command(self.args());self.assertEqual(done.returncode,0,done.stderr)
        config=json.loads((self.output/'configuration.json').read_text());receipt=json.loads((self.output/'success.json').read_text())
        self.assertTrue(config['forceMetadata']);self.assertIn('one JVM',config['writerModel'])
        self.assertEqual(config['plannedTotalWriteBytes'],20480);self.assertEqual(config['plannedForceCalls'],4)
        with (self.output/'writer-0.csv').open(newline='') as stream:rows=list(csv.DictReader(stream))
        self.assertEqual([r['phase'] for r in rows],['preallocation','warmup','measurement','measurement'])
        self.assertEqual(sum(int(r['force_calls']) for r in rows),4)
        self.assertEqual(sum(int(r['written_bytes']) for r in rows),20480)
        for row in rows:
            self.assertEqual(row['status'],'complete');self.assertEqual(row['deadline_exceeded'],'false')
            self.assertEqual(row['written_bytes'],row['requested_bytes'])
            self.assertEqual(int(row['total_elapsed_ns']),int(row['write_elapsed_ns'])+int(row['force_elapsed_ns']))
            self.assertGreaterEqual(int(row['offset_bytes']),0)
            self.assertLessEqual(int(row['offset_bytes'])+int(row['requested_bytes']),8192)
            if row['thread_cpu_ns']:self.assertGreaterEqual(int(row['thread_cpu_ns']),0)
        self.assertEqual(receipt['forceTrueCalls'],4);self.assertEqual(receipt['totalWrittenBytes'],20480)
        data=self.output/'synthetic-force-writer-0.data';self.assertEqual(data.stat().st_size,8192)
        self.assertEqual(hashlib.sha256(data.read_bytes()).hexdigest(),receipt['dataFiles'][0]['sha256'])
        self.assertFalse((self.output/'failure.json').exists())
    def test_real_three_threads_independent_files_and_rows_not_three_JVM_claim(self):
        done=self.command(self.args(**{'writers':'3','file-bytes-per-writer':'4096','warmup-iterations':'0',
                                      'measurement-iterations':'1','max-total-write-bytes':'24576'}))
        self.assertEqual(done.returncode,0,done.stderr)
        receipt=json.loads((self.output/'success.json').read_text());self.assertEqual(receipt['forceTrueCalls'],6)
        self.assertTrue(receipt['allWorkerThreadsTerminated'])
        for writer in range(3):
            with (self.output/f'writer-{writer}.csv').open(newline='') as stream:rows=list(csv.DictReader(stream))
            self.assertEqual([r['phase'] for r in rows],['preallocation','measurement'])
            self.assertTrue(all(r['writer_id']==str(writer) for r in rows))
            self.assertEqual((self.output/f'synthetic-force-writer-{writer}.data').stat().st_size,4096)
    def test_no_overwrite_or_failure_receipt_in_existing_directory(self):
        self.output.mkdir();sentinel=self.output/'untouched';sentinel.write_bytes(b'original')
        done=self.command(self.args());self.assertNotEqual(done.returncode,0)
        self.assertEqual(list(self.output.iterdir()),[sentinel]);self.assertEqual(sentinel.read_bytes(),b'original')
    def test_explicit_total_write_budget_includes_preallocation_warmup_measurement(self):
        self.fail_before_create(self.args(**{'max-total-write-bytes':'20479'}))
    def test_invalid_size_writers_count_time_bounds_do_not_create_output(self):
        for key,value in [('block-bytes','8192'),('writers','2'),('file-bytes-per-writer','4097'),
                          ('file-bytes-per-writer',str((64<<20)+4096)),('measurement-iterations','0'),
                          ('measurement-iterations','100001'),('warmup-iterations','100001'),
                          ('max-duration-ms','0'),('max-duration-ms','60001'),('max-total-write-bytes',str((256<<20)+1))]:
            with self.subTest(key=key,value=value):self.fail_before_create(self.args(**{key:value}))
    def test_noncanonical_overflow_negative_or_unknown_options_refused(self):
        for value in ('+1','01','-1','1e2','999999999999999999999999'):
            with self.subTest(value=value):self.fail_before_create(self.args(**{'writers':value}))
        self.fail_before_create([*self.args(),'--unknown','x'])
        self.fail_before_create([*self.args(),'--writers','1'])
    def test_symlink_parent_and_production_path_refused(self):
        link=self.root/'link';link.symlink_to(self.root,target_is_directory=True)
        done=self.command(self.args(**{'output-dir':str(link/'force-probe-new')}));self.assertNotEqual(done.returncode,0)
        self.assertFalse((self.root/'force-probe-new').exists())
        done=self.command(self.args(**{'output-dir':str(self.root/'postgres18'/'force-probe-new')}));self.assertNotEqual(done.returncode,0)
        self.assertFalse((self.root/'postgres18').exists())
    def test_space_floor_before_creation(self):
        self.fail_before_create(self.args(**{'min-free-bytes':str((1<<63)-1)}))
    def test_injected_monotonic_deadline_retains_failure_never_success(self):
        done=self.command([str(self.output)],'ForcePathProbeClockGuard');self.assertEqual(done.returncode,0,done.stderr)
        receipt=json.loads((self.output/'failure.json').read_text());self.assertFalse(receipt['passed'])
        self.assertTrue((self.output/'configuration.json').exists());self.assertFalse((self.output/'success.json').exists())
    def test_each_supported_block_size_has_only_tiny_bounded_writes(self):
        for block in (16384,24576,49152):
            output=self.root/f'force-probe-block{block}'
            done=self.command(self.args(**{'output-dir':str(output),'block-bytes':str(block),
                'file-bytes-per-writer':str(block),'warmup-iterations':'0','measurement-iterations':'1',
                'max-total-write-bytes':str(block*2)}))
            self.assertEqual(done.returncode,0,done.stderr)
            receipt=json.loads((output/'success.json').read_text());self.assertEqual(receipt['forceTrueCalls'],2)
            self.assertEqual(receipt['totalWrittenBytes'],block*2)

if __name__=='__main__':unittest.main()
