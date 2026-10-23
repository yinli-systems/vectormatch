import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cgroups = load("cgroup_limits_test", "cgroup-limits.py")
preflight = load("cloud_preflight_test", "cloud-preflight.py")


class CgroupLimitsTest(unittest.TestCase):
    def test_v2_process_and_ancestors_constrain_cpu_memory_and_cpuset(self):
        values = {
            "/sys/fs/cgroup/user.slice/session.scope/cpu.max": "max 100000",
            "/sys/fs/cgroup/user.slice/cpu.max": "200000 100000",
            "/sys/fs/cgroup/cpu.max": "max 100000",
            "/sys/fs/cgroup/user.slice/session.scope/memory.max": "max",
            "/sys/fs/cgroup/user.slice/memory.max": "1073741824",
            "/sys/fs/cgroup/memory.max": "4294967296",
            "/sys/fs/cgroup/user.slice/session.scope/cpuset.cpus.effective": "0-7",
            "/sys/fs/cgroup/user.slice/cpuset.cpus.effective": "0-3",
            "/sys/fs/cgroup/cpuset.cpus.effective": "0-15",
        }
        result = cgroups.collect("0::/user.slice/session.scope", "28 1 0:28 / /sys/fs/cgroup rw - cgroup2 cgroup rw",
                                 reader=values.get, affinity=list(range(8)))
        self.assertEqual(2, result["visibleCpuQuotaUpperBound"])
        self.assertEqual(2, result["visibleCpuUpperBound"])
        self.assertEqual(1073741824, result["visibleMemoryUpperBoundBytes"])
        self.assertEqual([0, 1, 2, 3], result["affinityAndVisibleCpusetCpuIds"])
        self.assertEqual(["/sys/fs/cgroup/user.slice/session.scope", "/sys/fs/cgroup/user.slice", "/sys/fs/cgroup"],
                         [row["directory"] for row in result["hierarchies"][0]["ancestors"]])

    def test_v1_separate_mounts_delegated_root_and_escaped_mountpoint(self):
        member = "2:cpu,cpuacct:/tenant/job\n3:memory:/tenant/job\n4:cpuset:/tenant/job"
        mount = "\n".join([
            "28 1 0:28 /tenant /sys/fs/cgroup/cpu\\040slice rw - cgroup cgroup rw,cpu,cpuacct",
            "29 1 0:29 / /sys/fs/cgroup/memory rw - cgroup cgroup rw,memory",
            "30 1 0:30 /tenant /sys/fs/cgroup/cpuset rw - cgroup cgroup rw,cpuset",
        ])
        values = {
            "/sys/fs/cgroup/cpu slice/job/cpu.cfs_quota_us": "-1",
            "/sys/fs/cgroup/cpu slice/job/cpu.cfs_period_us": "100000",
            "/sys/fs/cgroup/cpu slice/cpu.cfs_quota_us": "300000",
            "/sys/fs/cgroup/cpu slice/cpu.cfs_period_us": "100000",
            "/sys/fs/cgroup/memory/tenant/job/memory.limit_in_bytes": "67108864",
            "/sys/fs/cgroup/memory/tenant/memory.limit_in_bytes": "268435456",
            "/sys/fs/cgroup/memory/memory.limit_in_bytes": "9223372036854771712",
            "/sys/fs/cgroup/cpuset/job/cpuset.effective_cpus": "1-4",
            "/sys/fs/cgroup/cpuset/cpuset.cpus": "0-7",
        }
        result = cgroups.collect(member, mount, reader=values.get, affinity=[0, 1, 2, 3])
        self.assertEqual(3, result["visibleCpuQuotaUpperBound"])
        self.assertEqual(3, result["visibleCpuUpperBound"])
        self.assertEqual(67108864, result["visibleMemoryUpperBoundBytes"])
        self.assertEqual([1, 2, 3], result["affinityAndVisibleCpusetCpuIds"])
        self.assertTrue(result["hierarchies"][0]["ancestorsOutsideMountNotVisible"])
        self.assertEqual("/sys/fs/cgroup/cpu slice/job", result["hierarchies"][0]["processDirectory"])

    def test_unmapped_membership_is_unknown_instead_of_reading_unrelated_root(self):
        reads = []
        def reader(path):
            reads.append(path)
            return "max 100000"
        result = cgroups.collect("0::/different/job", "28 1 0:28 /other /sys/fs/cgroup rw - cgroup2 cgroup rw",
                                 reader=reader, affinity=[0, 1])
        self.assertEqual([], reads)
        self.assertEqual(1, len(result["unresolved"]))
        self.assertIsNone(result["visibleCpuQuotaUpperBound"])
        self.assertEqual(2, result["visibleCpuUpperBound"])

    def test_zero_memory_limit_is_a_real_limit(self):
        result = cgroups.collect("0::/", "28 1 0:28 / /sys/fs/cgroup rw - cgroup2 cgroup rw",
                                 reader={"/sys/fs/cgroup/memory.max": "0"}.get)
        self.assertEqual(0, result["visibleMemoryUpperBoundBytes"])

    def test_java_version_probe_does_not_echo_secret_jvm_environment_options(self):
        with patch.dict(os.environ, {"JAVA_TOOL_OPTIONS": "-Dpassword=sentinel", "JDK_JAVA_OPTIONS": "-Dtoken=sentinel", "_JAVA_OPTIONS": "-Dsecret=sentinel"}):
            with patch.object(preflight.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "version", "")) as run:
                preflight.command(["java", "-version"])
                environment = run.call_args.kwargs["env"]
                for key in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"):
                    self.assertNotIn(key, environment)


class LauncherLockTest(unittest.TestCase):
    def test_bash_reentry_preserves_the_lock_descriptor(self):
        helper = str(SCRIPTS / "launcher-lock.py")
        command = f'exec {shlex.quote(sys.executable)} {shlex.quote(helper)} --validate "$VM_REPLICATED_LOCK_FD" "$1"'
        with tempfile.TemporaryDirectory() as directory:
            lock = str(Path(directory) / "launcher.lock")
            result = subprocess.run([sys.executable, helper, lock, "bash", "-c", command, "lock-check", lock], timeout=5)
            self.assertEqual(0, result.returncode)

    def test_lock_survives_exec_rejects_second_launcher_and_releases_on_exit(self):
        helper = str(SCRIPTS / "launcher-lock.py")
        with tempfile.TemporaryDirectory() as directory:
            lock, ready = Path(directory) / "launcher.lock", Path(directory) / "ready"
            first = subprocess.Popen([sys.executable, helper, str(lock), sys.executable, "-c",
                                      "from pathlib import Path; import sys,time; Path(sys.argv[1]).write_text('ready'); time.sleep(10)", str(ready)])
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(ready.exists(), "First process did not start")
                second = subprocess.run([sys.executable, helper, str(lock), sys.executable, "-c", "pass"],
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(75, second.returncode)
                self.assertIn("no drivers were touched", second.stderr)
            finally:
                first.terminate()
                first.wait(timeout=5)
            self.assertTrue(lock.exists(), "Lock inode must not be unlinked on exit")
            third = subprocess.run([sys.executable, helper, str(lock), sys.executable, "-c", "pass"], timeout=5)
            self.assertEqual(0, third.returncode)

    def test_inherited_descriptor_validation_and_drop_for_persistent_infrastructure(self):
        helper = str(SCRIPTS / "launcher-lock.py")
        program = r"""import os,subprocess,sys
fd=int(os.environ['VM_REPLICATED_LOCK_FD'])
subprocess.run([sys.executable,sys.argv[1],'--validate',str(fd),sys.argv[2]],pass_fds=(fd,),check=True)
probe='import os,sys\ntry: os.fstat(int(sys.argv[1]))\nexcept OSError: sys.exit(0)\nraise SystemExit("Lock descriptor was inherited by persistent infrastructure")'
subprocess.run([sys.executable,sys.argv[1],'--without-lock',str(fd),sys.executable,'-c',probe,str(fd)],pass_fds=(fd,),check=True)
"""
        with tempfile.TemporaryDirectory() as directory:
            lock = str(Path(directory) / "launcher.lock")
            result = subprocess.run([sys.executable, helper, lock, sys.executable, "-c", program, helper, lock], timeout=5)
            self.assertEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
